#include "core/worker_process.hpp"

#include <cerrno>
#include <chrono>
#include <cstring>
#include <fcntl.h>
#include <poll.h>
#include <spawn.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>
#include <utility>

extern char** environ;

namespace kinect2 {
namespace {
constexpr int CHILD_SOCKET_FD = 32;

bool acceptable_executable(const std::string& path) noexcept {
  if (path.empty() || path.front() != '/') return false;
  struct stat st {};
  return ::lstat(path.c_str(), &st) == 0 && S_ISREG(st.st_mode) &&
         st.st_uid == ::geteuid() && (st.st_mode & (S_IWGRP | S_IWOTH)) == 0 &&
         (st.st_mode & (S_ISUID | S_ISGID)) == 0 &&
         ::access(path.c_str(), X_OK) == 0;
}

void wait_for_child(pid_t pid) noexcept {
  if (pid <= 0) return;
  int status = 0;
  for (int n = 0; n < 30; ++n) {
    const pid_t done = ::waitpid(pid, &status, WNOHANG);
    if (done == pid || (done < 0 && errno == ECHILD)) return;
    if (done < 0 && errno != EINTR) return;
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  // Avoid killing a recycled PID: check that this is still our child.
  const pid_t check = ::waitpid(pid, &status, WNOHANG);
  if (check == pid || (check < 0 && errno == ECHILD)) return;
  if (check != 0) return;
  ::kill(pid, SIGTERM);
  for (int n = 0; n < 30; ++n) {
    const pid_t done = ::waitpid(pid, &status, WNOHANG);
    if (done == pid || (done < 0 && errno == ECHILD)) return;
    if (done < 0 && errno != EINTR) return;
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  const pid_t check_again = ::waitpid(pid, &status, WNOHANG);
  if (check_again == 0) {
    ::kill(pid, SIGKILL);
    while (::waitpid(pid, &status, 0) < 0 && errno == EINTR) {}
  }
}
} // namespace

WorkerProcess::~WorkerProcess() { stop(); }

bool WorkerProcess::exchange(const char* request, const char* expected) noexcept {
  if (fd_ < 0 || pid_ <= 0) return false;
  const auto len = std::strlen(request);
  if (::send(fd_, request, len, MSG_NOSIGNAL | MSG_DONTWAIT) !=
      static_cast<ssize_t>(len)) return false;
  pollfd pfd{fd_, POLLIN, 0};
  int ready = 0;
  do {
    ready = ::poll(&pfd, 1, 500);
  } while (ready < 0 && errno == EINTR);
  if (ready <= 0 || !(pfd.revents & POLLIN)) return false;
  char reply[32]{};
  const ssize_t n = ::recv(fd_, reply, sizeof(reply), MSG_DONTWAIT);
  return n == static_cast<ssize_t>(std::strlen(expected)) &&
         std::memcmp(reply, expected, static_cast<size_t>(n)) == 0;
}

bool WorkerProcess::start(const std::string& executable) noexcept {
  if (pid_ > 0 || fd_ >= 0 || !acceptable_executable(executable)) return false;
  int ends[2]{-1, -1};
  if (::socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, ends) < 0)
    return false;
  // Reserve the fixed descriptor in the spawned child without accidentally
  // closing it in file actions if one of socketpair's ends was originally 32.
  for (auto& end : ends) {
    if (end == CHILD_SOCKET_FD) {
      const int moved = ::fcntl(end, F_DUPFD_CLOEXEC, CHILD_SOCKET_FD + 1);
      if (moved < 0) {
        ::close(ends[0]);
        ::close(ends[1]);
        return false;
      }
      ::close(end);
      end = moved;
    }
  }
  posix_spawn_file_actions_t actions {};
  if (::posix_spawn_file_actions_init(&actions) != 0) {
    ::close(ends[0]); ::close(ends[1]);
    return false;
  }
  const int a = ::posix_spawn_file_actions_adddup2(&actions, ends[1], CHILD_SOCKET_FD);
  const int b = ::posix_spawn_file_actions_addclose(&actions, ends[0]);
  const int c = ::posix_spawn_file_actions_addclose(&actions, ends[1]);
  const std::string fdarg = std::to_string(CHILD_SOCKET_FD);
  const std::string ppidarg = std::to_string(::getpid());
  char* argv[] = {const_cast<char*>(executable.c_str()),
                  const_cast<char*>("--ipc-fd"),
                  const_cast<char*>(fdarg.c_str()),
                  const_cast<char*>("--parent-pid"),
                  const_cast<char*>(ppidarg.c_str()),
                  nullptr};
  pid_t child = -1;
  const int result = (a == 0 && b == 0 && c == 0)
      ? ::posix_spawn(&child, executable.c_str(), &actions, nullptr, argv, environ)
      : EINVAL;
  ::posix_spawn_file_actions_destroy(&actions);
  ::close(ends[1]);
  if (result != 0 || child <= 0) {
    ::close(ends[0]);
    return false;
  }
  fd_ = ends[0];
  pid_ = child;
  if (!exchange("HELLO/1", "READY/1")) {
    stop();
    return false;
  }
  return true;
}

bool WorkerProcess::ping() noexcept {
  return exchange("PING/1", "PONG/1");
}

void WorkerProcess::stop() noexcept {
  if (fd_ >= 0) {
    (void)exchange("STOP/1", "BYE/1");
    ::close(fd_);
    fd_ = -1;
  }
  const pid_t child = std::exchange(pid_, -1);
  wait_for_child(child);
}

} // namespace kinect2
