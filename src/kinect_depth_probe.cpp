// Kinect2-Linux: IR + Depth diagnostics (no V4L2, no PAM, no stored biometrics).
// libfreenect2 Depth frames are float32, Z in millimeters, with invalid values <=0/NaN/Inf.
#include <libfreenect2/libfreenect2.hpp>
#include <libfreenect2/frame_listener_impl.h>
#include <libfreenect2/packet_pipeline.h>

#include <algorithm>
#include <cmath>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <vector>

namespace {
volatile std::sig_atomic_t keep_running = 1;
void stop_handler(int) { keep_running = 0; }

struct RegionStat {
  float median_mm;
  int valid;
  int total;
};

RegionStat region_depth(const float* z, int width, int height,
                        int cx, int cy, int radius) {
  std::vector<float> valid;
  int total = 0;
  for (int y = std::max(0, cy - radius); y <= std::min(height - 1, cy + radius); ++y) {
    for (int x = std::max(0, cx - radius); x <= std::min(width - 1, cx + radius); ++x) {
      ++total;
      const float value = z[y * width + x];
      // Validity check, not a promise of Kinect's advertised accuracy/range.
      if (std::isfinite(value) && value > 0.f && value < 10000.f)
        valid.push_back(value);
    }
  }
  if (valid.empty()) return {0.f, 0, total};
  const size_t mid = valid.size() / 2;
  std::nth_element(valid.begin(), valid.begin() + mid, valid.end());
  return {valid[mid], static_cast<int>(valid.size()), total};
}

float median_of(std::vector<float> v) {
  if (v.empty()) return 0.f;
  const size_t mid = v.size() / 2;
  std::nth_element(v.begin(), v.begin() + mid, v.end());
  return v[mid];
}
} // namespace

int main(int argc, char** argv) {
  long samples = 120;
  if (argc > 2) {
    std::cerr << "Usage: " << argv[0] << " [number_of_frames: 1..2000]\n";
    return 2;
  }
  if (argc == 2) {
    char* end = nullptr;
    samples = std::strtol(argv[1], &end, 10);
    if (!argv[1][0] || *end != '\0' || samples < 1 || samples > 2000) {
      std::cerr << "Frame count must be between 1 and 2000.\n";
      return 2;
    }
  }

  std::signal(SIGINT, stop_handler);
  std::signal(SIGTERM, stop_handler);

  libfreenect2::Freenect2 context;
  if (context.enumerateDevices() == 0) {
    std::cerr << "No Kinect found. Is another bridge using it?\n";
    return 1;
  }
  libfreenect2::Freenect2Device* device = context.openDevice(
      context.getDefaultDeviceSerialNumber(), new libfreenect2::CpuPacketPipeline());
  if (!device) {
    std::cerr << "Could not open Kinect. Stop ./kinect2 run first.\n";
    return 1;
  }

  libfreenect2::SyncMultiFrameListener listener(
      libfreenect2::Frame::Ir | libfreenect2::Frame::Depth);
  device->setIrAndDepthFrameListener(&listener);
  if (!device->startStreams(false, true)) {
    std::cerr << "Could not start IR+Depth.\n";
    device->close();
    return 1;
  }

  std::cout << "IR + Depth, 512x424; Depth Z in millimeters; Ctrl+C to stop.\n"
            << "Aim a flat object approximately 1 m away at the image center.\n";
  long received = 0, paired = 0, bad_format = 0, gaps = 0;
  long invalid_frames = 0;
  int timeouts = 0;
  uint32_t prev_seq = 0;
  bool previous = false;
  std::vector<float> center_medians;
  double valid_sum = 0.;

  for (long i = 0; i < samples && keep_running; ++i) {
    libfreenect2::FrameMap frames;
    if (!listener.waitForNewFrame(frames, 2000)) {
      if (!keep_running) break;
      std::cerr << "Timeout: no IR/Depth pair within 2 seconds.\n";
      if (++timeouts >= 3) break;
      --i;
      continue;
    }
    timeouts = 0;
    const auto itd = frames.find(libfreenect2::Frame::Depth);
    const auto iti = frames.find(libfreenect2::Frame::Ir);
    if (itd == frames.end() || iti == frames.end() || !itd->second || !iti->second) {
      ++invalid_frames;
      listener.release(frames);
      continue;
    }
    const libfreenect2::Frame* depth = itd->second;
    const libfreenect2::Frame* ir = iti->second;
    if (!depth->data || !ir->data || depth->width != 512 || depth->height != 424 ||
        ir->width != 512 || ir->height != 424 || depth->bytes_per_pixel != 4 ||
        ir->bytes_per_pixel != 4 || depth->format != libfreenect2::Frame::Float ||
        ir->format != libfreenect2::Frame::Float) {
      ++bad_format;
      listener.release(frames);
      continue;
    }

    const uint32_t seq = depth->sequence;
    if (previous && seq > prev_seq + 1) gaps += seq - prev_seq - 1;
    prev_seq = seq;
    previous = true;
    if (ir->sequence == depth->sequence && ir->timestamp == depth->timestamp) ++paired;
    const float* z = reinterpret_cast<const float*>(depth->data);
    const RegionStat center = region_depth(z, 512, 424, 256, 212, 24);
    if (center.valid) center_medians.push_back(center.median_mm);
    valid_sum += static_cast<double>(center.valid) / center.total;
    ++received;
    // Do not retain pointers to frame data after releasing frames.
    listener.release(frames);

    if (received == 1 || received % 30 == 0) {
      std::cout << "Frame " << received << " | center 49x49: ";
      if (center.valid)
        std::cout << std::fixed << std::setprecision(1) << center.median_mm << " mm";
      else
        std::cout << "NO VALID DEPTH";
      std::cout << " | valid " << center.valid << "/" << center.total << '\n';
    }
  }

  device->stop();
  device->close();

  std::cout << "\n=== SUMMARY ===\n"
            << "Received frames: " << received << "\n"
            << "Matching IR+Depth sequence/timestamps: " << paired << '/' << received << "\n"
            << "Sequence gaps: " << gaps << "\n"
            << "Bad frame formats: " << bad_format << "; missing pairs: " << invalid_frames << "\n";
  if (received) {
    std::cout << "Center ROI valid samples: " << std::fixed << std::setprecision(1)
              << 100.0 * valid_sum / received << "%\n";
  }
  if (!center_medians.empty()) {
    const float z = median_of(center_medians);
    std::cout << "Median center Z: " << std::fixed << std::setprecision(1)
              << z << " mm (" << z / 10.f << " cm)\n";
    std::cout << "Note: Z is optical-axis depth, not automatically tape-measure distance.\n";
  } else {
    std::cout << "No valid depth in the central region. Check target and distance.\n";
  }
  return (received > 0 && bad_format == 0 && !center_medians.empty()) ? 0 : 1;
}
