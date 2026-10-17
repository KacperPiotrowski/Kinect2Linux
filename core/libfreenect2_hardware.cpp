#include "core/device_session.hpp"

#ifdef KINECT2_WITH_LIBFREENECT2
#include <libfreenect2/libfreenect2.hpp>
#include <libfreenect2/packet_pipeline.h>
#include <exception>
#include <memory>
#include <utility>

namespace {

class Libfreenect2Hardware final : public kinect2::HardwareDevice {
 public:
  ~Libfreenect2Hardware() override { close(); }

  kinect2::ControlResult open() override {
    if (device_) return {false, "already_open"};
    try {
      context_ = std::make_unique<libfreenect2::Freenect2>();
      if (context_->enumerateDevices() < 1) {
        close();
        return {false, "no_device"};
      }
      // Matches the CPU pipeline used by the working RGB/IR/Depth bridges.
      device_ = context_->openDevice(context_->getDefaultDeviceSerialNumber(),
                                    new libfreenect2::CpuPacketPipeline());
      if (!device_) {
        close();
        return {false, "open_failed"};
      }
      // Intentionally NO start(), startStreams(), listeners, or V4L2 writes.
      return {true, ""};
    } catch (const std::exception&) {
      close();
      return {false, "open_failed"};
    } catch (...) {
      close();
      return {false, "open_failed"};
    }
  }

  void close() noexcept override {
    if (device_) {
      try { device_->close(); } catch (...) { /* no throws on cleanup */ }
      device_ = nullptr;
    }
    context_.reset();
  }

 private:
  std::unique_ptr<libfreenect2::Freenect2> context_;
  libfreenect2::Freenect2Device* device_ = nullptr;
};
} // namespace
#endif

namespace kinect2 {

std::unique_ptr<HardwareDevice> make_hardware_device() {
#ifdef KINECT2_WITH_LIBFREENECT2
  return std::make_unique<Libfreenect2Hardware>();
#else
  return nullptr;
#endif
}

} // namespace kinect2
