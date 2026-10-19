#include "core/usb_disconnect_guard.hpp"

#include <cassert>

int main() {
  kinect2::UsbDisconnectGuard guard;

  // Idle and unverifiable sysfs must never trigger a restart.
  assert(!guard.lost_device(false, true, 0));
  assert(!guard.lost_device(true, false, 0));
  assert(!guard.lost_device(true, true, 0));

  // Only a *previously present* active Kinect going absent is fatal.
  assert(!guard.lost_device(true, true, 1));
  assert(!guard.lost_device(true, false, 0));
  assert(guard.lost_device(true, true, 0));
  assert(guard.lost_device(true, true, 0));

  // Returning to idle disarms the guard: hotplug at idle is normal.
  assert(!guard.lost_device(false, true, 0));
  assert(!guard.lost_device(false, true, 1));
  assert(!guard.lost_device(true, true, 0));
  assert(!guard.lost_device(true, true, 2));
  assert(!guard.lost_device(true, true, 1));
  assert(guard.lost_device(true, true, 0));
}
