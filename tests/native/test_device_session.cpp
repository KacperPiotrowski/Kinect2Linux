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
  bool handle_open = false;
  int opened = 0;
  int closed = 0;
  kinect2::ControlResult open() override {
    ++opened;
    if (fail) return {false, "mock_failure"};
    handle_open = true;
    return {true, ""};
  }
  void close() noexcept override {
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

  assert(a.open().ok);
  assert(a.is_open() && first->handle_open && first->opened == 1);
  assert(!a.open().ok && first->opened == 1);

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
  assert(b.open().ok);
  assert(second->opened == 1);
  b.close();
  assert(flock(external, LOCK_EX | LOCK_NB) == 0);
  flock(external, LOCK_UN);
  ::close(external);

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
