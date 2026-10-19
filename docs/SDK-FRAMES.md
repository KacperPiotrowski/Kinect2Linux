# Native RGB / IR / Depth frame contract (experimental Python SDK)

The broker is the **only** Kinect USB owner. Python `FrameClient` reads
independent, read-only sealed-memfd snapshots via the per-user Unix socket.
Consumers do not open the sensor, V4L2 devices or audio hardware.

| Stream | Native dimensions | Wire data | NumPy shape and dtype | Meaning |
| --- | --- | --- | --- | --- |
| `rgb` | 1920×1080 | packed 4-byte BGRX | `(1080, 1920, 4) uint8` | B, G, R and an unused X byte — **not** RGB or RGBA |
| `ir` | 512×424 | native little-endian float32 | `(424, 512) float32` | Raw infrared intensity; **not** normalized grayscale or distance |
| `depth` | 512×424 | native little-endian float32 | `(424, 512) float32` | Depth in **millimetres**, as delivered by libfreenect2; may contain invalid values |

All frames have `kind`, `width`, `height`, `bytes_per_pixel=4`,
`sequence`, `host_time_us` and an immutable mmap `mapping`.
`host_time_us` is a **monotonic broker publication time** (microseconds),
**not** the Kinect's sensor exposure timestamp or a hardware synchronisation
guarantee. Sequences are per native stream; they can reset after capture restart.
Do not silently assume two adjacent RGB/Depth frames are synchronized.

## Safe array snapshot (default)

Install NumPy separately only if you need array conversion.
The broker, the control SDK and tracking OFF mode do not import NumPy.

```python
from kinect2_linux.frame_client import FrameClient

with FrameClient("depth", timeout=5) as camera:
    with camera.receive() as frame:
        depth_mm = frame.as_numpy()  # owned copy: survives frame.close()
        print(depth_mm.shape, depth_mm.dtype, frame.sequence)
# depth_mm is still usable here
```

`frame.as_numpy()` (or `frame_to_numpy(frame)` from
`kinect2_linux.frame_arrays`) performs **no colorspace conversion, distortion
correction, scaling, unit changes or RGB-to-Depth registration**.
The default copy protects users from accidentally accessing released mmaps.

## Opt-in zero-copy

```python
with FrameClient("rgb") as camera:
    with camera.receive() as frame:
        bgrx = frame.as_numpy(copy=False)  # read-only, borrowed memory
        print(bgrx.shape, bgrx[0, 0, :3])  # B, G, R, NOT RGB
        del bgrx  # release EVERY derived NumPy view before frame.close()
```

If any NumPy view/slice outlives the `FrameSnapshot`, closing the mmap can
raise `BufferError`. Keep the zero-copy lifetime *strictly* inside the
frame's context; use `copy=True` when retaining or storing arrays.
The NumPy dependency is imported only on conversion.

## Explicitly not implemented by this change

- Kinect per-device IR and color **calibration** and RGB↔Depth registration
- Hardware capture-time synchronization / matched RGB-D pairs
- Point cloud XYZ / texture export to PLY or Blender
- Shared USB ownership changes, V4L2 modification, authentication or PAM

Those are subsequent SDK milestones. Existing raw streams remain unchanged.
Never insert fabricated intrinsics or treat unregistered depth pixels as
coordinates in the RGB image.
