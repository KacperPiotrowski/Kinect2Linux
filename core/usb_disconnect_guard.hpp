#pragma once

#include <cstddef>

namespace kinect2 {

// A native libusb handle becomes unusable after physical disconnection,
// even when the Kinect later re-enumerates on the same USB port.
// Only fail fast if the sensor was previously confirmed present while active.
class UsbDisconnectGuard final {
 public:
  [[nodiscard]] bool lost_device(bool streaming, bool scan_ok,
                                 std::size_t devices) noexcept {
    if (!streaming) {
      observed_present_ = false;
      return false;
    }
    if (!scan_ok) return false;  // Sysfs scan failure is not proof of unplug.
    if (devices != 0) {
      observed_present_ = true;
      return false;
    }
    return observed_present_;
  }

 private:
  bool observed_present_ = false;
};

} // namespace kinect2
