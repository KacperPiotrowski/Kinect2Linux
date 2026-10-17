#include "core/sequence_gap_tracker.hpp"

#include <cassert>
#include <cstdint>
#include <limits>

int main() {
  kinect2::SequenceGapTracker t;
  assert(t.observe(7) == 0);
  assert(t.observe(8) == 0);
  assert(t.observe(11) == 2);
  assert(t.observe(11) == 0); // duplicate
  assert(t.observe(13) == 1);
  assert(t.observe(5) == 0); // unexpected backwards/reset; do not inflate gaps
  assert(t.observe(6) == 0);

  kinect2::SequenceGapTracker wrap;
  assert(wrap.observe(std::numeric_limits<std::uint32_t>::max() - 1) == 0);
  assert(wrap.observe(1) == 2); // gap over wrap: max, 0
  assert(wrap.observe(2) == 0);

  kinect2::SequenceGapTracker restarted;
  assert(restarted.observe(500) == 0);
  assert(restarted.observe(60001) == 0); // implausibly large reset
  assert(restarted.observe(60002) == 0);
}
