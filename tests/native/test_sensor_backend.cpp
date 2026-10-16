#include "core/sensor_backend.hpp"

#include <cassert>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <utility>

namespace fs = std::filesystem;
using kinect2::DiscoveryResult;
using kinect2::SensorBackend;
using kinect2::SensorInfo;
using kinect2::SysfsSensorBackend;

struct FakeBackend final : SensorBackend {
  DiscoveryResult result;
  DiscoveryResult discover() const override { return result; }
};

struct TempDir {
  fs::path root;
  TempDir() {
    std::string pattern = (fs::temp_directory_path() / "kinect2-sysfs-XXXXXX").string();
    char* path = mkdtemp(pattern.data());
    assert(path);
    root = path;
  }
  ~TempDir() { std::error_code ec; fs::remove_all(root, ec); }
};

void create_device(const fs::path& root, const std::string& name,
                   const std::string& vendor, const std::string& product) {
  fs::create_directory(root / name);
  std::ofstream(root / name / "idVendor") << vendor;
  std::ofstream(root / name / "idProduct") << product;
}

int main() {
  FakeBackend fake;
  fake.result = {true, {SensorInfo{"mock-1"}}};
  assert(fake.discover().scan_ok);
  assert(fake.discover().devices.at(0).sysfs_name == "mock-1");

  TempDir tmp;
  SysfsSensorBackend scanner(tmp.root);
  auto result = scanner.discover();
  assert(result.scan_ok && result.devices.empty());

  create_device(tmp.root, "3-2", "045E\n", "02C4\n");
  create_device(tmp.root, "1-1", "045e\n", "02c4\n");
  create_device(tmp.root, "2-1", "045e\n", "02c5\n");
  create_device(tmp.root, "4-3", "AAAA\n", "02c4\n");
  create_device(tmp.root, "5-1", "invalid\n", "02c4\n");
  fs::create_directory(tmp.root / "1-1:1.0");  // USB interface, not a sensor.
  result = scanner.discover();
  assert(result.scan_ok && result.devices.size() == 2);
  assert(result.devices.at(0).sysfs_name == "1-1");
  assert(result.devices.at(1).sysfs_name == "3-2");

  fs::remove_all(tmp.root / "1-1");  // Simulated unplug.
  result = scanner.discover();
  assert(result.scan_ok && result.devices.size() == 1);
  assert(result.devices.at(0).sysfs_name == "3-2");

  const SysfsSensorBackend missing(tmp.root / "no-such-path");
  result = missing.discover();
  assert(!result.scan_ok && result.devices.empty());
}
