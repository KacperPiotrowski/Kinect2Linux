#include "core/frame_hub.hpp"

#include <arpa/inet.h>
#include <array>
#include <cassert>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <filesystem>
#include <string>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

namespace {
int subscribe(const std::string& path, char stream) {
  const int fd = ::socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
  assert(fd >= 0);
  timeval timeout{2, 0};
  assert(::setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) == 0);
  sockaddr_un address{};
  address.sun_family = AF_UNIX;
  std::memcpy(address.sun_path, path.c_str(), path.size() + 1);
  assert(::connect(fd, reinterpret_cast<sockaddr*>(&address), sizeof(address)) == 0);
  assert(::send(fd, &stream, 1, MSG_NOSIGNAL) == 1);
  char answer{};
  assert(::recv(fd, &answer, 1, 0) == 1 && answer == 'K');
  return fd;
}
void verify(int sock, int expected_kind, unsigned expected_seq,
            const std::array<std::uint8_t, 16>& pixels) {
  char payload[32]{};
  char control[CMSG_SPACE(sizeof(int))]{};
  iovec iov{payload, sizeof(payload)};
  msghdr msg{};
  msg.msg_iov = &iov;
  msg.msg_iovlen = 1;
  msg.msg_control = control;
  msg.msg_controllen = sizeof(control);
  assert(::recvmsg(sock, &msg, 0) == 32);
  assert(std::memcmp(payload, "K2F1", 4) == 0);
  assert(static_cast<unsigned char>(payload[4]) == expected_kind);
  assert(static_cast<unsigned char>(payload[5]) == 4);
  std::uint32_t network_seq{}, network_size{};
  std::memcpy(&network_size, payload + 16, sizeof(network_size));
  std::memcpy(&network_seq, payload + 20, sizeof(network_seq));
  assert(ntohl(network_size) == pixels.size());
  assert(ntohl(network_seq) == expected_seq);
  cmsghdr* cmsg = CMSG_FIRSTHDR(&msg);
  assert(cmsg && cmsg->cmsg_level == SOL_SOCKET && cmsg->cmsg_type == SCM_RIGHTS);
  int received = -1;
  std::memcpy(&received, CMSG_DATA(cmsg), sizeof(received));
  assert(received >= 0);
  std::array<std::uint8_t, 16> copy{};
  assert(::pread(received, copy.data(), copy.size(), 0) ==
         static_cast<ssize_t>(copy.size()));
  assert(copy == pixels);
  const int seals = ::fcntl(received, F_GET_SEALS);
  assert(seals >= 0 && (seals & F_SEAL_WRITE));
  ::close(received);
}
} // namespace

int main() {
  char dir[] = "/tmp/kinect2-framehub-XXXXXX";
  assert(::mkdtemp(dir) != nullptr);
  assert(::chmod(dir, 0700) == 0);
  const std::string path = std::string(dir) + "/frames.sock";
  kinect2::FrameHub hub;
  assert(hub.start(path));
  const int rgb1 = subscribe(path, 'R');
  const int rgb2 = subscribe(path, 'R');
  const int ir1 = subscribe(path, 'I');
  const int ir2 = subscribe(path, 'I');
  assert(hub.subscriber_count() == 4);
  auto subscribed = hub.subscriptions();
  assert(subscribed.rgb == 2 && subscribed.ir == 2 &&
         subscribed.depth == 0 && subscribed.total() == 4);
  const std::array<std::uint8_t, 16> bytes{1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16};
  hub.publish(kinect2::FrameKind::rgb, bytes.data(), 2, 2, 4, 123);
  hub.publish(kinect2::FrameKind::ir, bytes.data(), 2, 2, 4, 124);
  verify(rgb1, 1, 123, bytes);
  verify(rgb2, 1, 123, bytes);
  verify(ir1, 2, 124, bytes);
  verify(ir2, 2, 124, bytes);
  // If the last viewer closes during a sensor pause, the broker needs to
  // learn about it without waiting for the next FrameHub::publish().
  ::close(rgb1);
  for (int i = 0; i < 50 && hub.subscriptions().rgb != 1; ++i) {
    hub.reap_disconnected();
    ::usleep(2000);
  }
  subscribed = hub.subscriptions();
  assert(subscribed.rgb == 1 && subscribed.ir == 2);
  ::close(rgb2); ::close(ir1); ::close(ir2);
  for (int i = 0; i < 50 && hub.subscriber_count() != 0; ++i) {
    hub.reap_disconnected();
    ::usleep(2000);
  }
  assert(hub.subscriber_count() == 0);
  hub.stop();
  assert(!std::filesystem::exists(path));
  assert(hub.subscriber_count() == 0);
  assert(!hub.start("/tmp/not-private/frames.sock"));
  std::filesystem::remove(dir);
  return 0;
}
