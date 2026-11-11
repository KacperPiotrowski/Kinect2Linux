"""Independent CPU reference for observed vvtechs.dll active-tile preprocessing.

This models masking and tile-list generation only, not body classification,
skeleton tracking, or Microsoft proprietary shader/source code.
"""
from dataclasses import dataclass
import struct

SOURCE_WIDTH, SOURCE_HEIGHT = 512, 424
MASK_WIDTH, MASK_HEIGHT = 256, 212
REDUCED_WIDTH, REDUCED_HEIGHT = 128, 106
TILES_WIDTH, TILES_HEIGHT = 64, 53
MAX_TILES = TILES_WIDTH * TILES_HEIGHT


@dataclass(frozen=True)
class MaskResult:
    sampled_mask: bytes
    reduced_mask: bytes
    active_sample_count: int
    worklist: tuple[int, ...]
    padded_worklist: tuple[int, ...]


def preprocess_r16_uint(source: bytes, row_pitch_bytes: int = SOURCE_WIDTH * 2) -> MaskResult:
    """Sample even x/y of 512x424 LE R16_UINT, mask low 3 bits, OR neighbors.

    The row pitch is configurable to model mapped texture rows.
    """
    if row_pitch_bytes < SOURCE_WIDTH * 2:
        raise ValueError("row_pitch_bytes must be at least 1024")
    required = (SOURCE_HEIGHT - 1) * row_pitch_bytes + SOURCE_WIDTH * 2
    if len(source) < required:
        raise ValueError(f"source buffer too short: {len(source)} < {required}")

    sampled = bytearray(MASK_WIDTH * MASK_HEIGHT)
    nonzero = 0
    for y in range(MASK_HEIGHT):
        base = (y * 2) * row_pitch_bytes
        out = y * MASK_WIDTH
        for x in range(MASK_WIDTH):
            value = struct.unpack_from("<H", source, base + (x * 2) * 2)[0] & 0x7
            sampled[out + x] = value
            nonzero += (value != 0)

    reduced = bytearray(REDUCED_WIDTH * REDUCED_HEIGHT)
    for y in range(REDUCED_HEIGHT):
        top = (2 * y) * MASK_WIDTH
        bot = top + MASK_WIDTH
        dst = y * REDUCED_WIDTH
        for x in range(REDUCED_WIDTH):
            col = 2 * x
            reduced[dst + x] = (sampled[top + col] | sampled[top + col + 1]
                                | sampled[bot + col] | sampled[bot + col + 1])

    # X-outer/Y-inner visitation; encoded IDs use row-major y*64+x.
    indices = []
    for tx in range(TILES_WIDTH):
        for ty in range(TILES_HEIGHT):
            top = (2 * ty) * REDUCED_WIDTH + 2 * tx
            if (reduced[top] | reduced[top + 1] |
                    reduced[top + REDUCED_WIDTH] | reduced[top + REDUCED_WIDTH + 1]):
                indices.append(ty * TILES_WIDTH + tx)

    padded = tuple(indices) + (0,) * (MAX_TILES - len(indices))
    return MaskResult(bytes(sampled), bytes(reduced), nonzero, tuple(indices), padded)


def compute_dispatch_groups(active_tiles: int, *, has_output_buffer: bool) -> int:
    """Observed Dispatch X-group count; the other dimensions equal 1."""
    if not 0 <= active_tiles <= MAX_TILES:
        raise ValueError("active_tiles out of range")
    return min((active_tiles + 3) // 4, 848) if has_output_buffer else MAX_TILES
