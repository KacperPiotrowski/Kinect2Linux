#pragma once

#include <filesystem>
#include <string>
#include <vector>

namespace kinect2 {

// USB enumeration only: no device nodes are opened or claimed.
struct SensorInfo {
  std::string sysfs_name;  // USB sysfs directory name, never a device serial.
};

struct DiscoveryResult {
  bool scan_ok = false;  // Whether the sysfs directory could be enumerated.
  std::vector<SensorInfo> devices;
};

class SensorBackend {
 public:
  virtual ~SensorBackend() = default;
  virtual DiscoveryResult discover() const = 0;
};

class SysfsSensorBackend final : public SensorBackend {
 public:
  explicit SysfsSensorBackend(
      std::filesystem::path root = "/sys/bus/usb/devices");
  DiscoveryResult discover() const override;

 private:
  std::filesystem::path root_;
};

}  // namespace kinect2
