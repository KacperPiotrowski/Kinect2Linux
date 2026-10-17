#pragma once

#include "core/device_session.hpp"
#include "core/frame_hub.hpp"
#include <chrono>
#include <string>

namespace kinect2 {

// Opt-in: a single broker owns USB and reconciles native capture against
// connected read-only frame subscribers. All calls occur on the broker
// control thread. Capture and FrameHub never call into DeviceSession.
class AutoCapture final {
 public:
  explicit AutoCapture(DeviceSession& session) noexcept : session_(session) {}

  // May perform slow USB work: never call on FrameHub's accept/capture threads.
  void reconcile(SubscriptionCounts subscribers) noexcept;

  [[nodiscard]] const std::string& last_error() const noexcept { return last_error_; }

 private:
  void failed(std::string error) noexcept;
  DeviceSession& session_;
  std::string last_error_;
  std::chrono::steady_clock::time_point retry_after_{};
};

} // namespace kinect2
