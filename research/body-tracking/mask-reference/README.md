# Active-mask CPU reference (research)

Independent Python 3.10+ reference for a **small, observed preprocessing stage** of the Kinect v2 body-classification pipeline. This is **not** 3D body tracking, an SDK feature, or a working Vulkan shader.

Run from the repository root (no Kinect, GPU, dependencies or Microsoft SDK needed):

    python3 -m unittest discover -s research/body-tracking/mask-reference -p 'test_*.py' -v

The reference accepts a 512 x 424 little-endian R16_UINT buffer (optionally with a padded row pitch), samples even pixel coordinates and retains the lowest three bits. It performs two successive 2x2 bitwise-OR reductions to identify up to 3392 active tiles. The worklist is visited X-first, Y-second, but tile IDs are encoded row-major (y * 64 + x). An auxiliary function models an observed compute-dispatch group count.

## Scope and evidence

- Research prototype based on static inspection of an independently supplied legacy Kinect SDK binary, not Microsoft source code or redistributed shader bytecode.
- The nine synthetic tests check boundary cases, bit masks, tile ordering and dispatch arithmetic; passing tests **does not** demonstrate hardware, proprietary-SDK or GPU equivalence.
- Next steps: validate the source-mask semantics and GPU shader inputs; implement an independent Vulkan/SPIR-V stage, compare results against this CPU reference, benchmark only after correctness.
- Never commit Microsoft DLLs/DXBC blobs or any captured user/sensor data.

Related: [Issue #39](https://github.com/KacperPiotrowski/Kinect2Linux/issues/39).
