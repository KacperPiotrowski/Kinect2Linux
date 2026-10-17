#include "core/worker_process.hpp"

#include <cassert>
#include <cerrno>
#include <csignal>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <sys/wait.h>
#include <unistd.h>

int main(int argc, char** argv) {
  assert(argc == 2);
  const std::string executable(argv[1]);
  assert(std::filesystem::path(executable).is_absolute());

  kinect2::WorkerProcess supervisor;
  assert(!supervisor.start("/missing/kinect2-worker"));
  assert(supervisor.pid() == -1);
  assert(supervisor.start(executable));
  const pid_t first = supervisor.pid();
  assert(first > 0 && first != ::getpid());
  assert(supervisor.ping());
  assert(supervisor.ping());
  supervisor.stop();
  assert(supervisor.pid() == -1);
  int status = 0;
  assert(::waitpid(first, &status, WNOHANG) == -1 && errno == ECHILD);

  // Repeat start/stop: no process leaks and no lingering parent socket.
  assert(supervisor.start(executable));
  assert(supervisor.ping());
  supervisor.stop();
  supervisor.stop();

  // An unexpectedly killed child must not kill the parent.
  assert(supervisor.start(executable));
  const pid_t killed = supervisor.pid();
  assert(::kill(killed, SIGKILL) == 0);
  assert(!supervisor.ping());
  supervisor.stop();
  assert(supervisor.pid() == -1);
  assert(::waitpid(killed, &status, WNOHANG) == -1 && errno == ECHILD);

  // Explicit executable path required; no PATH lookup / arbitrary commands.
  assert(!supervisor.start("kinect2-worker"));
  assert(!supervisor.start("/bin/sh")); // Not owned by running user.
  return 0;
}
