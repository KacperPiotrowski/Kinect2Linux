// Kinect2-Linux IR -> V4L2 bridge (experimental)
// Target: libfreenect2 0.2, CPU depth pipeline with our OpenMP bilateral filter.
// The full float32 IR values are used for conversion; 8-bit luminance is only
// an output format for widely compatible V4L2 consumers (including OpenCV/Howdy).
// Usage: ./kinect_ir_bridge [/dev/video10]

#include <libfreenect2/libfreenect2.hpp>
#include <libfreenect2/frame_listener_impl.h>
#include <libfreenect2/packet_pipeline.h>

#include <linux/videodev2.h>
#include <sys/ioctl.h>
#include <fcntl.h>
#include <unistd.h>
#include <cerrno>
#include <csignal>
#include <cstring>
#include <cmath>
#include <cstdint>
#include <algorithm>
#include <iostream>
#include <vector>
#include <string>

namespace {
volatile std::sig_atomic_t running = 1;
void stop_handler(int) { running = 0; }

// A single V4L2 write is one complete frame. Never retry a short write with
// only the remaining bytes: v4l2loopback would treat them as a second frame.
enum class WriteResult { Ok, Drop, Stop, Error };

WriteResult write_frame(int fd, const std::vector<uint8_t>& bytes)
{
  for (;;) {
    if (!running) return WriteResult::Stop;
    const ssize_t n = ::write(fd, bytes.data(), bytes.size());
    if (n == static_cast<ssize_t>(bytes.size())) return WriteResult::Ok;
    if (n < 0 && errno == EINTR) {
      if (!running) return WriteResult::Stop;
      continue;
    }
    if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
      return WriteResult::Drop; // Don't build up a queue of stale video frames.

    if (n >= 0)
      std::cerr << "V4L2 short write: " << n << " of " << bytes.size()
                << " bytes (incomplete frame)\n";
    else
      std::cerr << "V4L2 write error: " << std::strerror(errno) << '\n';
    return WriteResult::Error;
  }
}

bool install_stop_handlers()
{
  // Unlike std::signal() on glibc, no SA_RESTART: interruptible syscalls
  // should return EINTR when Ctrl+C is pressed.
  struct sigaction sa{};
  sa.sa_handler = stop_handler;
  sigemptyset(&sa.sa_mask);
  sa.sa_flags = 0;
  return sigaction(SIGINT, &sa, nullptr) == 0 &&
         sigaction(SIGTERM, &sa, nullptr) == 0;
}

// Estimate intensity levels from a small subset. Ignore zero/invalid pixels.
bool estimate_levels(const float* ir, int width, int height, float& low, float& high)
{
  std::vector<float> sample;
  sample.reserve(((width + 3) / 4) * ((height + 3) / 4));
  for (int y = 0; y < height; y += 4)
    for (int x = 0; x < width; x += 4) {
      const float v = ir[y * width + x];
      if (std::isfinite(v) && v > 0.f) sample.push_back(v);
    }
  if (sample.size() < 100) return false;
  const size_t ilo = sample.size() / 100;            // 1st percentile
  const size_t ihi = sample.size() * 995 / 1000;     // 99.5th percentile
  std::nth_element(sample.begin(), sample.begin() + ilo, sample.end());
  low = sample[ilo];
  std::nth_element(sample.begin(), sample.begin() + ihi, sample.end());
  high = std::max(sample[ihi], low + 1.f);
  return true;
}

uint8_t luminance(float value, float low, float high)
{
  if (!std::isfinite(value) || value <= 0.f) return 0;
  const float t = std::max(0.f, std::min(1.f, (value - low) / (high - low)));
  return static_cast<uint8_t>(std::sqrt(t) * 255.f + 0.5f);
}
} // namespace

int main(int argc, char** argv)
{
  if (argc > 2) {
    std::cerr << "Usage: " << argv[0] << " [/dev/video10]\n";
    return 2;
  }
  const std::string v4l_device = argc == 2 ? argv[1] : "/dev/video10";
  if (!install_stop_handlers()) {
    std::cerr << "Cannot install signal handlers: " << std::strerror(errno) << '\n';
    return 1;
  }

  // Request nonblocking I/O (driver-internal mutex waits are still possible).
  const int fd = ::open(v4l_device.c_str(), O_WRONLY | O_NONBLOCK | O_CLOEXEC);
  if (fd < 0) {
    std::cerr << "Cannot open " << v4l_device << ": " << std::strerror(errno)
              << "\nCreate it with v4l2loopback first.\n";
    return 1;
  }

  constexpr int WIDTH = 512, HEIGHT = 424;
  v4l2_format fmt{};
  fmt.type = V4L2_BUF_TYPE_VIDEO_OUTPUT;
  fmt.fmt.pix.width = WIDTH;
  fmt.fmt.pix.height = HEIGHT;
  fmt.fmt.pix.pixelformat = V4L2_PIX_FMT_YUYV;
  fmt.fmt.pix.field = V4L2_FIELD_NONE;
  fmt.fmt.pix.colorspace = V4L2_COLORSPACE_SRGB;
  fmt.fmt.pix.bytesperline = WIDTH * 2;
  fmt.fmt.pix.sizeimage = WIDTH * HEIGHT * 2;
  if (::ioctl(fd, VIDIOC_S_FMT, &fmt) < 0 ||
      fmt.fmt.pix.width != WIDTH || fmt.fmt.pix.height != HEIGHT ||
      fmt.fmt.pix.pixelformat != V4L2_PIX_FMT_YUYV ||
      fmt.fmt.pix.bytesperline != WIDTH * 2) {
    std::cerr << "Cannot negotiate 512x424 YUYV with " << v4l_device
              << ": " << std::strerror(errno) << '\n';
    ::close(fd);
    return 1;
  }

  v4l2_streamparm parm{};
  parm.type = V4L2_BUF_TYPE_VIDEO_OUTPUT;
  parm.parm.output.timeperframe.numerator = 1;
  parm.parm.output.timeperframe.denominator = 30;
  ::ioctl(fd, VIDIOC_S_PARM, &parm); // optional, driver may ignore it

  libfreenect2::Freenect2 freenect;
  if (freenect.enumerateDevices() < 1) {
    std::cerr << "Kinect v2 not found.\n";
    ::close(fd);
    return 1;
  }
  libfreenect2::Freenect2Device* device = freenect.openDevice(
      freenect.getDefaultDeviceSerialNumber(), new libfreenect2::CpuPacketPipeline());
  if (!device) {
    std::cerr << "Cannot open Kinect. Close any other Kinect programs.\n";
    ::close(fd);
    return 1;
  }

  libfreenect2::SyncMultiFrameListener listener(
      libfreenect2::Frame::Ir | libfreenect2::Frame::Depth);
  device->setIrAndDepthFrameListener(&listener);
  if (!device->startStreams(false, true)) {
    std::cerr << "Cannot start Kinect IR/Depth streams.\n";
    device->close();
    ::close(fd);
    return 1;
  }

  std::vector<uint8_t> yuyv(WIDTH * HEIGHT * 2);
  float smooth_low = 0.f, smooth_high = 1.f;
  bool calibrated = false;
  uint32_t prev_seq = 0;
  bool have_seq = false;
  uint64_t count = 0, skipped = 0, output_drops = 0;
  bool success = true;
  unsigned int consecutive_timeouts = 0;

  std::cout << "Kinect IR -> " << v4l_device
            << " | 512x424 YUYV | Ctrl+C to stop\n" << std::flush;

  while (running) {
    libfreenect2::FrameMap frames;
    if (!listener.waitForNewFrame(frames, 500)) {
      // Short timeouts make stop responsive even when the Kinect stops sending.
      if (running && (++consecutive_timeouts % 4 == 0))
        std::cerr << "IR frame timeout (2 s without frames).\n";
      continue;
    }
    consecutive_timeouts = 0;
    auto it = frames.find(libfreenect2::Frame::Ir);
    if (it == frames.end() || !it->second) {
      std::cerr << "Missing IR frame.\n";
      listener.release(frames);
      continue;
    }
    const libfreenect2::Frame* ir = it->second;
    if (!ir->data || ir->width != WIDTH || ir->height != HEIGHT ||
        ir->bytes_per_pixel != sizeof(float) || ir->format != libfreenect2::Frame::Float) {
      std::cerr << "Unexpected IR frame format.\n";
      listener.release(frames);
      success = false;
      break;
    }
    // Read the raw float32 frame *before* release().
    const float* pixels = reinterpret_cast<const float*>(ir->data);
    if (!calibrated || (count % 15 == 0)) {
      float low = 0.f, high = 1.f;
      if (estimate_levels(pixels, WIDTH, HEIGHT, low, high)) {
        if (!calibrated) { smooth_low = low; smooth_high = high; calibrated = true; }
        else {
          smooth_low = 0.75f * smooth_low + 0.25f * low;
          smooth_high = 0.75f * smooth_high + 0.25f * high;
        }
      }
    }
    for (size_t i = 0; i < static_cast<size_t>(WIDTH * HEIGHT); i += 2) {
      yuyv[i*2] = luminance(pixels[i], smooth_low, smooth_high);
      yuyv[i*2 + 1] = 128;    // U: neutral chroma
      yuyv[i*2 + 2] = luminance(pixels[i+1], smooth_low, smooth_high);
      yuyv[i*2 + 3] = 128;    // V: neutral chroma
    }
    if (have_seq && ir->sequence > prev_seq + 1)
      skipped += static_cast<uint64_t>(ir->sequence - prev_seq - 1);
    prev_seq = ir->sequence;
    have_seq = true;

    // Output uses only our own byte buffer, so we can release the Kinect frame first.
    listener.release(frames);
    const WriteResult wr = write_frame(fd, yuyv);
    if (wr == WriteResult::Stop) break;
    if (wr == WriteResult::Error) { success = false; break; }
    if (wr == WriteResult::Drop) ++output_drops;
    else ++count;
    if (count > 0 && count % 300 == 0 && wr == WriteResult::Ok) {
      std::cout << "Frames: " << count << ", sequence gaps: " << skipped
                << ", V4L2 output drops: " << output_drops
                << ", IR levels: " << smooth_low << " .. " << smooth_high << '\n'
                << std::flush;
    }
  }

  device->stop();
  device->close();
  ::close(fd);
  std::cout << "Stopped. Frames: " << count << ", sequence gaps: " << skipped
            << ", V4L2 output drops: " << output_drops << '\n';
  return success ? 0 : 1;
}
