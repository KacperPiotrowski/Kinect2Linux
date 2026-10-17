#pragma once

#include "core/frame_hub.hpp"

#include <atomic>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace kinect2 {

// Pure pixel conversion, for native Kinect RGB BGRX -> V4L2 YUYV422.
// Returns false for unsupported dimensions, stride or insufficient buffers.
// Source is row-major B, G, R, ignored X; destination uses Y0 U Y1 V.
bool bgrx_to_yuyv(const std::uint8_t* src, std::size_t source_bytes,
                  std::uint8_t* dst, std::size_t destination_bytes,
                  std::uint32_t width, std::uint32_t height,
                  std::uint32_t source_stride) noexcept;

// Optional *in-process* V4L2 output. Never touches libfreenect2/USB.
// Capturing hardware can publish from its pump thread without waiting for
// V4L2 writes or colorspace conversion. Latest-frame only: one bounded
// pending RGB slot plus one worker buffer.
class V4l2RgbOutput final : public FrameSink {
 public:
  V4l2RgbOutput() = default;
  ~V4l2RgbOutput() override;
  V4l2RgbOutput(const V4l2RgbOutput&) = delete;
  V4l2RgbOutput& operator=(const V4l2RgbOutput&) = delete;

  // Only open the expected Kinect v2 virtual RGB camera, never /dev/video10.
  bool start(const std::string& path = "/dev/video11") noexcept;
  void stop() noexcept;
  void publish(FrameKind kind, const std::uint8_t* bytes,
               std::uint32_t width, std::uint32_t height,
               std::uint32_t bytes_per_pixel,
               std::uint32_t sequence) noexcept override;

  [[nodiscard]] bool active() const noexcept { return running_.load(); }
  [[nodiscard]] unsigned viewers() const noexcept { return readers_.load(); }
  [[nodiscard]] std::uint64_t frames_written() const noexcept { return frames_.load(); }
  [[nodiscard]] std::uint64_t drops() const noexcept { return drops_.load(); }
  [[nodiscard]] std::string last_error() const;

 private:
  void loop() noexcept;
  bool drain_usage() noexcept;
  void set_error(std::string error) noexcept;
  void write_black() noexcept;

  int fd_ = -1;  // owned by worker thread after start(), joined before close
  std::atomic<bool> running_{false};
  std::atomic<unsigned> readers_{0};
  std::atomic<std::uint64_t> frames_{0};
  std::atomic<std::uint64_t> drops_{0};
  mutable std::mutex mutex_;
  std::condition_variable wake_;
  std::vector<std::uint8_t> pending_;
  std::vector<std::uint8_t> work_;
  std::vector<std::uint8_t> yuyv_;
  std::vector<std::uint8_t> black_;
  bool has_pending_ = false;
  bool needs_black_ = false;
  std::string last_error_;
  std::thread worker_;
};

} // namespace kinect2
