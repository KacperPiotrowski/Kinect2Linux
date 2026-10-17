#pragma once

#include <cstdint>
#include <filesystem>
#include <memory>
#include <string>

namespace kinect2 {

class FrameSink;

struct ControlResult {
  bool ok;
  std::string code;
};

// Start modes are independent at the API boundary. IR and Depth must be
// acquired together when either one is requested from libfreenect2.
struct StreamSelection {
  bool rgb = false;
  bool ir_depth = false;
};

struct StreamCounters {
  std::uint64_t rgb_frames = 0;
  std::uint64_t ir_frames = 0;
  std::uint64_t depth_frames = 0;
  // Gaps in sequence numbers among frames actually delivered by libfreenect2.
  // These are diagnostics, not a complete accounting of USB/decoder losses.
  std::uint64_t rgb_seq_gaps = 0;
  std::uint64_t ir_seq_gaps = 0;
  std::uint64_t depth_seq_gaps = 0;
};

class HardwareDevice {
 public:
  virtual ~HardwareDevice() = default;
  virtual ControlResult open() = 0;
  virtual void close() noexcept = 0;
  virtual ControlResult start_streams(StreamSelection streams) = 0;
  virtual void stop_streams() noexcept = 0;
  virtual StreamCounters counters() const noexcept = 0;
  // Optional, controlled by broker; fake backends remain unchanged.
  virtual void set_frame_sink(FrameSink*) noexcept {}

};

// nullptr in the hardware-free build, even if CLI opt-in is requested.
std::unique_ptr<HardwareDevice> make_hardware_device();

// Exactly one USB owner. Lock is retained through start/stop until close().
// This is NOT yet a subscription API: no image buffers leave the process.
class DeviceSession final {
 public:
  DeviceSession(std::unique_ptr<HardwareDevice> device, std::filesystem::path lock_path);
  ~DeviceSession();
  DeviceSession(const DeviceSession&) = delete;
  DeviceSession& operator=(const DeviceSession&) = delete;

  ControlResult open();
  ControlResult start_streams(StreamSelection streams);
  void stop_streams() noexcept;
  void close() noexcept;

  [[nodiscard]] bool is_open() const noexcept { return open_; }
  [[nodiscard]] bool is_streaming() const noexcept { return streaming_; }
  [[nodiscard]] StreamSelection selection() const noexcept { return selection_; }
  [[nodiscard]] StreamCounters counters() const noexcept;
  void set_frame_sink(FrameSink* sink) noexcept { if (device_) device_->set_frame_sink(sink); }


 private:
  void release_lock() noexcept;
  std::unique_ptr<HardwareDevice> device_;
  std::filesystem::path lock_path_;
  int lock_fd_ = -1;
  bool open_ = false;
  bool streaming_ = false;
  StreamSelection selection_{};
};

} // namespace kinect2
