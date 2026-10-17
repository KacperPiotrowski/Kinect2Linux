#include "core/v4l2_rgb_output.hpp"

#include <cerrno>
#include <chrono>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <linux/videodev2.h>
#include <poll.h>
#include <stdexcept>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <unistd.h>
#include <utility>

namespace kinect2 {
namespace {
constexpr std::uint32_t WIDTH = 1920;
constexpr std::uint32_t HEIGHT = 1080;
constexpr std::size_t RAW_SIZE = std::size_t(WIDTH) * HEIGHT * 4;
constexpr std::size_t OUT_SIZE = std::size_t(WIDTH) * HEIGHT * 2;
// v4l2loopback >=0.13 private event used by the existing working RGB bridge.
constexpr std::uint32_t CLIENT_USAGE =
    V4L2_EVENT_PRIVATE_START + 0x08E00000u + 1u;

std::uint8_t clamp8(int x) noexcept {
  return static_cast<std::uint8_t>(x < 0 ? 0 : (x > 255 ? 255 : x));
}
void yuv(std::uint8_t r, std::uint8_t g, std::uint8_t b,
         std::uint8_t& y, std::uint8_t& u, std::uint8_t& v) noexcept {
  y = clamp8(((66 * r + 129 * g + 25 * b + 128) >> 8) + 16);
  u = clamp8(((-38 * r - 74 * g + 112 * b + 128) >> 8) + 128);
  v = clamp8(((112 * r - 94 * g - 18 * b + 128) >> 8) + 128);
}
} // namespace

bool bgrx_to_yuyv(const std::uint8_t* src, std::size_t source_bytes,
                  std::uint8_t* dst, std::size_t destination_bytes,
                  std::uint32_t width, std::uint32_t height,
                  std::uint32_t source_stride) noexcept {
  if (!src || !dst || !width || !height || width % 2 ||
      width > 1920 || height > 1080 ||
      std::uint64_t(source_stride) < std::uint64_t(width) * 4 ||
      std::uint64_t(source_stride) * height > source_bytes ||
      std::uint64_t(width) * height * 2 > destination_bytes) return false;
  for (std::uint32_t y = 0; y < height; ++y) {
    const auto* in = src + std::size_t(y) * source_stride;
    auto* out = dst + std::size_t(y) * width * 2;
    for (std::uint32_t x = 0; x < width; x += 2) {
      const auto* a = in + std::size_t(x) * 4;
      const auto* b = a + 4;
      std::uint8_t y0, u0, v0, y1, u1, v1;
      yuv(a[2], a[1], a[0], y0, u0, v0);
      yuv(b[2], b[1], b[0], y1, u1, v1);
      out[std::size_t(x) * 2] = y0;
      out[std::size_t(x) * 2 + 1] =
          static_cast<std::uint8_t>((unsigned(u0) + u1 + 1) / 2);
      out[std::size_t(x) * 2 + 2] = y1;
      out[std::size_t(x) * 2 + 3] =
          static_cast<std::uint8_t>((unsigned(v0) + v1 + 1) / 2);
    }
  }
  return true;
}

V4l2RgbOutput::~V4l2RgbOutput() { stop(); }

std::string V4l2RgbOutput::last_error() const {
  std::lock_guard<std::mutex> guard(mutex_);
  return last_error_;
}

void V4l2RgbOutput::set_error(std::string error) noexcept {
  std::lock_guard<std::mutex> guard(mutex_);
  last_error_.swap(error);
}

bool V4l2RgbOutput::start(const std::string& path) noexcept {
  if (running_.load() || fd_ >= 0) return false;
  // Refuse unrelated video devices; /dev/video10 is used by the IR bridge.
  if (path != "/dev/video11") {
    set_error("only /dev/video11 is supported");
    return false;
  }
  char name[64]{};
  const int nfd = ::open("/sys/class/video4linux/video11/name",
                         O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (nfd < 0) {
    set_error("cannot read Kinect v2 virtual camera name");
    return false;
  }
  const ssize_t n = ::read(nfd, name, sizeof(name) - 1);
  ::close(nfd);
  if (n <= 0 || std::string(name) != "Kinect v2 RGB\n") {
    set_error("refusing unexpected /dev/video11 device");
    return false;
  }
  const int fd = ::open(path.c_str(), O_WRONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
  if (fd < 0) {
    set_error("cannot open /dev/video11: old RGB service may own the writer");
    return false;
  }
  v4l2_format format{};
  format.type = V4L2_BUF_TYPE_VIDEO_OUTPUT;
  format.fmt.pix.width = WIDTH;
  format.fmt.pix.height = HEIGHT;
  format.fmt.pix.pixelformat = V4L2_PIX_FMT_YUYV;
  format.fmt.pix.field = V4L2_FIELD_NONE;
  format.fmt.pix.colorspace = V4L2_COLORSPACE_SMPTE170M;
  format.fmt.pix.bytesperline = WIDTH * 2;
  format.fmt.pix.sizeimage = OUT_SIZE;
  if (::ioctl(fd, VIDIOC_S_FMT, &format) != 0 ||
      format.fmt.pix.width != WIDTH || format.fmt.pix.height != HEIGHT ||
      format.fmt.pix.pixelformat != V4L2_PIX_FMT_YUYV ||
      format.fmt.pix.bytesperline != WIDTH * 2) {
    set_error("V4L2 cannot negotiate Kinect RGB 1920x1080 YUYV");
    ::close(fd);
    return false;
  }
  v4l2_event_subscription sub{};
  sub.type = CLIENT_USAGE;
  sub.flags = V4L2_EVENT_SUB_FL_SEND_INITIAL;
  if (::ioctl(fd, VIDIOC_SUBSCRIBE_EVENT, &sub) != 0) {
    set_error("v4l2loopback client-usage events unavailable (requires >=0.13)");
    ::close(fd);
    return false;
  }
  v4l2_streamparm parm{};
  parm.type = V4L2_BUF_TYPE_VIDEO_OUTPUT;
  parm.parm.output.timeperframe.numerator = 1;
  parm.parm.output.timeperframe.denominator = 30;
  (void)::ioctl(fd, VIDIOC_S_PARM, &parm); // best-effort

  try {
    pending_.resize(RAW_SIZE);
    work_.resize(RAW_SIZE);
    yuyv_.resize(OUT_SIZE);
    black_.resize(OUT_SIZE);
    for (std::size_t i = 0; i < OUT_SIZE; i += 4) {
      black_[i] = 16; black_[i + 1] = 128;
      black_[i + 2] = 16; black_[i + 3] = 128;
    }
    fd_ = fd;
    readers_.store(0);
    frames_.store(0);
    drops_.store(0);
    needs_black_ = true;
    has_pending_ = false;
    set_error("");
    running_.store(true);
    worker_ = std::thread(&V4l2RgbOutput::loop, this);
  } catch (...) {
    running_.store(false);
    if (fd_ >= 0) { ::close(fd_); fd_ = -1; }
    else ::close(fd);
    set_error("cannot allocate V4L2 buffers or start worker");
    return false;
  }
  std::cerr << "Kinect RGB V4L2 attached in-process to broker on /dev/video11\n";
  return true;
}

void V4l2RgbOutput::stop() noexcept {
  running_.store(false);
  wake_.notify_all();
  if (worker_.joinable()) worker_.join();
  readers_.store(0);
  if (fd_ >= 0) { ::close(fd_); fd_ = -1; }
}

bool V4l2RgbOutput::drain_usage() noexcept {
  while (running_.load()) {
    v4l2_event event{};
    if (::ioctl(fd_, VIDIOC_DQEVENT, &event) < 0) {
      if (errno == EINTR) continue;
      if (errno == EAGAIN || errno == ENOENT) return true;
      set_error("V4L2 client usage event read failed");
      return false;
    }
    if (event.type != CLIENT_USAGE) continue;
    std::uint32_t count = 0;
    std::memcpy(&count, event.u.data, sizeof(count));
    if (count == readers_.load()) continue;
    readers_.store(count);
    if (count == 0) {
      std::lock_guard<std::mutex> guard(mutex_);
      has_pending_ = false;
      needs_black_ = true;
    }
    std::cerr << "Broker V4L2 streaming clients: " << count << '\n';
  }
  return true;
}

void V4l2RgbOutput::write_black() noexcept {
  if (!needs_black_) return; // Only the V4L2 worker accesses this flag.
  const ssize_t n = ::write(fd_, black_.data(), black_.size());
  if (n == static_cast<ssize_t>(black_.size())) {
    needs_black_ = false;
  } else if (n != -1 || (errno != EAGAIN && errno != EWOULDBLOCK)) {
    set_error("failed to write V4L2 privacy black frame");
    running_.store(false);
  }
}

void V4l2RgbOutput::loop() noexcept {
  while (running_.load()) {
    pollfd poll_event{fd_, POLLPRI, 0};
    const int polled = ::poll(&poll_event, 1, 0);
    if (polled < 0 && errno != EINTR) {
      set_error("V4L2 poll failed");
      break;
    }
    if (polled > 0 && (poll_event.revents & (POLLERR | POLLHUP | POLLNVAL))) {
      set_error("V4L2 writer disconnected");
      break;
    }
    if (polled > 0 && (poll_event.revents & POLLPRI) && !drain_usage())
      break;

    if (readers_.load() == 0) write_black();
    if (!running_.load()) break;

    {
      std::unique_lock<std::mutex> lock(mutex_);
      if (!has_pending_)
        wake_.wait_for(lock, std::chrono::milliseconds(35), [&] {
          return !running_.load() || has_pending_;
        });
      if (!running_.load()) break;
      if (!has_pending_) continue;
      work_.swap(pending_);
      has_pending_ = false;
    }
    if (!readers_.load()) continue;
    if (!bgrx_to_yuyv(work_.data(), work_.size(), yuyv_.data(), yuyv_.size(),
                      WIDTH, HEIGHT, WIDTH * 4)) {
      set_error("invalid broker RGB conversion buffer");
      break;
    }
    if (!readers_.load()) continue;
    const ssize_t n = ::write(fd_, yuyv_.data(), yuyv_.size());
    if (n == static_cast<ssize_t>(yuyv_.size())) {
      ++frames_;
    } else if (n == -1 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
      ++drops_; // Always skip stale frame: USB and clients must not stall.
    } else if (n == -1 && errno == EINTR) {
      ++drops_;
    } else {
      set_error("V4L2 RGB output write failed");
      break;
    }
  }
  readers_.store(0);
  running_.store(false);
}

void V4l2RgbOutput::publish(FrameKind kind, const std::uint8_t* bytes,
                            std::uint32_t width, std::uint32_t height,
                            std::uint32_t bpp, std::uint32_t) noexcept {
  if (kind != FrameKind::rgb || !running_.load() || !readers_.load() ||
      !bytes || width != WIDTH || height != HEIGHT || bpp != 4)
    return;
  // Two preallocated raw 8MB slots, never a growing queue. On contention
  // newer frames overwrite older pending frames; the pump only does memcpy.
  std::lock_guard<std::mutex> guard(mutex_);
  if (!running_.load() || !readers_.load()) return;
  std::memcpy(pending_.data(), bytes, RAW_SIZE);
  if (has_pending_) ++drops_;
  has_pending_ = true;
  wake_.notify_one();
}

} // namespace kinect2
