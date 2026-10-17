#include "core/frame_hub.hpp"

#include <arpa/inet.h>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <endian.h>
#include <fcntl.h>
#include <poll.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <unistd.h>
#include <utility>

namespace kinect2 {
namespace {
constexpr std::size_t MAX_SUBSCRIBERS = 8;
constexpr std::uint64_t MAX_FRAME_BYTES = 16ULL * 1024 * 1024;

#pragma pack(push, 1)
struct WireHeader {
  char magic[4];              // K2F1
  std::uint8_t kind;          // 1 = RGB BGRX, 2 = IR f32, 3 = Depth f32
  std::uint8_t bytes_per_pixel;
  std::uint16_t reserved;
  std::uint32_t width;
  std::uint32_t height;
  std::uint32_t size;
  std::uint32_t sequence;
  std::uint64_t host_time_us;
};
#pragma pack(pop)
static_assert(sizeof(WireHeader) == 32);

bool private_parent(const std::string& path) noexcept {
  if (path.empty() || path[0] != '/' ||
      path.size() >= sizeof(sockaddr_un::sun_path)) return false;
  const auto slash = path.rfind('/');
  if (slash == std::string::npos || slash + 1 == path.size()) return false;
  const std::string dir = slash == 0 ? "/" : path.substr(0, slash);
  struct stat st {};
  return ::lstat(dir.c_str(), &st) == 0 && S_ISDIR(st.st_mode) &&
         st.st_uid == ::geteuid() && (st.st_mode & 0077) == 0;
}

bool send_frame(int sock, int fd, const WireHeader& wire) noexcept {
  iovec iov{const_cast<WireHeader*>(&wire), sizeof(wire)};
  char control[CMSG_SPACE(sizeof(int))]{};
  msghdr msg{};
  msg.msg_iov = &iov;
  msg.msg_iovlen = 1;
  msg.msg_control = control;
  msg.msg_controllen = sizeof(control);
  cmsghdr* cmsg = CMSG_FIRSTHDR(&msg);
  cmsg->cmsg_level = SOL_SOCKET;
  cmsg->cmsg_type = SCM_RIGHTS;
  cmsg->cmsg_len = CMSG_LEN(sizeof(int));
  std::memcpy(CMSG_DATA(cmsg), &fd, sizeof(fd));
  return ::sendmsg(sock, &msg, MSG_DONTWAIT | MSG_NOSIGNAL) ==
         static_cast<ssize_t>(sizeof(wire));
}

bool write_all(int fd, const std::uint8_t* bytes, std::size_t size) noexcept {
  while (size != 0) {
    const ssize_t n = ::write(fd, bytes, size);
    if (n > 0) {
      bytes += n;
      size -= static_cast<std::size_t>(n);
    } else if (n < 0 && errno == EINTR) {
      continue;
    } else {
      return false;
    }
  }
  return true;
}
} // namespace

FrameHub::~FrameHub() { stop(); }

bool FrameHub::start(const std::string& path) noexcept {
  if (running_.load() || server_fd_ >= 0 || !private_parent(path))
    return false;
  struct stat existing {};
  if (::lstat(path.c_str(), &existing) == 0 || errno != ENOENT) return false;

  const int fd = ::socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
  if (fd < 0) return false;
  sockaddr_un addr {};
  addr.sun_family = AF_UNIX;
  std::memcpy(addr.sun_path, path.c_str(), path.size() + 1);
  const mode_t mask = ::umask(0077);
  const bool bound =
      ::bind(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) == 0;
  ::umask(mask);
  if (!bound) {
    ::close(fd);
    return false;
  }
  struct stat created {};
  if (::chmod(path.c_str(), 0600) != 0 ||
      ::listen(fd, 16) != 0 ||
      ::lstat(path.c_str(), &created) != 0 ||
      !S_ISSOCK(created.st_mode) ||
      created.st_uid != ::geteuid() || (created.st_mode & 0077) != 0) {
    ::close(fd);
    ::unlink(path.c_str());
    return false;
  }
  try {
    socket_path_ = path;
    socket_dev_ = created.st_dev;
    socket_ino_ = created.st_ino;
    server_fd_ = fd;
    running_.store(true);
    accept_thread_ = std::thread(&FrameHub::accept_loop, this);
  } catch (...) {
    running_.store(false);
    ::close(fd);
    server_fd_ = -1;
    ::unlink(path.c_str());
    return false;
  }
  return true;
}

void FrameHub::stop() noexcept {
  running_.store(false);
  if (accept_thread_.joinable()) accept_thread_.join();
  std::lock_guard<std::mutex> lock(mutex_);
  for (auto& client : clients_) ::close(client.fd);
  clients_.clear();
  if (server_fd_ >= 0) {
    ::close(server_fd_);
    server_fd_ = -1;
  }
  struct stat current {};
  if (!socket_path_.empty() &&
      ::lstat(socket_path_.c_str(), &current) == 0 &&
      S_ISSOCK(current.st_mode) &&
      current.st_dev == socket_dev_ && current.st_ino == socket_ino_)
    ::unlink(socket_path_.c_str());
  socket_path_.clear();
}

std::size_t FrameHub::subscriber_count() const noexcept {
  std::lock_guard<std::mutex> lock(mutex_);
  return clients_.size();
}

void FrameHub::accept_loop() noexcept {
  while (running_.load()) {
    pollfd event{server_fd_, POLLIN, 0};
    const int result = ::poll(&event, 1, 100);
    if (result < 0 && errno == EINTR) continue;
    if (result <= 0 || !(event.revents & POLLIN)) continue;
    const int client = ::accept4(server_fd_, nullptr, nullptr,
                                 SOCK_CLOEXEC | SOCK_NONBLOCK);
    if (client < 0) continue;
    struct ucred peer {};
    socklen_t len = sizeof(peer);
    if (::getsockopt(client, SOL_SOCKET, SO_PEERCRED, &peer, &len) != 0 ||
        len != sizeof(peer) || peer.uid != ::geteuid()) {
      ::close(client);
      continue;
    }
    pollfd ready{client, POLLIN, 0};
    int rc = ::poll(&ready, 1, 300);
    if (rc <= 0 || !(ready.revents & POLLIN)) {
      ::close(client);
      continue;
    }
    char selection = '\0';
    if (::recv(client, &selection, 1, MSG_DONTWAIT) != 1 ||
        (selection != 'R' && selection != 'I' && selection != 'D')) {
      ::close(client);
      continue;
    }
    std::lock_guard<std::mutex> lock(mutex_);
    if (clients_.size() >= MAX_SUBSCRIBERS ||
        ::send(client, "K", 1, MSG_NOSIGNAL | MSG_DONTWAIT) != 1) {
      ::close(client);
      continue;
    }
    try {
      clients_.push_back(Client{client, selection == 'R' ? FrameKind::rgb :
                                (selection == 'I' ? FrameKind::ir : FrameKind::depth)});
    } catch (...) {
      ::close(client);
    }
  }
}

void FrameHub::publish(FrameKind kind, const std::uint8_t* bytes,
                       std::uint32_t width, std::uint32_t height,
                       std::uint32_t bpp, std::uint32_t sequence) noexcept {
  if (!running_.load() || !bytes || width == 0 || height == 0 || bpp != 4)
    return;
  const std::uint64_t amount = std::uint64_t(width) * height * bpp;
  if (amount == 0 || amount > MAX_FRAME_BYTES) return;
  {
    std::lock_guard<std::mutex> lock(mutex_);
    bool wanted = false;
    for (const auto& subscriber : clients_) {
      if (subscriber.kind == kind) { wanted = true; break; }
    }
    if (!wanted) return;
  }

  // One immutable sealed snapshot per captured frame; no pointers cross
  // process boundaries and no slow viewer can block the capture thread.
  const int memfd = ::memfd_create("kinect2-raw-frame",
                                  MFD_CLOEXEC | MFD_ALLOW_SEALING);
  if (memfd < 0) return;
  if (!write_all(memfd, bytes, static_cast<std::size_t>(amount)) ||
      ::fcntl(memfd, F_ADD_SEALS,
              F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK | F_SEAL_SEAL) != 0) {
    ::close(memfd);
    return;
  }
  const auto now = std::chrono::steady_clock::now().time_since_epoch();
  const auto us = std::chrono::duration_cast<std::chrono::microseconds>(now).count();
  WireHeader wire{{'K','2','F','1'}, static_cast<std::uint8_t>(kind),
                  static_cast<std::uint8_t>(bpp), 0,
                  ::htonl(width), ::htonl(height),
                  ::htonl(static_cast<std::uint32_t>(amount)),
                  ::htonl(sequence), ::htobe64(static_cast<std::uint64_t>(us))};
  {
    std::lock_guard<std::mutex> lock(mutex_);
    for (auto it = clients_.begin(); it != clients_.end();) {
      if (it->kind != kind) { ++it; continue; }
      if (send_frame(it->fd, memfd, wire)) {
        ++it;
      } else if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) {
        // Drop this frame for this client, never block USB/decode.
        ++it;
      } else {
        ::close(it->fd);
        it = clients_.erase(it);
      }
    }
  }
  ::close(memfd);
}

} // namespace kinect2
