#include "core/frame_sink_fanout.hpp"
#include "core/v4l2_rgb_output.hpp"

#include <array>
#include <cassert>
#include <cstdint>
#include <vector>

namespace {
class CountingSink final : public kinect2::FrameSink {
 public:
  int rgb = 0, ir = 0, depth = 0;
  void publish(kinect2::FrameKind kind, const std::uint8_t*,
               std::uint32_t, std::uint32_t,
               std::uint32_t, std::uint32_t) noexcept override {
    if (kind == kinect2::FrameKind::rgb) ++rgb;
    if (kind == kinect2::FrameKind::ir) ++ir;
    if (kind == kinect2::FrameKind::depth) ++depth;
  }
};
}

int main() {
  // BGRX black => studio-range YUYV black (16 128 16 128).
  {
    const std::array<std::uint8_t, 8> in{};
    std::array<std::uint8_t, 4> out{};
    assert(kinect2::bgrx_to_yuyv(in.data(), in.size(), out.data(),
                                 out.size(), 2, 1, 8));
    assert((out == std::array<std::uint8_t, 4>{16, 128, 16, 128}));
  }
  // BGRX white -> studio range Y=235, U/V=128.
  {
    const std::array<std::uint8_t, 8> in{
        255, 255, 255, 1, 255, 255, 255, 2};
    std::array<std::uint8_t, 4> out{};
    assert(kinect2::bgrx_to_yuyv(in.data(), in.size(), out.data(),
                                 out.size(), 2, 1, 8));
    assert((out == std::array<std::uint8_t, 4>{235, 128, 235, 128}));
  }
  // BGRX red and blue have distinct expected luminance, shared chroma.
  {
    const std::array<std::uint8_t, 8> in{0, 0, 255, 0, 255, 0, 0, 0};
    std::array<std::uint8_t, 4> out{};
    assert(kinect2::bgrx_to_yuyv(in.data(), in.size(), out.data(),
                                 out.size(), 2, 1, 8));
    assert(out[0] == 82 && out[2] == 41);
    assert(out[1] != 128 && out[3] != 128);
  }
  // Ignore 4-byte padding at the end of each input row.
  {
    const std::array<std::uint8_t, 24> in{
        0,0,0,0, 0,0,0,0, 255,255,255,0,
        0,0,0,0, 0,0,0,0, 255,255,255,0};
    std::array<std::uint8_t, 8> out{};
    assert(kinect2::bgrx_to_yuyv(in.data(), in.size(), out.data(),
                                 out.size(), 2, 2, 12));
    assert((out == std::array<std::uint8_t, 8>{
        16,128,16,128,16,128,16,128})); // second row ignored content?
  }
  // Strict rejection of too-small buffers, odd width and unsupported shape.
  {
    std::array<std::uint8_t, 8> in{};
    std::array<std::uint8_t, 4> out{};
    assert(!kinect2::bgrx_to_yuyv(in.data(), 4, out.data(), 4, 2, 1, 8));
    assert(!kinect2::bgrx_to_yuyv(in.data(), 8, out.data(), 2, 2, 1, 8));
    assert(!kinect2::bgrx_to_yuyv(in.data(), 8, out.data(), 4, 1, 1, 4));
    assert(!kinect2::bgrx_to_yuyv(in.data(), 8, out.data(), 4, 2, 1, 7));
    assert(!kinect2::bgrx_to_yuyv(nullptr, 8, out.data(), 4, 2, 1, 8));
  }
  // RGB is duplicated to the in-process webcam; IR/Depth to SDK only.
  {
    CountingSink sdk, webcam;
    kinect2::FrameFanout sink(sdk, &webcam);
    const std::uint8_t data[4]{};
    sink.publish(kinect2::FrameKind::rgb, data, 1920, 1080, 4, 1);
    sink.publish(kinect2::FrameKind::ir, data, 512, 424, 4, 2);
    sink.publish(kinect2::FrameKind::depth, data, 512, 424, 4, 3);
    assert(sdk.rgb == 1 && sdk.ir == 1 && sdk.depth == 1);
    assert(webcam.rgb == 1 && webcam.ir == 0 && webcam.depth == 0);
  }
}
