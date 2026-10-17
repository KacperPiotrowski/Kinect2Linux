#include "core/auto_capture.hpp"

namespace kinect2 {

void AutoCapture::failed(std::string error) noexcept {
  last_error_.swap(error);
  retry_after_ = std::chrono::steady_clock::now() + std::chrono::seconds(2);
  session_.close();  // On failure never retain the USB lock indefinitely.
}

void AutoCapture::reconcile(SubscriptionCounts subscribers) noexcept {
  const StreamSelection wanted{subscribers.rgb != 0,
                                subscribers.ir != 0 || subscribers.depth != 0};
  if (!wanted.rgb && !wanted.ir_depth) {
    // Last client left: stop both pumps, then release the USB file lock.
    if (session_.is_open()) session_.close();
    last_error_.clear();
    retry_after_ = {};
    return;
  }

  if (session_.is_streaming() &&
      session_.selection().rgb == wanted.rgb &&
      session_.selection().ir_depth == wanted.ir_depth) return;

  if (std::chrono::steady_clock::now() < retry_after_) return;

  if (!session_.is_open()) {
    const ControlResult opened = session_.open();
    if (!opened.ok) {
      failed(opened.code);
      return;
    }
  }

  // libfreenect2 offers startStreams(rgb, ir_depth) but not an atomic
  // live reconfiguration. Stop then restart capture with the union
  // selected by all clients; other clients may briefly miss frames.
  if (session_.is_streaming()) session_.stop_streams();
  const ControlResult started = session_.start_streams(wanted);
  if (!started.ok) {
    failed(started.code);
    return;
  }

  last_error_.clear();
  retry_after_ = {};
}

} // namespace kinect2
