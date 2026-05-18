"""Board catalogue: lookup and filter helpers over the static board list."""
from __future__ import annotations

from typing import Iterator

from .boards_data import BOARDS

KNOWN_ARCHS = frozenset({"avr", "arm-cm0+", "arm-cm4f", "arm-cm7", "xtensa", "riscv32imc"})
KNOWN_UPLOAD_PROTOCOLS = frozenset({"avrdude", "esptool", "stm32flash", "bossac"})
BOARD_FIELDS = frozenset({
    "name", "slug", "vendor", "mcu", "arch",
    "cpu_freq_mhz", "flash_kb", "ram_kb",
    "voltage_v", "has_usb", "upload_protocol", "source_url",
})


def all_boards() -> list[dict]:
    """Return a shallow copy of the full board catalogue."""
    return list(BOARDS)


def get_board(slug: str) -> dict | None:
    """Return the board entry with the given slug, or None."""
    for board in BOARDS:
        if board["slug"] == slug:
            return board
    return None


def filter_boards(
    *,
    vendor: str | None = None,
    arch: str | None = None,
    upload_protocol: str | None = None,
    min_flash_kb: int | None = None,
    min_ram_kb: int | None = None,
    has_usb: bool | None = None,
) -> list[dict]:
    """Return boards matching all supplied (non-None) criteria."""
    results: list[dict] = []
    for board in BOARDS:
        if vendor is not None and board["vendor"].lower() != vendor.lower():
            continue
        if arch is not None and board["arch"] != arch:
            continue
        if upload_protocol is not None and board["upload_protocol"] != upload_protocol:
            continue
        if min_flash_kb is not None and board["flash_kb"] < min_flash_kb:
            continue
        if min_ram_kb is not None and board["ram_kb"] < min_ram_kb:
            continue
        if has_usb is not None and board["has_usb"] != has_usb:
            continue
        results.append(board)
    return results


def iter_by_arch(arch: str) -> Iterator[dict]:
    """Yield all boards with the given architecture."""
    for board in BOARDS:
        if board["arch"] == arch:
            yield board


def slugs() -> list[str]:
    """Return all board slugs."""
    return [b["slug"] for b in BOARDS]


def validate_catalogue() -> list[str]:
    """Validate all board entries; return a list of error strings (empty == OK)."""
    errors: list[str] = []
    seen_slugs: set[str] = set()

    for i, board in enumerate(BOARDS):
        prefix = f"BOARDS[{i}] ({board.get('slug', '?')})"

        missing = BOARD_FIELDS - board.keys()
        if missing:
            errors.append(f"{prefix}: missing fields {missing}")

        slug = board.get("slug", "")
        if slug in seen_slugs:
            errors.append(f"{prefix}: duplicate slug '{slug}'")
        seen_slugs.add(slug)

        arch = board.get("arch", "")
        if arch not in KNOWN_ARCHS:
            errors.append(f"{prefix}: unknown arch '{arch}'")

        proto = board.get("upload_protocol", "")
        if proto not in KNOWN_UPLOAD_PROTOCOLS:
            errors.append(f"{prefix}: unknown upload_protocol '{proto}'")

    return errors
