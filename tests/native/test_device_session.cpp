#include "core/device_session.hpp"

#include <cassert>
#include <cstdlib>
#include <fcntl.h>
#include <filesystem>
#include <fstream>
#include <memory>
#include <string>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

namespace fs = std::filesystem;

struct TempDir {
  fs::path path;
  TempDir() {
    auto name = (fs::temp_directory_path() / "kinect-session-XXXXXX").string();
    char* created = mkdtemp(name.data());
    assert(created);
    path = created;
  }
  ~TempDir() { std::error_code ec; fs::remove_all(path, ec); }
};

struct FakeHardware final : kinect2::HardwareDevice {
  bool fail = false;
  bool fail_start = false;
  bool handle_open = false;
  bool started = false;
  int opened = 0;
  int closed = 0;
  int start_calls = 0;
  int stop_calls = 0;
  kinect2::StreamSelection selected{};
  kinect2::ControlResult open() override {
    ++opened;
    if (fail) return {false, "mock_failure"};
    handle_open = true;
    return {true, ""};
  }
  kinect2::ControlResult start_streams(kinect2::StreamSelection requested) override {
    ++start_calls;
    if (fail_start) return {false, "mock_start_failed"};
    selected = requested;
    started = true;
    return {true, ""};
  }
  void stop_streams() noexcept override {
    ++stop_calls;
    started = false;
  }
  kinect2::StreamCounters counters() const noexcept override {
    return selected.rgb ? kinect2::StreamCounters{12, 0, 0} :
                          kinect2::StreamCounters{0, 17, 17};
  }
  void close() noexcept override {
    assert(!started); // Must stop workers BEFORE releasing USB.
    ++closed;
    handle_open = false;
  }
};

int main() {
  TempDir tmp;
  const fs::path lock = tmp.path / "kinect2-sensor.lock";
  auto first_mock = std::make_unique<FakeHardware>();
  auto* first = first_mock.get();
  kinect2::DeviceSession a(std::move(first_mock), lock);
  assert(!a.is_open());
  assert(a.start_streams({true, false}).code == "device_not_open");
  assert(a.counters().rgb_frames == 0);

  assert(a.open().ok);
  assert(a.is_open() && first->handle_open && first->opened == 1);
  assert(!a.open().ok && first->opened == 1);
  assert(a.start_streams({}).code == "no_stream_selected");
  assert(a.start_streams({true, false}).ok);
  assert(a.is_streaming() && first->started);
  assert(a.selection().rgb && !a.selection().ir_depth);
  assert(a.counters().rgb_frames == 12);
  assert(a.start_streams({false, true}).code == "already_streaming");
  assert(first->start_calls == 1);
  a.stop_streams();
  assert(!a.is_streaming() && !first->started);
  assert(!a.selection().rgb && !a.selection().ir_depth);
  // Stopping doesn't close USB; switching capture modes is explicit.
  assert(a.is_open());
  assert(a.start_streams({false, true}).ok);
  assert(a.selection().ir_depth && a.counters().depth_frames == 17);
  a.stop_streams();
  assert(a.start_streams({true, true}).ok);
  assert(a.selection().rgb && a.selection().ir_depth);
  // close() must stop streams before closing USB.

  // Other processes and existing bridges use the same advisory flock.
  const int external = ::open(lock.c_str(), O_RDWR | O_CLOEXEC);
  assert(external >= 0);
  assert(flock(external, LOCK_EX | LOCK_NB) != 0);

  auto second_mock = std::make_unique<FakeHardware>();
  auto* second = second_mock.get();
  kinect2::DeviceSession b(std::move(second_mock), lock);
  const auto busy = b.open();
  assert(!busy.ok && busy.code == "device_busy" && second->opened == 0);

  a.close();
  assert(!a.is_open() && !first->handle_open && first->closed == 1);
  assert(!a.is_streaming() && !first->started && first->stop_calls >= 3);
  assert(b.open().ok);
  assert(second->opened == 1);
  b.close();
  assert(flock(external, LOCK_EX | LOCK_NB) == 0);
  flock(external, LOCK_UN);
  ::close(external);

  // Legacy ./kinect2 run/depth uses `flock -F`, which often creates a 0644 lock.
  assert(::chmod(lock.c_str(), 0644) == 0);
  assert(a.open().ok);
  a.close();
  assert(::chmod(lock.c_str(), 0600) == 0);

  // Device-open errors must release the advisory lock.
  auto failing_mock = std::make_unique<FakeHardware>();
  auto* failing = failing_mock.get();
  failing->fail = true;
  kinect2::DeviceSession failing_session(std::move(failing_mock), lock);
  auto failure = failing_session.open();
  assert(!failure.ok && failure.code == "mock_failure");
  assert(!failing_session.is_open() && failing->closed == 1);
  assert(a.open().ok);
  a.close();

  // A failed start must be rolled back, and a later attempt may succeed.
  auto start_mock = std::make_unique<FakeHardware>();
  auto* start_failure = start_mock.get();
  kinect2::DeviceSession retry(std::move(start_mock), lock);
  assert(retry.open().ok);
  start_failure->fail_start = true;
  assert(retry.start_streams({true, false}).code == "mock_start_failed");
  assert(!retry.is_streaming() && retry.is_open());
  assert(start_failure->stop_calls > 0);
  start_failure->fail_start = false;
  assert(retry.start_streams({false, true}).ok);
  retry.close();
  assert(!start_failure->started);

  // Destruction closes open handles and releases the lock.
  {
    auto mock = std::make_unique<FakeHardware>();
    kinect2::DeviceSession scoped(std::move(mock), lock);
    assert(scoped.open().ok);
  }
  assert(a.open().ok);
  a.close();

  // A symlink may never be used as the lock file.
  const fs::path victim = tmp.path / "other";
  std::ofstream(victim) << "leave unchanged";
  fs::remove(lock);
  fs::create_symlink(victim, lock);
  const auto unsafe = a.open();
  assert(!unsafe.ok);
  assert(!a.is_open());
  assert(fs::file_size(victim) == 15);
  fs::remove(lock);

  // Public directories must be rejected (no USB attempt).
  fs::permissions(tmp.path, fs::perms::owner_all | fs::perms::group_read,
                  fs::perm_options::replace);
  const auto public_path = a.open();
  assert(!public_path.ok && public_path.code == "unsafe_lock_path");
  assert(!a.is_open());
  fs::permissions(tmp.path, fs::perms::owner_all, fs::perm_options::replace);

  kinect2::DeviceSession disabled(nullptr, lock);
  const auto no_backend = disabled.open();
  assert(!no_backend.ok && no_backend.code == "backend_disabled");
}
