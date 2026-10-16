// Kinect2-Linux experimental LOCAL control broker.
// Does not open Kinect/USB, V4L2, ALSA, or start any device service.
#include <arpa/inet.h>
#include <cerrno>
#include <csignal>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <nlohmann/json.hpp>
#include "core/sensor_backend.hpp"
#include <vector>
#include <stdexcept>
#include <string>
#include <string_view>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <unistd.h>
#include <unordered_set>

namespace {
constexpr uint32_t MAX_CONTROL_BYTES = 65536;
volatile std::sig_atomic_t running = 1;

void stop_handler(int) { running = 0; }

// The JSON library validates UTF-8, JSON grammar and escaped Unicode.
// A callback also rejects duplicate keys at every object nesting level and
// enforces a depth limit; neither is guaranteed by default json::parse().
using json = nlohmann::json;
constexpr int MAX_JSON_DEPTH = 32;
constexpr std::uint64_t MAX_REQUEST_ID = 9999999999999999ULL;

json parse_control_json(const std::string& payload) {
  int nesting = 0;
  std::vector<std::unordered_set<std::string>> object_keys;
  auto validate = [&](int, json::parse_event_t event, json& parsed) -> bool {
    switch (event) {
      case json::parse_event_t::object_start:
        if (++nesting > MAX_JSON_DEPTH)
          throw std::runtime_error("JSON nesting too deep");
        object_keys.emplace_back();
        break;
      case json::parse_event_t::array_start:
        if (++nesting > MAX_JSON_DEPTH)
          throw std::runtime_error("JSON nesting too deep");
        break;
      case json::parse_event_t::key:
        if (object_keys.empty() ||
            !object_keys.back().insert(parsed.get<std::string>()).second)
          throw std::runtime_error("duplicate JSON object key");
        break;
      case json::parse_event_t::object_end:
        object_keys.pop_back();
        --nesting;
        break;
      case json::parse_event_t::array_end:
        --nesting;
        break;
      default: break;
    }
    return true; // Keep every field for schema validation.
  };
  return json::parse(payload, validate);
}

bool read_exact(int fd, void* dst, size_t size) {
  auto* p = static_cast<char*>(dst);
  while (size) {
    const ssize_t n = recv(fd, p, size, 0);
    if (n > 0) { p += n; size -= static_cast<size_t>(n); continue; }
    if (n < 0 && errno == EINTR && running) continue;
    return false;
  }
  return true;
}

void send_json(int fd, const std::string& body) {
  const uint32_t size = static_cast<uint32_t>(body.size());
  const uint32_t net_size = htonl(size);
  std::string wire(reinterpret_cast<const char*>(&net_size), sizeof(net_size));
  wire += body;
  const char* p = wire.data();
  size_t remaining = wire.size();
  while (remaining) {
    const ssize_t n = send(fd, p, remaining, MSG_NOSIGNAL);
    if (n > 0) { p += n; remaining -= static_cast<size_t>(n); continue; }
    if (n < 0 && errno == EINTR && running) continue;
    return;
  }
}

void handle_client(int fd, const kinect2::SensorBackend& backend) {
  struct ucred peer {};
  socklen_t size = sizeof(peer);
  if (getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &peer, &size) != 0 ||
      size != sizeof(peer) || peer.uid != geteuid()) return;
  timeval timeout {2, 0};
  if (setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout)) != 0) return;
  if (setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout)) != 0) return;
  uint32_t net_length;
  if (!read_exact(fd, &net_length, sizeof(net_length))) return;
  const uint32_t length = ntohl(net_length);
  if (length == 0 || length > MAX_CONTROL_BYTES) return;
  std::string data(length, '\0');
  if (!read_exact(fd, data.data(), length)) return;
  json request;
  try { request = parse_control_json(data); }
  catch (const std::exception&) { return; }

  if (!request.is_object() || !request.contains("protocol_version") ||
      !request["protocol_version"].is_number_unsigned() ||
      request["protocol_version"].get<std::uint64_t>() != 1) return;

  if (!request.contains("request_id") ||
      !request["request_id"].is_number_unsigned()) return;
  const auto request_id = request["request_id"].get<std::uint64_t>();
  if (request_id > MAX_REQUEST_ID) return;

  if (!request.contains("params") || !request["params"].is_object() ||
      !request.contains("op") || !request["op"].is_string()) return;

  json response = {{"protocol_version", 1},
                   {"request_id", request_id}};
  const std::string op = request["op"].get<std::string>();
  if (op == "ping") {
    response["ok"] = true;
    response["result"] = {{"pong", true}};
  } else if (op == "get_status") {
    // Presence in sysfs is NOT proof of stream health, USB ownership or readiness.
    const auto discovery = backend.discover();
    response["ok"] = true;
    response["result"] = {{"state", "unavailable"},
                          {"sensor_open", false},
                          {"reason", "sensor_backend_not_implemented"},
                          {"usb_detection", {
                            {"source", "sysfs"},
                            {"scan_ok", discovery.scan_ok},
                            {"device_count", discovery.devices.size()}}}};
  } else if (op == "list_devices") {
    // Identification metadata only. Do not include serials or claim the USB interface.
    const auto discovery = backend.discover();
    json devices = json::array();
    for (const auto& device : discovery.devices) {
      devices.push_back({{"sysfs_name", device.sysfs_name},
                         {"vendor_id", "045e"}, {"product_id", "02c4"}});
    }
    response["ok"] = true;
    response["result"] = {{"source", "sysfs"}, {"scan_ok", discovery.scan_ok},
                          {"devices", std::move(devices)}};
  } else {
    response["ok"] = false;
    response["error"] = {{"code", "unknown_operation"},
                         {"message", "Unsupported control operation"}};
  }
  send_json(fd, response.dump());
}

bool valid_private_parent(const std::string& path) {
  if (path.empty() || path[0] != '/' || path.size() >= sizeof(sockaddr_un::sun_path))
    return false;
  const size_t slash = path.rfind('/');
  if (slash == std::string::npos || slash == path.size() - 1) return false;
  const std::string parent = slash == 0 ? "/" : path.substr(0, slash);
  struct stat st {};
  // Refuse symlink at immediate parent; private directory must belong to us.
  return lstat(parent.c_str(), &st) == 0 && S_ISDIR(st.st_mode) &&
         st.st_uid == geteuid() && (st.st_mode & 077) == 0;
}

} // namespace

int main(int argc, char** argv) {
  std::string path;
  if (argc == 2 && std::string_view(argv[1]) == "--help") {
    std::cout << "Usage: kinect2-broker [--socket /absolute/private/dir/kinect2.sock]\n";
    return 0;
  }
  if (argc == 3 && std::string_view(argv[1]) == "--socket") path = argv[2];
  else if (argc == 1) {
    const char* dir = getenv("XDG_RUNTIME_DIR");
    if (dir) path = std::string(dir) + "/kinect2-broker.sock";
  } else { std::cerr << "Usage: kinect2-broker [--socket PATH]\n"; return 2; }
  if (!valid_private_parent(path)) {
    std::cerr << "Socket path requires a private 0700 directory owned by current user.\n";
    return 2;
  }
  if (path.find('\0') != std::string::npos) return 2;
  // Never unlink an existing path: it could belong to another active service.
  struct stat existing {};
  if (lstat(path.c_str(), &existing) == 0 || errno != ENOENT) {
    std::cerr << "Socket path already exists (or cannot be inspected): " << path << '\n';
    return 2;
  }
  struct sigaction sa {};
  sa.sa_handler = stop_handler;
  sigemptyset(&sa.sa_mask);
  sigaction(SIGINT, &sa, nullptr);
  sigaction(SIGTERM, &sa, nullptr);
  const mode_t old_mask = umask(0077);
  const int server = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
  if (server < 0) { umask(old_mask); perror("socket"); return 1; }
  sockaddr_un addr {};
  addr.sun_family = AF_UNIX;
  std::memcpy(addr.sun_path, path.c_str(), path.size() + 1);
  const bool bound = bind(server, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) == 0;
  umask(old_mask);
  if (!bound || chmod(path.c_str(), 0600) != 0 || listen(server, 8) != 0) {
    perror("bind/chmod/listen"); close(server);
    if (bound) unlink(path.c_str());
    return 1;
  }
  struct stat created {};
  if (lstat(path.c_str(), &created) != 0 || !S_ISSOCK(created.st_mode) ||
      created.st_uid != geteuid() || (created.st_mode & 077) != 0) {
    std::cerr << "Unsafe socket permissions.\n";
    close(server); unlink(path.c_str()); return 1;
  }
  kinect2::SysfsSensorBackend sensor_backend;
  std::cout << "Kinect2 broker control socket ready: " << path
            << " (no sensor backend)\n" << std::flush;
  while (running) {
    const int client = accept4(server, nullptr, nullptr, SOCK_CLOEXEC);
    if (client < 0) {
      if (errno == EINTR) continue;
      perror("accept"); break;
    }
    handle_client(client, sensor_backend);
    close(client);
  }
  close(server);
  // Avoid removing a path that was replaced while the server was running.
  struct stat current {};
  if (lstat(path.c_str(), &current) == 0 && S_ISSOCK(current.st_mode) &&
      current.st_dev == created.st_dev && current.st_ino == created.st_ino)
    unlink(path.c_str());
  return 0;
}
