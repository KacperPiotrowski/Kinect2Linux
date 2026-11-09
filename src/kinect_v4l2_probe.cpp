// Read-only, no Kinect USB access. Tests actual CLIENT_USAGE event support
// on the exact virtual camera which the broker will later own.
#include "core/v4l2_usage_events.hpp"
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <string>
#include <unistd.h>

int main(int argc, char** argv) {
  if (argc != 1 && !(argc == 2 && std::string(argv[1]) == "--probe")) {
    std::cerr << "Usage: kinect2-v4l2-probe [--probe]\n";
    return 2;
  }
  char name[64]{};
  const int label_fd = ::open("/sys/class/video4linux/video11/name",
                              O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
  if (label_fd < 0) {
    std::cerr << "Cannot read /dev/video11 name: " << std::strerror(errno) << '\n';
    return 2;
  }
  const auto n = ::read(label_fd, name, sizeof(name) - 1);
  ::close(label_fd);
  if (n <= 0 || std::string(name) != "Kinect v2 RGB\n") {
    std::cerr << "Refusing unexpected /dev/video11 (expected Kinect v2 RGB).\n";
    return 2;
  }
  const int fd = ::open("/dev/video11",
                        O_RDONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
  if (fd < 0) {
    std::cerr << "Cannot open /dev/video11 read-only for event check: "
              << std::strerror(errno) << '\n';
    return 2;
  }
  const auto event = kinect2::subscribe_usage_event(fd);
  ::close(fd);
  if (!event.type) {
    std::cerr << "No usable v4l2loopback CLIENT_USAGE event on /dev/video11: "
              << "upstream ioctl=" << std::strerror(event.upstream_error)
              << ", Ubuntu backport ioctl=" << std::strerror(event.ubuntu_error)
              << ". Do not enable broker RGB mode. See docs/INSTALL.md.\n";
    return 2;
  }
  std::cout << "OK: /dev/video11 supports CLIENT_USAGE ("
            << (event.type == kinect2::kUsageEventUbuntuLegacy ?
                "Ubuntu legacy event ID" : "upstream event ID") << ").\n";
  return 0;
}
