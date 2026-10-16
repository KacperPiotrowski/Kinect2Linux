// Kinect2-Linux: snapshot of one calibrated Kinect v2 point cloud.
// Requires libfreenect2 (CPU/OpenMP build); never writes to PAM or V4L2.
// Output: ASCII PLY (XYZ in metres, artificial greyscale) + calibration JSON.
#include <libfreenect2/libfreenect2.hpp>
#include <libfreenect2/frame_listener_impl.h>
#include <libfreenect2/packet_pipeline.h>
#include <libfreenect2/registration.h>

#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <string>
#include <vector>

namespace {
struct Point { float x, y, z; std::uint8_t shade; };

bool save_ply(const std::string& path, const std::vector<Point>& points,
              const std::string& serial) {
  std::ofstream out(path.c_str(), std::ios::binary);
  if (!out) return false;
  out << "ply\nformat ascii 1.0\n"
      << "comment Kinect2-Linux point cloud - single sensor, not calibrated to world\n"
      << "comment sensor_serial " << serial << "\n"
      << "comment units meters; camera X right, Y down, Z forward\n"
      << "comment colors are artificial depth greyscale, NOT visible-light RGB\n"
      << "element vertex " << points.size() << "\n"
      << "property float x\nproperty float y\nproperty float z\n"
      << "property uchar red\nproperty uchar green\nproperty uchar blue\n"
      << "end_header\n";
  out << std::fixed << std::setprecision(6);
  for (const Point& p : points) {
    const unsigned int k = p.shade;
    out << p.x << ' ' << p.y << ' ' << p.z << ' '
        << k << ' ' << k << ' ' << k << '\n';
  }
  return out.good();
}

bool save_calibration(const std::string& path,
                      const libfreenect2::Freenect2Device::IrCameraParams& c,
                      const std::string& serial, std::uint32_t seq,
                      std::uint32_t timestamp) {
  std::ofstream out(path.c_str());
  if (!out) return false;
  out << std::setprecision(9)
      << "{\n"
      << "  \"device_serial\": \"" << serial << "\",\n"
      << "  \"depth_sequence\": " << seq << ",\n"
      << "  \"depth_timestamp\": " << timestamp << ",\n"
      << "  \"width\": 512, \"height\": 424,\n"
      << "  \"intrinsics\": {\n"
      << "    \"fx\": " << c.fx << ", \"fy\": " << c.fy << ",\n"
      << "    \"cx\": " << c.cx << ", \"cy\": " << c.cy << ",\n"
      << "    \"k1\": " << c.k1 << ", \"k2\": " << c.k2 << ",\n"
      << "    \"k3\": " << c.k3 << ", \"p1\": " << c.p1 << ",\n"
      << "    \"p2\": " << c.p2 << "\n"
      << "  }\n}\n";
  return out.good();
}
} // namespace

int main(int argc, char** argv) {
  if (argc != 2) {
    std::cerr << "Usage: " << argv[0] << " output.ply\n"
              << "Stop ./kinect2 run before starting.\n";
    return 2;
  }
  const std::string target = argv[1];

  libfreenect2::Freenect2 context;
  if (context.enumerateDevices() < 1) {
    std::cerr << "No Kinect v2 found. Check USB and stop other Kinect processes.\n";
    return 1;
  }
  libfreenect2::Freenect2Device* device = context.openDevice(
      context.getDefaultDeviceSerialNumber(), new libfreenect2::CpuPacketPipeline());
  if (!device) {
    std::cerr << "Cannot open Kinect. Is ./kinect2 run still active?\n";
    return 1;
  }
  const std::string serial = device->getSerialNumber();
  libfreenect2::SyncMultiFrameListener listener(
      libfreenect2::Frame::Ir | libfreenect2::Frame::Depth);
  device->setIrAndDepthFrameListener(&listener);
  if (!device->startStreams(false, true)) {
    std::cerr << "Failed to start IR/Depth.\n";
    device->close();
    return 1;
  }

  const auto calibration = device->getIrCameraParams();
  libfreenect2::Registration registration(calibration, device->getColorCameraParams());
  libfreenect2::Frame undistorted(512, 424, 4);
  std::vector<Point> points;
  std::uint32_t seq = 0, timestamp = 0;
  bool captured = false;
  int good_frames = 0, timeouts = 0;

  std::cout << "Capturing a 3D frame from " << serial << " (warming up 45 frames)...\n";
  while (good_frames < 45 && timeouts < 3) {
    libfreenect2::FrameMap frames;
    if (!listener.waitForNewFrame(frames, 2000)) {
      ++timeouts;
      std::cerr << "Timeout waiting for sensor (" << timeouts << "/3).\n";
      continue;
    }
    timeouts = 0;
    auto it_depth = frames.find(libfreenect2::Frame::Depth);
    auto it_ir = frames.find(libfreenect2::Frame::Ir);
    if (it_depth != frames.end() && it_ir != frames.end() &&
        it_depth->second && it_ir->second) {
      const libfreenect2::Frame* depth = it_depth->second;
      const libfreenect2::Frame* ir = it_ir->second;
      if (depth->width == 512 && depth->height == 424 && depth->bytes_per_pixel == 4 &&
          depth->format == libfreenect2::Frame::Float &&
          depth->data && ir->data && depth->sequence == ir->sequence &&
          depth->timestamp == ir->timestamp) {
        ++good_frames;
        if (good_frames == 45) {
          registration.undistortDepth(depth, &undistorted);
          const float* zdata = reinterpret_cast<const float*>(undistorted.data);
          points.reserve(512 * 424);
          for (int y = 0; y < 424; ++y) {
            for (int x = 0; x < 512; ++x) {
              const float depth_mm = zdata[y * 512 + x];
              if (!std::isfinite(depth_mm) || depth_mm < 450.f || depth_mm > 4500.f)
                continue;
              float px, py, pz;
              registration.getPointXYZ(&undistorted, y, x, px, py, pz);
              if (!std::isfinite(px) || !std::isfinite(py) || !std::isfinite(pz))
                continue;
              const float scaled = (pz - 0.45f) / (4.5f - 0.45f);
              const float brightness = 245.f - 190.f * scaled;
              points.push_back({px, py, pz, static_cast<std::uint8_t>(brightness)});
            }
          }
          seq = depth->sequence;
          timestamp = depth->timestamp;
          captured = true;
        }
      }
    }
    listener.release(frames);
  }

  device->stop();
  device->close();
  if (!captured || points.empty()) {
    std::cerr << "No usable 3D points; nothing was saved.\n";
    return 1;
  }
  if (!save_ply(target, points, serial) ||
      !save_calibration(target + ".calibration.json", calibration, serial, seq, timestamp)) {
    std::cerr << "Cannot write output. Check path and disk permissions.\n";
    return 1;
  }
  std::cout << "Saved " << points.size() << " 3D points to " << target << '\n'
            << "Calibration: " << target << ".calibration.json\n"
            << "Point coordinates are in METRES, in this Kinect's own frame.\n"
            << "Do not upload face scans publicly (they may contain biometric data).\n";
  return 0;
}
