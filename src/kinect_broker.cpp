// Kinect2-Linux experimental LOCAL control broker.
// Does not open Kinect/USB, V4L2, ALSA, or start any device service.
#include <arpa/inet.h>
#include <cerrno>
#include <csignal>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
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
constexpr int MAX_JSON_DEPTH = 32;
volatile std::sig_atomic_t running = 1;

void stop_handler(int) { running = 0; }

// Validate all UTF-8 (including ignored JSON fields) before parsing.
bool valid_utf8(std::string_view s) {
  for (size_t i = 0; i < s.size();) {
    const unsigned char c = static_cast<unsigned char>(s[i]);
    if (c < 0x80) { ++i; continue; }
    unsigned int code = 0; size_t n = 0;
    if (c >= 0xC2 && c <= 0xDF) { code = c & 31; n = 2; }
    else if (c >= 0xE0 && c <= 0xEF) { code = c & 15; n = 3; }
    else if (c >= 0xF0 && c <= 0xF4) { code = c & 7; n = 4; }
    else return false;
    if (i + n > s.size()) return false;
    for (size_t j = 1; j < n; ++j) {
      const auto b = static_cast<unsigned char>(s[i + j]);
      if ((b & 0xC0) != 0x80) return false;
      code = (code << 6) | (b & 63);
    }
    if ((n == 2 && code < 0x80) || (n == 3 && code < 0x800) ||
        (n == 4 && code < 0x10000) || (code >= 0xD800 && code <= 0xDFFF) ||
        code > 0x10FFFF) return false;
    i += n;
  }
  return true;
}

enum class Kind { Object, Array, String, Number, Boolean, Null };
struct Value { Kind kind; std::string text; };
struct Fields { Value version{Kind::Null, ""}; Value request_id{Kind::Null, ""};
                Value op{Kind::Null, ""}; Value params{Kind::Null, ""}; };

class JsonParser {
 public:
  explicit JsonParser(std::string_view input) : input_(input) {
    if (!valid_utf8(input)) throw std::runtime_error("invalid UTF-8");
  }
  Fields parse() {
    skip_ws();
    if (peek() != '{') throw std::runtime_error("expected JSON object");
    parse_object(true);
    skip_ws();
    if (i_ != input_.size()) throw std::runtime_error("trailing JSON data");
    return fields_;
  }
 private:
  std::string_view input_;
  size_t i_ = 0;
  int depth_ = 0;
  Fields fields_;
  char peek() const { return i_ < input_.size() ? input_[i_] : '\0'; }
  void skip_ws() {
    while (peek() == ' ' || peek() == '\n' || peek() == '\r' || peek() == '\t') ++i_;
  }
  void expect(char c) {
    if (peek() != c) throw std::runtime_error("invalid JSON punctuation");
    ++i_;
  }
  void literal(std::string_view s) {
    if (input_.substr(i_, s.size()) != s) throw std::runtime_error("invalid JSON literal");
    i_ += s.size();
  }
  static bool digit(char c) { return c >= '0' && c <= '9'; }
  static void append_codepoint(std::string& out, uint32_t cp) {
    if (cp < 0x80) out.push_back(static_cast<char>(cp));
    else if (cp < 0x800) {
      out.push_back(static_cast<char>(0xC0 | (cp >> 6)));
      out.push_back(static_cast<char>(0x80 | (cp & 63)));
    } else if (cp < 0x10000) {
      out.push_back(static_cast<char>(0xE0 | (cp >> 12)));
      out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 63)));
      out.push_back(static_cast<char>(0x80 | (cp & 63)));
    } else {
      out.push_back(static_cast<char>(0xF0 | (cp >> 18)));
      out.push_back(static_cast<char>(0x80 | ((cp >> 12) & 63)));
      out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 63)));
      out.push_back(static_cast<char>(0x80 | (cp & 63)));
    }
  }
  uint32_t hex4() {
    uint32_t cp = 0;
    for (int j = 0; j < 4; ++j) {
      char c = peek();
      if (!c) throw std::runtime_error("truncated unicode escape");
      ++i_;
      cp <<= 4;
      if (c >= '0' && c <= '9') cp |= c - '0';
      else if (c >= 'a' && c <= 'f') cp |= c - 'a' + 10;
      else if (c >= 'A' && c <= 'F') cp |= c - 'A' + 10;
      else throw std::runtime_error("invalid unicode escape");
    }
    return cp;
  }
  std::string parse_string() {
    expect('"');
    std::string out;
    while (true) {
      const char c = peek();
      if (!c) throw std::runtime_error("unterminated JSON string");
      ++i_;
      if (c == '"') return out;
      if (static_cast<unsigned char>(c) < 0x20) throw std::runtime_error("control character in JSON string");
      if (c != '\\') { out.push_back(c); continue; }
      const char escaped = peek();
      if (!escaped) throw std::runtime_error("truncated escape");
      ++i_;
      switch (escaped) {
        case '"': case '\\': case '/': out.push_back(escaped); break;
        case 'b': out.push_back('\b'); break;
        case 'f': out.push_back('\f'); break;
        case 'n': out.push_back('\n'); break;
        case 'r': out.push_back('\r'); break;
        case 't': out.push_back('\t'); break;
        case 'u': {
          uint32_t cp = hex4();
          if (cp >= 0xD800 && cp <= 0xDBFF) {
            expect('\\'); expect('u');
            const uint32_t low = hex4();
            if (low < 0xDC00 || low > 0xDFFF) throw std::runtime_error("invalid unicode pair");
            cp = 0x10000 + ((cp - 0xD800) << 10) + (low - 0xDC00);
          } else if (cp >= 0xDC00 && cp <= 0xDFFF) {
            throw std::runtime_error("unpaired surrogate");
          }
          append_codepoint(out, cp);
          break;
        }
        default: throw std::runtime_error("invalid JSON string escape");
      }
    }
  }
  Value parse_number() {
    const size_t begin = i_;
    if (peek() == '-') ++i_;
    if (peek() == '0') ++i_;
    else {
      if (peek() < '1' || peek() > '9') throw std::runtime_error("invalid JSON number");
      do { ++i_; } while (digit(peek()));
    }
    if (peek() == '.') {
      ++i_; if (!digit(peek())) throw std::runtime_error("invalid JSON fraction");
      do { ++i_; } while (digit(peek()));
    }
    if (peek() == 'e' || peek() == 'E') {
      ++i_; if (peek() == '+' || peek() == '-') ++i_;
      if (!digit(peek())) throw std::runtime_error("invalid JSON exponent");
      do { ++i_; } while (digit(peek()));
    }
    return {Kind::Number, std::string(input_.substr(begin, i_ - begin))};
  }
  void parse_object(bool root) {
    if (++depth_ > MAX_JSON_DEPTH) throw std::runtime_error("JSON nesting too deep");
    expect('{'); skip_ws();
    std::unordered_set<std::string> keys;
    if (peek() != '}') {
      while (true) {
        if (peek() != '"') throw std::runtime_error("expected JSON object key");
        std::string key = parse_string();
        if (!keys.insert(key).second) throw std::runtime_error("duplicate JSON key");
        skip_ws(); expect(':'); skip_ws();
        Value value = parse_value();
        if (root) {
          if (key == "protocol_version") fields_.version = std::move(value);
          else if (key == "request_id") fields_.request_id = std::move(value);
          else if (key == "op") fields_.op = std::move(value);
          else if (key == "params") fields_.params = std::move(value);
        }
        skip_ws(); if (peek() != ',') break;
        ++i_; skip_ws();
      }
    }
    expect('}'); --depth_;
  }
  void parse_array() {
    if (++depth_ > MAX_JSON_DEPTH) throw std::runtime_error("JSON nesting too deep");
    expect('['); skip_ws();
    if (peek() != ']') {
      while (true) {
        parse_value(); skip_ws();
        if (peek() != ',') break;
        ++i_; skip_ws();
      }
    }
    expect(']'); --depth_;
  }
  Value parse_value() {
    skip_ws();
    switch (peek()) {
      case '{': parse_object(false); return {Kind::Object, ""};
      case '[': parse_array(); return {Kind::Array, ""};
      case '"': return {Kind::String, parse_string()};
      case 't': literal("true"); return {Kind::Boolean, "true"};
      case 'f': literal("false"); return {Kind::Boolean, "false"};
      case 'n': literal("null"); return {Kind::Null, ""};
      default: if (peek() == '-' || digit(peek())) return parse_number();
    }
    throw std::runtime_error("invalid JSON value");
  }
};

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

void handle_client(int fd) {
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
  Fields fields;
  try { fields = JsonParser(data).parse(); }
  catch (const std::exception&) { return; }
  if (fields.version.kind != Kind::Number || fields.version.text != "1") return;
  if (fields.request_id.kind != Kind::Number || fields.request_id.text.empty() ||
      fields.request_id.text[0] == '-' ||
      fields.request_id.text.find_first_not_of("0123456789") != std::string::npos ||
      fields.request_id.text.size() > 16) return;
  if (fields.params.kind != Kind::Object) return;
  if (fields.op.kind != Kind::String) return;
  const std::string prefix = "{\"protocol_version\":1,\"request_id\":" + fields.request_id.text;
  if (fields.op.text == "ping") {
    send_json(fd, prefix + ",\"ok\":true,\"result\":{\"pong\":true}}");
  } else if (fields.op.text == "get_status") {
    // Do not report a live hardware state: this broker has no USB backend.
    send_json(fd, prefix + ",\"ok\":true,\"result\":{\"state\":\"unavailable\","
             "\"sensor_open\":false,\"reason\":\"sensor_backend_not_implemented\"}}");
  } else {
    send_json(fd, prefix + ",\"ok\":false,\"error\":{\"code\":\"unknown_operation\","
             "\"message\":\"Unsupported control operation\"}}");
  }
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
  std::cout << "Kinect2 broker control socket ready: " << path
            << " (no sensor backend)\n" << std::flush;
  while (running) {
    const int client = accept4(server, nullptr, nullptr, SOCK_CLOEXEC);
    if (client < 0) {
      if (errno == EINTR) continue;
      perror("accept"); break;
    }
    handle_client(client);
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
