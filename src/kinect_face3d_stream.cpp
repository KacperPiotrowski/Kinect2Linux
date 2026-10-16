// Kinect2-Linux / Face3D stage 1
// Single Kinect owner. Streams paired, full-precision IR + Depth float32 frames
// through an inherited file descriptor (never stdout, which libfreenect2 may log to).
// No PAM integration, no biometric model storage, no V4L2 required.
#include <libfreenect2/libfreenect2.hpp>
#include <libfreenect2/frame_listener_impl.h>
#include <libfreenect2/packet_pipeline.h>

#include <cerrno>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <limits>
#include <unistd.h>

namespace {
volatile std::sig_atomic_t running = 1;
void stop_handler(int) { running = 0; }

constexpr std::uint32_t WIDTH = 512;
constexpr std::uint32_t HEIGHT = 424;
constexpr std::size_t PLANE_BYTES = WIDTH * HEIGHT * sizeof(float);

struct Header {
  char magic[8];
  std::uint32_t sequence;
  std::uint32_t timestamp;
  std::uint32_t width;
  std::uint32_t height;
  float fx;
  float fy;
  float cx;
  float cy;
};
static_assert(sizeof(Header) == 40, "Stream header must be 40 bytes");

bool write_all(int fd, const void* data, std::size_t size) {
  const char* p = static_cast<const char*>(data);
  while (size > 0 && running) {
    const ssize_t n = ::write(fd, p, size);
    if (n > 0) { p += n; size -= static_cast<std::size_t>(n); continue; }
    if (n < 0 && errno == EINTR) continue;
    if (n < 0 && (errno == EPIPE || errno == EBADF)) return false;
    if (n < 0) std::cerr << "Face3D stream write error: " << std::strerror(errno) << '\n';
    return false;
  }
  return size == 0;
}

bool valid_frame(const libfreenect2::Frame* f) {
  return f && f->data && f->width == static_cast<int>(WIDTH) &&
    f->height == static_cast<int>(HEIGHT) && f->bytes_per_pixel == 4 &&
    f->format == libfreenect2::Frame::Float;
}
} // namespace

int main(int argc, char** argv) {
  if (argc != 2) {
    std::cerr << "Usage: kinect_face3d_stream <inherited_write_fd>\n";
    return 2;
  }
  char* end = nullptr;
  const long descriptor = std::strtol(argv[1], &end, 10);
  if (!argv[1][0] || !end || *end || descriptor < 3 ||
      descriptor > std::numeric_limits<int>::max()) {
    std::cerr << "Invalid stream file descriptor\n";
    return 2;
  }
  const int fd = static_cast<int>(descriptor);
  std::signal(SIGINT, stop_handler);
  std::signal(SIGTERM, stop_handler);
  std::signal(SIGPIPE, SIG_IGN);

  libfreenect2::Freenect2 context;
  if (context.enumerateDevices() < 1) {
    std::cerr << "Face3D: no Kinect v2 detected\n";
    return 1;
  }
  auto* device = context.openDevice(context.getDefaultDeviceSerialNumber(),
                                    new libfreenect2::CpuPacketPipeline());
  if (!device) {
    std::cerr << "Face3D: cannot open Kinect; stop other Kinect programs first\n";
    return 1;
  }

  libfreenect2::SyncMultiFrameListener listener(
      libfreenect2::Frame::Ir | libfreenect2::Frame::Depth);
  device->setIrAndDepthFrameListener(&listener);
  if (!device->startStreams(false, true)) {
    std::cerr << "Face3D: cannot start IR/Depth streams\n";
    device->close();
    return 1;
  }

  const auto camera = device->getIrCameraParams();
  if (!(camera.fx > 0.0f && camera.fy > 0.0f)) {
    std::cerr << "Face3D: invalid IR camera intrinsics" << std::endl;
    device->stop();
    device->close();
    return 1;
  }
  std::cerr << "Face3D: streaming synchronized IR+Depth float32 512x424"
            << " fx=" << camera.fx << " fy=" << camera.fy << std::endl;
  std::uint32_t previous = 0;
  bool has_previous = false;
  std::uint64_t received = 0, skipped = 0, gaps = 0;
  int timeouts = 0;
  while (running) {
    libfreenect2::FrameMap frames;
    if (!listener.waitForNewFrame(frames, 750)) {
      if (++timeouts >= 5) {
        std::cerr << "Face3D: timeout waiting for sensor\n";
        break;
      }
      continue;
    }
    timeouts = 0;
    auto iti = frames.find(libfreenect2::Frame::Ir);
    auto itd = frames.find(libfreenect2::Frame::Depth);
    const libfreenect2::Frame* ir = iti == frames.end() ? nullptr : iti->second;
    const libfreenect2::Frame* dep = itd == frames.end() ? nullptr : itd->second;
    if (!valid_frame(ir) || !valid_frame(dep) ||
        ir->sequence != dep->sequence || ir->timestamp != dep->timestamp) {
      ++skipped;
      listener.release(frames);
      continue;
    }
    if (has_previous && dep->sequence > previous + 1)
      gaps += dep->sequence - previous - 1;
    previous = dep->sequence;
    has_previous = true;
    Header h{{'K','2','F','3','D','0','0','2'},
             dep->sequence, dep->timestamp, WIDTH, HEIGHT,
             camera.fx, camera.fy, camera.cx, camera.cy};
    const bool ok = write_all(fd, &h, sizeof(h)) &&
                    write_all(fd, ir->data, PLANE_BYTES) &&
                    write_all(fd, dep->data, PLANE_BYTES);
    listener.release(frames);
    if (!ok) break;
    ++received;
    if (received % 300 == 0)
      std::cerr << "Face3D: frames=" << received << " seq_gaps=" << gaps
                << " invalid_pairs=" << skipped << '\n';
  }
  device->stop();
  device->close();
  ::close(fd);
  std::cerr << "Face3D stopped: frames=" << received << " gaps=" << gaps << '\n';
  return received ? 0 : 1;
}
