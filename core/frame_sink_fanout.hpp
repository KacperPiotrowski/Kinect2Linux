#pragma once
#include "core/frame_hub.hpp"

namespace kinect2 {

// A single native USB pump sends each frame to SDK subscribers and to the
// optional in-process V4L2 RGB producer. Both sinks are nonblocking to USB
// (bounded per-stream frame handling); neither opens a second Kinect.
class FrameFanout final : public FrameSink {
 public:
  FrameFanout(FrameSink& sdk, FrameSink* v4l2) noexcept
      : sdk_(sdk), v4l2_(v4l2) {}

  void publish(FrameKind kind, const std::uint8_t* data,
               std::uint32_t width, std::uint32_t height,
               std::uint32_t bpp, std::uint32_t sequence) noexcept override {
    sdk_.publish(kind, data, width, height, bpp, sequence);
    if (v4l2_ && kind == FrameKind::rgb)
      v4l2_->publish(kind, data, width, height, bpp, sequence);
  }

 private:
  FrameSink& sdk_;
  FrameSink* v4l2_;
};
} // namespace kinect2
