#pragma once
// v4l2loopback client usage events. Ubuntu Noble backported this feature to
// 0.12.x under a different private ID; negotiate capability, not version.
// See: https://bugs.launchpad.net/ubuntu/+source/v4l2loopback/+bug/2078947
#include <cerrno>
#include <cstdint>
#include <linux/videodev2.h>
#include <sys/ioctl.h>

namespace kinect2 {
constexpr std::uint32_t kUsageEventUpstream =
    V4L2_EVENT_PRIVATE_START + 0x08E00000u + 1u;
constexpr std::uint32_t kUsageEventUbuntuLegacy =
    V4L2_EVENT_PRIVATE_START + 1u;

struct UsageSubscription {
  std::uint32_t type = 0; // Zero = neither supported
  int upstream_error = 0;
  int ubuntu_error = 0;
};

// The callable is injectable for hardware-free regression tests.
template <class TrySubscribe>
UsageSubscription select_usage_event(TrySubscribe try_subscribe) noexcept {
  UsageSubscription result;
  if (try_subscribe(kUsageEventUpstream)) {
    result.type = kUsageEventUpstream;
    return result;
  }
  result.upstream_error = errno;
  if (try_subscribe(kUsageEventUbuntuLegacy)) {
    result.type = kUsageEventUbuntuLegacy;
    return result;
  }
  result.ubuntu_error = errno;
  return result;
}

inline UsageSubscription subscribe_usage_event(int fd) noexcept {
  return select_usage_event([fd](std::uint32_t id) {
    v4l2_event_subscription sub{};
    sub.type = id;
    sub.flags = V4L2_EVENT_SUB_FL_SEND_INITIAL;
    return ::ioctl(fd, VIDIOC_SUBSCRIBE_EVENT, &sub) == 0;
  });
}
} // namespace kinect2
