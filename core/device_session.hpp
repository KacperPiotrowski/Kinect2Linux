#pragma once

#include <filesystem>
#include <memory>
#include <string>

namespace kinect2 {

struct ControlResult {
  bool ok;
  std::string code; // Empty on success; stable machine-readable error otherwise.
};

// Minimal boundary to libfreenect2, replaceable with an offline fake.
class HardwareDevice {
 public:
  virtual ~HardwareDevice() = default;
  virtual ControlResult open() = 0;
  virtual void close() noexcept = 0; // May be called after failed open.
};

// nullptr means this broker was built without native Kinect support.
std::unique_ptr<HardwareDevice> make_hardware_device();

// Holds the SAME flock file used by existing RGB/IR/Depth bridges for as long
// as a physical device handle is open. Deliberately owns no video streams yet.
class DeviceSession final {
 public:
  DeviceSession(std::unique_ptr<HardwareDevice> device, std::filesystem::path lock_path);
  ~DeviceSession();

  DeviceSession(const DeviceSession&) = delete;
  DeviceSession& operator=(const DeviceSession&) = delete;

  ControlResult open();
  void close() noexcept;
  [[nodiscard]] bool is_open() const noexcept { return open_; }

 private:
  void release_lock() noexcept;
  std::unique_ptr<HardwareDevice> device_;
  std::filesystem::path lock_path_;
  int lock_fd_ = -1;
  bool open_ = false;
};

} // namespace kinect2
