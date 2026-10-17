#include "core/auto_capture.hpp"

#include <cassert>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

namespace {
class FakeDevice : public kinect2::HardwareDevice {
 public:
  int opens = 0, closes = 0, starts = 0, stops = 0;
  bool fail_open = false, fail_start = false;
  std::vector<kinect2::StreamSelection> modes;

  kinect2::ControlResult open() override {
    ++opens;
    return fail_open ? kinect2::ControlResult{false, "fake_open_error"} :
                       kinect2::ControlResult{true, ""};
  }
  void close() noexcept override { ++closes; }
  kinect2::ControlResult start_streams(kinect2::StreamSelection selected) override {
    ++starts;
    modes.push_back(selected);
    return fail_start ? kinect2::ControlResult{false, "fake_start_error"} :
                        kinect2::ControlResult{true, ""};
  }
  void stop_streams() noexcept override { ++stops; }
  kinect2::StreamCounters counters() const noexcept override { return {}; }
};
} // namespace

int main() {
  char dir[] = "/tmp/kinect2-auto-XXXXXX";
  assert(::mkdtemp(dir));
  assert(::chmod(dir, 0700) == 0);
  const std::filesystem::path lock = std::string(dir) + "/sensor.lock";
  {
    auto device = std::make_unique<FakeDevice>();
    FakeDevice* fake = device.get();
    kinect2::DeviceSession session(std::move(device), lock);
    kinect2::AutoCapture auto_capture(session);

    auto_capture.reconcile({}); // idle broker must never open USB
    assert(!session.is_open() && fake->opens == 0);

    auto_capture.reconcile({2, 0, 0});  // two independent RGB clients
    assert(session.is_streaming() && session.selection().rgb);
    assert(!session.selection().ir_depth && fake->starts == 1);
    auto_capture.reconcile({1, 0, 0});  // closing one viewer does not stop RGB
    assert(session.is_streaming() && fake->starts == 1 && fake->stops == 0);

    auto_capture.reconcile({1, 1, 0});  // add IR -> physical IR+Depth group
    assert(session.is_streaming() && session.selection().rgb &&
           session.selection().ir_depth);
    assert(fake->starts == 2 && fake->stops == 1);

    auto_capture.reconcile({1, 0, 1});  // switch IR -> Depth, no restart
    assert(session.is_streaming() && fake->starts == 2);
    auto_capture.reconcile({0, 0, 1});  // RGB leaves, Depth remains
    assert(session.is_streaming() && !session.selection().rgb &&
           session.selection().ir_depth && fake->starts == 3);
    auto_capture.reconcile({});         // final Depth leaves -> release USB
    assert(!session.is_open() && !session.is_streaming());
    assert(fake->closes == 1);
    assert(fake->stops == 3);

    fake->fail_open = true;
    auto_capture.reconcile({0, 1, 0});
    assert(!session.is_open() && auto_capture.last_error() == "fake_open_error");
    const int open_count = fake->opens;
    auto_capture.reconcile({0, 1, 0}); // no busy retry storms
    assert(fake->opens == open_count);
    auto_capture.reconcile({}); // zero clients resets cooldown
    assert(auto_capture.last_error().empty());
    fake->fail_open = false;
    fake->fail_start = true;
    auto_capture.reconcile({0, 1, 0});
    assert(!session.is_open() && auto_capture.last_error() == "fake_start_error");
    auto_capture.reconcile({});
    fake->fail_start = false;
    auto_capture.reconcile({0, 1, 0});
    assert(session.is_streaming() && session.selection().ir_depth);
    auto_capture.reconcile({});
  }
  std::filesystem::remove(lock);
  std::filesystem::remove(dir);
}
