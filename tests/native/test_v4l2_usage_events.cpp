#include "core/v4l2_usage_events.hpp"
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <vector>

int main() {
  using namespace kinect2;
  std::vector<std::uint32_t> calls;
  const auto upstream = select_usage_event([&](std::uint32_t id) {
    calls.push_back(id);
    return id == kUsageEventUpstream;
  });
  assert(upstream.type == kUsageEventUpstream);
  assert(calls.size() == 1);

  calls.clear();
  const auto ubuntu = select_usage_event([&](std::uint32_t id) {
    calls.push_back(id);
    if (id == kUsageEventUpstream) {
      errno = EINVAL;
      return false;
    }
    return id == kUsageEventUbuntuLegacy;
  });
  assert(ubuntu.type == kUsageEventUbuntuLegacy);
  assert(ubuntu.upstream_error == EINVAL);
  assert(calls.size() == 2);

  calls.clear();
  const auto unsupported = select_usage_event([&](std::uint32_t id) {
    calls.push_back(id);
    errno = ENOTTY;
    return false;
  });
  assert(unsupported.type == 0);
  assert(unsupported.upstream_error == ENOTTY);
  assert(unsupported.ubuntu_error == ENOTTY);
  assert(calls.size() == 2);
}
