#pragma once

#include <atomic>
#include <cstdint>
#include <mutex>
#include <string>
#include <sys/types.h>
#include <thread>
#include <vector>

namespace kinect2 {

// Exactly one USB capture; viewers receive immutable snapshots by fd passing.
// The wire protocol is experimental and intentionally separate from JSON IPC.
enum class FrameKind : std::uint8_t { rgb = 1, ir = 2, depth = 3 };

class FrameSink {
 public:
  virtual ~FrameSink() = default;
  virtual void publish(FrameKind kind, const std::uint8_t* bytes,
                       std::uint32_t width, std::uint32_t height,
                       std::uint32_t bytes_per_pixel,
                       std::uint32_t sequence) noexcept = 0;
};

class FrameHub final : public FrameSink {
 public:
  FrameHub() = default;
  ~FrameHub() override;
  FrameHub(const FrameHub&) = delete;
  FrameHub& operator=(const FrameHub&) = delete;

  // Path parent must be a current-user 0700 directory; no unlink of old sockets.
  bool start(const std::string& path) noexcept;
  void stop() noexcept;
  void publish(FrameKind kind, const std::uint8_t* bytes,
               std::uint32_t width, std::uint32_t height,
               std::uint32_t bytes_per_pixel,
               std::uint32_t sequence) noexcept override;

  [[nodiscard]] std::size_t subscriber_count() const noexcept;

 private:
  struct Client {
    int fd;
    FrameKind kind;
  };
  void accept_loop() noexcept;

  mutable std::mutex mutex_;
  std::vector<Client> clients_;
  std::atomic<bool> running_{false};
  std::thread accept_thread_;
  std::string socket_path_;
  int server_fd_ = -1;
  dev_t socket_dev_ = 0;
  ino_t socket_ino_ = 0;
};

} // namespace kinect2
