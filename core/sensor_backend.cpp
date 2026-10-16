#include "core/sensor_backend.hpp"

#include <algorithm>
#include <array>
#include <fstream>
#include <optional>
#include <system_error>
#include <utility>

namespace kinect2 {
namespace {

// sysfs idVendor and idProduct are normally ASCII hex with a trailing newline.
// Bound reads even if a test fixture or strange filesystem contains huge files.
std::optional<std::string> read_usb_id(const std::filesystem::path& path) {
  std::ifstream file(path, std::ios::binary);
  if (!file) return std::nullopt;
  std::array<char, 16> buffer{};
  file.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
  const auto count = static_cast<size_t>(file.gcount());
  if (count == 0 || count == buffer.size()) return std::nullopt;
  std::string text(buffer.data(), count);
  const auto start = text.find_first_not_of(" \t\r\n");
  if (start == std::string::npos) return std::nullopt;
  const auto end = text.find_last_not_of(" \t\r\n");
  text = text.substr(start, end - start + 1);
  if (text.size() != 4) return std::nullopt;
  for (char& c : text) {
    if (c >= 'A' && c <= 'F') c = static_cast<char>(c - 'A' + 'a');
    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')))
      return std::nullopt;
  }
  return text;
}

}  // namespace

SysfsSensorBackend::SysfsSensorBackend(std::filesystem::path root)
    : root_(std::move(root)) {}

DiscoveryResult SysfsSensorBackend::discover() const {
  DiscoveryResult result;
  std::error_code ec;
  std::filesystem::directory_iterator it(root_, ec);
  if (ec) return result;
  result.scan_ok = true;
  const std::filesystem::directory_iterator end;
  for (; it != end; it.increment(ec)) {
    if (ec) { result.scan_ok = false; break; }
    const auto& path = it->path();
    const auto vendor = read_usb_id(path / "idVendor");
    if (!vendor || *vendor != "045e") continue;
    const auto product = read_usb_id(path / "idProduct");
    if (!product || *product != "02c4") continue;
    const std::string name = path.filename().string();
    // USB sysfs names are ASCII. Never include arbitrary metadata or serials.
    if (name.empty() || name.size() > 80 ||
        !std::all_of(name.begin(), name.end(), [](char c) {
          return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                 (c >= '0' && c <= '9') || c == '-' || c == '_' ||
                 c == '.' || c == ':';
        })) continue;
    result.devices.push_back({name});
  }
  if (ec) result.scan_ok = false;
  std::sort(result.devices.begin(), result.devices.end(),
            [](const SensorInfo& a, const SensorInfo& b) {
              return a.sysfs_name < b.sysfs_name;
            });
  return result;
}

}  // namespace kinect2
