#include "core/device_session.hpp"

#include <cerrno>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>
#include <utility>

namespace kinect2 {

DeviceSession::DeviceSession(std::unique_ptr<HardwareDevice> device,
                             std::filesystem::path lock_path)
    : device_(std::move(device)), lock_path_(std::move(lock_path)) {}

DeviceSession::~DeviceSession() { close(); }

void DeviceSession::release_lock() noexcept {
  if (lock_fd_ >= 0) {
    flock(lock_fd_, LOCK_UN);
    ::close(lock_fd_);
    lock_fd_ = -1;
  }
}

ControlResult DeviceSession::open() {
  if (open_) return {false, "already_open"};
  if (!device_) return {false, "backend_disabled"};

  // Only accept a same-user private runtime directory. Never follow a symlink
  // for the lock file and never change permissions on somebody else's file.
  if (!lock_path_.is_absolute()) return {false, "unsafe_lock_path"};
  struct stat parent {};
  const auto dir = lock_path_.parent_path().string();
  if (::lstat(dir.c_str(), &parent) != 0 || !S_ISDIR(parent.st_mode) ||
      parent.st_uid != geteuid() || (parent.st_mode & 0077) != 0) {
    return {false, "unsafe_lock_path"};
  }

  lock_fd_ = ::open(lock_path_.c_str(),
                    O_CREAT | O_RDWR | O_CLOEXEC | O_NOFOLLOW, 0600);
  if (lock_fd_ < 0) return {false, "lock_error"};

  // Legacy CLI `flock -F` may create a 0644 file under a private 0700 dir.
  // Refuse other-user write access, but allow that cooperative lock format.
  struct stat file {};
  if (fstat(lock_fd_, &file) != 0 || !S_ISREG(file.st_mode) ||
      file.st_uid != geteuid() || (file.st_mode & 0022) != 0 ||
      file.st_nlink != 1) {
    release_lock();
    return {false, "unsafe_lock_path"};
  }
  if (flock(lock_fd_, LOCK_EX | LOCK_NB) != 0) {
    const int error = errno;
    release_lock();
    return {false, (error == EWOULDBLOCK || error == EAGAIN)
                       ? "device_busy" : "lock_error"};
  }

  ControlResult result{false, "open_failed"};
  try {
    result = device_->open();
  } catch (...) {
    result = {false, "open_failed"};
  }
  if (!result.ok) {
    device_->close();
    release_lock();
    return result;
  }
  open_ = true;
  return {true, ""};
}

ControlResult DeviceSession::start_streams(StreamSelection streams) {
  if (!open_) return {false, "device_not_open"};
  if (streaming_) return {false, "already_streaming"};
  if (!streams.rgb && !streams.ir_depth) return {false, "no_stream_selected"};
  ControlResult result{false, "start_failed"};
  try {
    result = device_->start_streams(streams);
  } catch (...) {
    result = {false, "start_failed"};
  }
  if (!result.ok) {
    // Roll back potentially partial initialization without releasing USB.
    device_->stop_streams();
    return result;
  }
  selection_ = streams;
  streaming_ = true;
  return {true, ""};
}

void DeviceSession::stop_streams() noexcept {
  if (streaming_ && device_) device_->stop_streams();
  streaming_ = false;
  selection_ = {};
}

StreamCounters DeviceSession::counters() const noexcept {
  if (!open_ || !device_) return {};
  return device_->counters();
}

void DeviceSession::close() noexcept {
  // Releasing the physical handle must precede unlocking, or an old bridge
  // could acquire the lock while libfreenect2 is still closing.
  stop_streams(); // Must join capture workers and stop streams before close.
  if (open_ && device_) device_->close();
  open_ = false;
  release_lock();
}

} // namespace kinect2
