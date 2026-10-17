#include "core/device_session.hpp"
#include "core/sequence_gap_tracker.hpp"

#ifdef KINECT2_WITH_LIBFREENECT2
#include <libfreenect2/libfreenect2.hpp>
#include <libfreenect2/frame_listener_impl.h>
#include <libfreenect2/packet_pipeline.h>

#include <atomic>
#include <exception>
#include <memory>
#include <thread>
#include <utility>

namespace {

// Collect only frame counts. All frame buffers remain native in libfreenect2;
// no RGB/IR/Depth bytes are delivered over IPC in this change.
class Libfreenect2Hardware final : public kinect2::HardwareDevice {
 public:
  ~Libfreenect2Hardware() override { close(); }

  kinect2::ControlResult open() override {
    if (device_) return {false, "already_open"};
    try {
      context_ = std::make_unique<libfreenect2::Freenect2>();
      if (context_->enumerateDevices() < 1) {
        close();
        return {false, "no_device"};
      }
      device_ = context_->openDevice(context_->getDefaultDeviceSerialNumber(),
                                    new libfreenect2::CpuPacketPipeline());
      if (!device_) {
        close();
        return {false, "open_failed"};
      }
      return {true, ""};
    } catch (...) {
      close();
      return {false, "open_failed"};
    }
  }

  kinect2::ControlResult start_streams(kinect2::StreamSelection streams) override {
    if (!device_) return {false, "device_not_open"};
    if (started_) return {false, "already_streaming"};
    if (!streams.rgb && !streams.ir_depth) return {false, "no_stream_selected"};
    try {
      rgb_frames_.store(0);
      ir_frames_.store(0);
      depth_frames_.store(0);
      rgb_gaps_.store(0);
      ir_gaps_.store(0);
      depth_gaps_.store(0);
      if (streams.rgb) {
        rgb_listener_ = std::make_unique<libfreenect2::SyncMultiFrameListener>(
            libfreenect2::Frame::Color);
        device_->setColorFrameListener(rgb_listener_.get());
      }
      if (streams.ir_depth) {
        ir_depth_listener_ = std::make_unique<libfreenect2::SyncMultiFrameListener>(
            libfreenect2::Frame::Ir | libfreenect2::Frame::Depth);
        device_->setIrAndDepthFrameListener(ir_depth_listener_.get());
      }
      // Single hardware session, hardware-selected RGB and/or IR+Depth.
      if (!device_->startStreams(streams.rgb, streams.ir_depth)) {
        stop_streams();
        return {false, "start_failed"};
      }
      started_ = true;
      running_.store(true);
      if (rgb_listener_) {
        rgb_worker_ = std::thread([this]() { pump(rgb_listener_.get()); });
      }
      if (ir_depth_listener_) {
        ir_depth_worker_ = std::thread([this]() { pump(ir_depth_listener_.get()); });
      }
      return {true, ""};
    } catch (...) {
      stop_streams();
      return {false, "start_failed"};
    }
  }

  void stop_streams() noexcept override {
    running_.store(false);
    if (rgb_worker_.joinable()) rgb_worker_.join();
    if (ir_depth_worker_.joinable()) ir_depth_worker_.join();
    if (device_ && (started_ || rgb_listener_ || ir_depth_listener_)) {
      try { device_->stop(); } catch (...) {}
      try {
        device_->setColorFrameListener(nullptr);
        device_->setIrAndDepthFrameListener(nullptr);
      } catch (...) {}
    }
    started_ = false;
    rgb_listener_.reset();
    ir_depth_listener_.reset();
  }

  kinect2::StreamCounters counters() const noexcept override {
    return {rgb_frames_.load(), ir_frames_.load(), depth_frames_.load(),
            rgb_gaps_.load(), ir_gaps_.load(), depth_gaps_.load()};
  }

  void close() noexcept override {
    stop_streams();
    if (device_) {
      try { device_->close(); } catch (...) {}
      device_ = nullptr;
    }
    context_.reset();
  }

 private:
  void pump(libfreenect2::SyncMultiFrameListener* listener) noexcept {
    kinect2::SequenceGapTracker rgb_sequence, ir_sequence, depth_sequence;
    while (running_.load()) {
      libfreenect2::FrameMap frames;
      try {
        if (!listener->waitForNewFrame(frames, 75)) continue;
        auto count = [&](libfreenect2::Frame::Type type,
                         std::atomic<std::uint64_t>& counter,
                         std::atomic<std::uint64_t>& gaps,
                         kinect2::SequenceGapTracker& sequence) {
          const auto it = frames.find(type);
          if (it != frames.end() && it->second) {
            ++counter;
            gaps.fetch_add(sequence.observe(it->second->sequence),
                           std::memory_order_relaxed);
          }
        };
        count(libfreenect2::Frame::Color, rgb_frames_, rgb_gaps_, rgb_sequence);
        count(libfreenect2::Frame::Ir, ir_frames_, ir_gaps_, ir_sequence);
        count(libfreenect2::Frame::Depth, depth_frames_, depth_gaps_, depth_sequence);
        listener->release(frames);
      } catch (...) {
        // Stop capture on unexpected native listener failures. Device close
        // still joins all workers before destroying listener and USB handle.
        running_.store(false);
        break;
      }
    }
  }

  std::unique_ptr<libfreenect2::Freenect2> context_;
  libfreenect2::Freenect2Device* device_ = nullptr;
  std::unique_ptr<libfreenect2::SyncMultiFrameListener> rgb_listener_;
  std::unique_ptr<libfreenect2::SyncMultiFrameListener> ir_depth_listener_;
  std::thread rgb_worker_;
  std::thread ir_depth_worker_;
  std::atomic<bool> running_{false};
  std::atomic<std::uint64_t> rgb_frames_{0};
  std::atomic<std::uint64_t> ir_frames_{0};
  std::atomic<std::uint64_t> depth_frames_{0};
  std::atomic<std::uint64_t> rgb_gaps_{0};
  std::atomic<std::uint64_t> ir_gaps_{0};
  std::atomic<std::uint64_t> depth_gaps_{0};
  bool started_ = false;
};

} // namespace
#endif

namespace kinect2 {

std::unique_ptr<HardwareDevice> make_hardware_device() {
#ifdef KINECT2_WITH_LIBFREENECT2
  return std::make_unique<Libfreenect2Hardware>();
#else
  return nullptr;
#endif
}

} // namespace kinect2
