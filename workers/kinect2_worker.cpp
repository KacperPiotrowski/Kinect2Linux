// Minimal supervised child executable. It cannot open Kinect USB or access
// sensor locks. Its only authority comes from an inherited private socketpair.
#include <cerrno>
#include <charconv>
#include <csignal>
#include <cstring>
#include <iostream>
#include <string_view>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <unistd.h>

namespace {
bool parse_positive(const char* text, long& result) {
  const std::string_view value(text);
  if (value.empty()) return false;
  const auto [ptr, error] =
      std::from_chars(value.data(), value.data() + value.size(), result);
  return error == std::errc{} && ptr == value.data() + value.size() &&
         result > 0;
}
bool send_reply(int fd, const char* reply) {
  const auto len = std::strlen(reply);
  return ::send(fd, reply, len, MSG_NOSIGNAL) == static_cast<ssize_t>(len);
}
} // namespace

int main(int argc, char** argv) {
  if (argc != 5 || std::string_view(argv[1]) != "--ipc-fd" ||
      std::string_view(argv[3]) != "--parent-pid") return 2;
  long socket_num = -1, parent_num = -1;
  if (!parse_positive(argv[2], socket_num) ||
      !parse_positive(argv[4], parent_num) ||
      socket_num > 4096 || parent_num > 1'000'000'000) return 2;
  const int fd = static_cast<int>(socket_num);
  const pid_t parent = static_cast<pid_t>(parent_num);

  // Exit if the spawning broker dies; prevent an orphan helper.
  if (::prctl(PR_SET_PDEATHSIG, SIGTERM) != 0 ||
      ::getppid() != parent || parent == 1) return 2;
  int type = 0;
  socklen_t len = sizeof(type);
  if (::getsockopt(fd, SOL_SOCKET, SO_TYPE, &type, &len) != 0 ||
      type != SOCK_SEQPACKET || len != sizeof(type)) return 2;
  struct ucred peer {};
  len = sizeof(peer);
  if (::getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &peer, &len) != 0 ||
      len != sizeof(peer) || peer.uid != ::geteuid() ||
      peer.pid != parent) return 2;

  bool connected = false;
  for (;;) {
    char message[32]{};
    const ssize_t received = ::recv(fd, message, sizeof(message), 0);
    if (received <= 0) break;
    const std::string_view command(message, static_cast<size_t>(received));
    if (!connected && command == "HELLO/1") {
      connected = send_reply(fd, "READY/1");
    } else if (connected && command == "PING/1") {
      if (!send_reply(fd, "PONG/1")) break;
    } else if (connected && command == "STOP/1") {
      (void)send_reply(fd, "BYE/1");
      break;
    } else {
      break; // Fail closed on unrecognized or out-of-order messages.
    }
  }
  ::close(fd);
  return 0;
}
