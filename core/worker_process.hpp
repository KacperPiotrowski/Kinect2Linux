#pragma once

#include <sys/types.h>
#include <string>

namespace kinect2 {

// A broker-owned, non-USB helper. Created via posix_spawn() (no fork of C++
// capture threads), supervised and reaped by the broker itself. This is an
// experimental opt-in child, NOT a dynamic module or sensor owner.
class WorkerProcess final {
 public:
  WorkerProcess() = default;
  ~WorkerProcess();
  WorkerProcess(const WorkerProcess&) = delete;
  WorkerProcess& operator=(const WorkerProcess&) = delete;

  // Refuses untrusted or group/world-writable executable files.
  bool start(const std::string& executable) noexcept;
  bool ping() noexcept;
  void stop() noexcept;

  [[nodiscard]] pid_t pid() const noexcept { return pid_; }

 private:
  bool exchange(const char* request, const char* expected) noexcept;
  int fd_ = -1;
  pid_t pid_ = -1;
};

} // namespace kinect2
