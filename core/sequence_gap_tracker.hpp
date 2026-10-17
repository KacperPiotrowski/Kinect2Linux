#pragma once

#include <cstdint>

namespace kinect2 {

// Counts missing sequence numbers among delivered frames, not USB packet loss.
// Wraparound uint32_t is supported; large discontinuities are treated as resets.
class SequenceGapTracker {
 public:
  std::uint64_t observe(std::uint32_t sequence) noexcept {
    if (!have_previous_) {
      have_previous_ = true;
      previous_ = sequence;
      return 0;
    }
    const std::uint32_t delta = sequence - previous_;
    previous_ = sequence;
    if (delta <= 1 || delta > 10000) return 0;
    return static_cast<std::uint64_t>(delta - 1);
  }

 private:
  bool have_previous_ = false;
  std::uint32_t previous_ = 0;
};

} // namespace kinect2
