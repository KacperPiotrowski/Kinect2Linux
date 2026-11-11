# Vulkan Compute tile-mask experiment

This is **research code**, not a production Body Tracking engine.

It extends [the CPU active-mask reference](../mask-reference/README.md) from PR #49 with a standalone **Vulkan 1.0 Compute Shader**. No Windows, Direct3D, Kinect hardware, model weights or Microsoft binaries are needed. The shader is independently written, not translated proprietary DXBC.

## Exact contract

- Input: **512 x 424 R16_UINT**, little-endian, tightly packed (no padded row pitch), supplied as a Vulkan `uint32` storage buffer with two adjacent 16-bit values per word.
- GPU workload: **53 workgroups of 64 invocations** = 3392 independent tiles. Each tile covers an 8x8 source-pixel rectangle, samples its **4x4 even-coordinate** pixels, ORs their **lowest three bits**, and stores the aggregate `uint32` to a 3392-element output buffer.
- Host converts each aggregate to one byte in row-major numeric tile-ID order. The Python parity test reconstructs the original **X-first, Y-second** ordered worklist and compares it to `mask_reference.preprocess_r16_uint`.
- This first stage does not attempt to reproduce the full sampled/reduced intermediate masks on the GPU, perform body-part classification, or produce 3D joints.
- No atomic append: each invocation writes its own output slot, so flags are deterministic. Later work can implement an efficient GPU prefix scan if required.

## Build and run on Linux

Install Vulkan loader/development headers, a Vulkan ICD/driver that supports compute (including Mesa lavapipe for software testing), `glslangValidator`, `spirv-val` and a C++17 compiler. On Debian/Ubuntu an example set is `libvulkan-dev mesa-vulkan-drivers glslang-tools spirv-tools g++`.

From the repository root:

```bash
mkdir -p /tmp/kinect2-vulkan-mask
glslangValidator -V --target-env vulkan1.0 -S comp \
  -o /tmp/kinect2-vulkan-mask/tile_mask.spv \
  research/body-tracking/vulkan-tile-mask/tile_mask.comp
spirv-val --target-env vulkan1.0 /tmp/kinect2-vulkan-mask/tile_mask.spv
g++ -std=c++17 -O2 -Wall -Wextra -Werror \
  research/body-tracking/vulkan-tile-mask/vulkan_tile_mask_runner.cpp \
  -lvulkan -o /tmp/kinect2-vulkan-mask/run
KINECT2_VULKAN_RUNNER=/tmp/kinect2-vulkan-mask/run \
KINECT2_VULKAN_SHADER=/tmp/kinect2-vulkan-mask/tile_mask.spv \
  python3 -m unittest discover -s research/body-tracking/vulkan-tile-mask -v
```

This test suite runs six synthetic inputs and checks **all 3392 output bytes and their reconstructed worklist** against the CPU reference. The dedicated GitHub Actions job deliberately selects the Mesa **lavapipe software Vulkan ICD**, allowing reproducible GPU-API testing without a physical GPU. That tests Vulkan execution, **not** real AMD/Intel/NVIDIA hardware or performance.

The runner expects arguments `<shader.spv> <input.r16> <output.bin>`. It uses host-visible Vulkan storage buffers, simple synchronous dispatch, and a CPU readback. This favors clarity and correctness; optimized memory transfers and persistent pipelines come later if needed.

**GPU compilation design:** GLSL to portable SPIR-V in CI/build; the user's Vulkan driver compiles pipelines for their actual device at runtime. This does not require GLSL tools for regular package users.

Related [Issue #39](https://github.com/KacperPiotrowski/Kinect2Linux/issues/39); stacked on draft PR #49.
