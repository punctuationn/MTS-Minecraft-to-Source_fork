# MTS_world.py
import logging
from typing import Union

from amulet import load_format
from amulet.api.level import World, Structure
from amulet.api.wrapper.world_format_wrapper import WorldFormatWrapper
from amulet.api.wrapper.structure_format_wrapper import StructureFormatWrapper
from amulet.api.errors import ChunkDoesNotExist, DimensionDoesNotExist

from PyVMF import VMF, World as VMFWorld

from MTS_block import BLOCK_SIZE, compute_texture_config, create_block
from MTS_optimization import optimize_blocks, create_cuboid

log = logging.getLogger(__name__)

# ---- Hammer/Source-friendly guardrails ----
MAX_SOLIDS_RAW = 12000
MAX_SOLIDS_OPTIMIZED = 80000
MAX_COORD = 16000  # keep geometry near origin to avoid editor/engine weirdness


def load_level(path: str) -> Union[World, Structure]:
    log.info(f"Loading level {path}")
    format_wrapper = load_format(path)

    if isinstance(format_wrapper, WorldFormatWrapper):
        return World(path, format_wrapper)
    if isinstance(format_wrapper, StructureFormatWrapper):
        return Structure(path, format_wrapper)
    raise Exception(
        f"FormatWrapper of type {format_wrapper.__class__.__name__} is not supported."
    )


def _aabb_ok(x: int, y: int, z: int, dx: int, dy: int, dz: int) -> bool:
    # Check full extents, not just the origin point
    min_x, max_x = x, x + dx
    min_y, max_y = y, y + dy
    min_z, max_z = z, z + dz
    return (
        abs(min_x) <= MAX_COORD and abs(max_x) <= MAX_COORD and
        abs(min_y) <= MAX_COORD and abs(max_y) <= MAX_COORD and
        abs(min_z) <= MAX_COORD and abs(max_z) <= MAX_COORD
    )


def get_surface_blocks(
    world_path,
    x1, z1, x2, z2,
    dimension="minecraft:overworld",
    y_min=-64,
    y_max=319,
    excluded_blocks=None
):
    """
    Iterates through all chunks in a given area and returns a list of blocks
    (excluding excluded_blocks) along with their coordinates and properties.

    Scans from y_max down to y_min.
    """
    if y_min > y_max:
        y_min, y_max = y_max, y_min

    if excluded_blocks is None:
        excluded_blocks = {"air", "barrier"}
    else:
        excluded_blocks = set(excluded_blocks)

    try:
        world = load_level(world_path)
    except Exception as e:
        print(f"Error loading world: {e}")
        return []

    blocks = []
    cx1, cz1 = x1 // 16, z1 // 16
    cx2, cz2 = x2 // 16, z2 // 16

    try:
        for cx in range(min(cx1, cx2), max(cx1, cx2) + 1):
            for cz in range(min(cz1, cz2), max(cz1, cz2) + 1):
                try:
                    chunk = world.get_chunk(cx, cz, dimension)

                    start_x = max(0, x1 - cx * 16) if cx == cx1 else 0
                    end_x = min(16, x2 - cx * 16 + 1) if cx == cx2 else 16
                    start_z = max(0, z1 - cz * 16) if cz == cz1 else 0
                    end_z = min(16, z2 - cz * 16 + 1) if cz == cz2 else 16

                    for x in range(start_x, end_x):
                        for z in range(start_z, end_z):
                            for y in range(y_max, y_min - 1, -1):
                                block = chunk.get_block(x, y, z)
                                if block.base_name in excluded_blocks:
                                    continue
                                wx = cx * 16 + x
                                wz = cz * 16 + z
                                blocks.append((wx, y, wz, block.base_name, block.properties))

                except ChunkDoesNotExist:
                    continue
                except DimensionDoesNotExist:
                    return blocks
    finally:
        try:
            world.close()
        except Exception:
            pass

    return blocks


def adjust_orientation(orientation, mirror_axis):
    if orientation is None or mirror_axis not in ("x", "y"):
        return orientation

    if isinstance(orientation, str):
        orient = orientation.lower()
        if mirror_axis == "x":
            return {"east": "west", "west": "east"}.get(orient, orientation)
        if mirror_axis == "y":
            return {"north": "south", "south": "north"}.get(orient, orientation)
        return orientation

    if isinstance(orientation, dict):
        facing = str(orientation.get("facing", "north")).lower()
        rot = int(orientation.get("rotation", 0))

        if mirror_axis == "x":
            facing = {"east": "west", "west": "east"}.get(facing, facing)
        elif mirror_axis == "y":
            facing = {"north": "south", "south": "north"}.get(facing, facing)

        return {"facing": facing, "rotation": (360 - rot) % 360}

    return orientation


def get_and_convert_blocks(
    world_path,
    x1, z1, x2, z2,
    output_vmf,
    dimension="minecraft:overworld",
    mirror_axis=None,
    optimize=False,
    y_min=-64,
    y_max=319,
    excluded_blocks=None,
    center_map=True
):
    """
    Converts blocks from a Minecraft world selection into a VMF.

    - center_map=True recenters the exported geometry around (0,0) in Hammer.
    - optimize=True merges blocks into larger cuboids.
    """
    blocks = get_surface_blocks(
        world_path,
        x1, z1, x2, z2,
        dimension=dimension,
        y_min=y_min,
        y_max=y_max,
        excluded_blocks=excluded_blocks
    )

    vmf = VMF()
    vmf.world = VMFWorld()

    if not blocks:
        vmf.export(output_vmf)
        return

    if not optimize and len(blocks) > MAX_SOLIDS_RAW:
        raise RuntimeError(
            f"Too many blocks ({len(blocks)}). Reduce selection / Y range / excluded list, or enable Optimize."
        )

    # Raw extents (used for consistent offsets & centering)
    raw_min_x = min(x for x, _, _, _, _ in blocks)
    raw_max_x = max(x for x, _, _, _, _ in blocks)
    raw_min_y = min(y for _, y, _, _, _ in blocks)
    raw_max_y = max(y for _, y, _, _, _ in blocks)
    raw_min_z = min(z for _, _, z, _, _ in blocks)
    raw_max_z = max(z for _, _, z, _, _ in blocks)

    # Centering offsets in Hammer units
    span_x_units = (raw_max_x - raw_min_x + 1) * BLOCK_SIZE  # hammer X
    span_y_units = (raw_max_z - raw_min_z + 1) * BLOCK_SIZE  # hammer Y (mc Z)
    span_z_units = (raw_max_y - raw_min_y + 1) * BLOCK_SIZE  # hammer Z (mc Y)

    off_x = -(span_x_units // 2) if center_map else 0
    off_y = -(span_y_units // 2) if center_map else 0
    off_z = -(span_z_units // 2) if center_map else 0

    if optimize:
        print("Block optimization...")
        cuboids = optimize_blocks(blocks)

        if len(cuboids) > MAX_SOLIDS_OPTIMIZED:
            raise RuntimeError(
                f"Too many optimized solids ({len(cuboids)}). Reduce selection / Y range."
            )

        opt_min_x = min(mx for mx, _, _, _, _, _, _, _ in cuboids)
        opt_min_y = min(my for _, my, _, _, _, _, _, _ in cuboids)
        opt_min_z = min(mz for _, _, mz, _, _, _, _, _ in cuboids)
        opt_max_x = max(mx + sx for mx, _, _, sx, _, _, _, _ in cuboids)
        opt_max_z = max(mz + sz for _, _, mz, _, _, sz, _, _ in cuboids)

        for mx, my, mz, sx, sy, sz, btype, props in cuboids:
            if sx <= 0 or sy <= 0 or sz <= 0:
                continue

            # Convert MC -> Hammer coordinates (relative to selection bounds)
            if mirror_axis == "x":
                hx = (opt_max_x - mx - sx) * BLOCK_SIZE
                hy = (mz - opt_min_z) * BLOCK_SIZE
            elif mirror_axis == "y":
                hx = (mx - opt_min_x) * BLOCK_SIZE
                hy = (opt_max_z - mz - sz) * BLOCK_SIZE
            else:
                hx = (mx - opt_min_x) * BLOCK_SIZE
                hy = (mz - opt_min_z) * BLOCK_SIZE

            hz = (my - opt_min_y) * BLOCK_SIZE

            # Center map around origin
            hx += off_x
            hy += off_y
            hz += off_z

            dx = sx * BLOCK_SIZE           # hammer X size
            dy = sz * BLOCK_SIZE           # hammer Y size (mc Z)
            dz = sy * BLOCK_SIZE           # hammer Z size (mc Y)

            if not _aabb_ok(hx, hy, hz, dx, dy, dz):
                continue

            create_cuboid(vmf, hx, hy, hz, dx, dy, dz, btype, props)

    else:
        # Raw blocks -> individual cubes
        for x, y, z, btype, props in blocks:
            if mirror_axis == "x":
                hx = (raw_max_x - x) * BLOCK_SIZE
                hy = (z - raw_min_z) * BLOCK_SIZE
            elif mirror_axis == "y":
                hx = (x - raw_min_x) * BLOCK_SIZE
                hy = (raw_max_z - z) * BLOCK_SIZE
            else:
                hx = (x - raw_min_x) * BLOCK_SIZE
                hy = (z - raw_min_z) * BLOCK_SIZE

            hz = (y - raw_min_y) * BLOCK_SIZE

            hx += off_x
            hy += off_y
            hz += off_z

            if not _aabb_ok(hx, hy, hz, BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE):
                continue

            texture_config, orientation = compute_texture_config(btype, props)
            orientation = adjust_orientation(orientation, mirror_axis)
            create_block(vmf, hx, hy, hz, btype, texture_config, orientation)

    vmf.export(output_vmf)
    print(f"Saved VMF: {output_vmf}")
