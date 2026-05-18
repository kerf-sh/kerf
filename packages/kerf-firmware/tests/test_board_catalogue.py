"""Tests for kerf_firmware.board_catalogue and kerf_firmware.boards_data."""
import pytest

from kerf_firmware.boards_data import BOARDS
from kerf_firmware.board_catalogue import (
    BOARD_FIELDS,
    KNOWN_ARCHS,
    KNOWN_UPLOAD_PROTOCOLS,
    all_boards,
    filter_boards,
    get_board,
    iter_by_arch,
    slugs,
    validate_catalogue,
)


# ── Data integrity ─────────────────────────────────────────────────────────────

def test_at_least_50_boards():
    assert len(BOARDS) >= 50, f"Expected ≥50 boards, got {len(BOARDS)}"


def test_all_slugs_unique():
    all_slugs = [b["slug"] for b in BOARDS]
    assert len(all_slugs) == len(set(all_slugs)), "Duplicate slugs found"


def test_every_entry_has_all_12_fields():
    for board in BOARDS:
        missing = BOARD_FIELDS - board.keys()
        assert not missing, f"{board.get('slug')} missing fields: {missing}"


def test_arch_values_are_valid():
    for board in BOARDS:
        assert board["arch"] in KNOWN_ARCHS, (
            f"{board['slug']}: invalid arch '{board['arch']}'"
        )


def test_upload_protocol_values_are_valid():
    for board in BOARDS:
        assert board["upload_protocol"] in KNOWN_UPLOAD_PROTOCOLS, (
            f"{board['slug']}: invalid upload_protocol '{board['upload_protocol']}'"
        )


def test_validate_catalogue_returns_no_errors():
    errors = validate_catalogue()
    assert errors == [], f"Catalogue validation failed:\n" + "\n".join(errors)


def test_numeric_fields_are_positive():
    for board in BOARDS:
        assert board["cpu_freq_mhz"] > 0, f"{board['slug']}: cpu_freq_mhz <= 0"
        assert board["flash_kb"] > 0, f"{board['slug']}: flash_kb <= 0"
        assert board["ram_kb"] > 0, f"{board['slug']}: ram_kb <= 0"
        assert board["voltage_v"] > 0, f"{board['slug']}: voltage_v <= 0"


def test_has_usb_is_bool():
    for board in BOARDS:
        assert isinstance(board["has_usb"], bool), (
            f"{board['slug']}: has_usb is not bool"
        )


def test_source_url_is_non_empty_string():
    for board in BOARDS:
        assert isinstance(board["source_url"], str) and board["source_url"], (
            f"{board['slug']}: source_url is empty"
        )


# ── API tests ─────────────────────────────────────────────────────────────────

def test_all_boards_returns_list_copy():
    result = all_boards()
    assert isinstance(result, list)
    assert len(result) == len(BOARDS)
    # Should be a copy, not the same object
    assert result is not BOARDS


def test_get_board_known_slug():
    board = get_board("arduino-uno-r3")
    assert board is not None
    assert board["name"] == "Arduino Uno R3"
    assert board["mcu"] == "ATmega328P"


def test_get_board_unknown_slug():
    assert get_board("nonexistent-board-xyz") is None


def test_filter_boards_by_vendor():
    arduino_boards = filter_boards(vendor="Arduino")
    assert len(arduino_boards) > 0
    for b in arduino_boards:
        assert b["vendor"].lower() == "arduino"


def test_filter_boards_by_arch():
    avr_boards = filter_boards(arch="avr")
    assert len(avr_boards) > 0
    for b in avr_boards:
        assert b["arch"] == "avr"


def test_filter_boards_by_upload_protocol():
    esptool_boards = filter_boards(upload_protocol="esptool")
    assert len(esptool_boards) > 0
    for b in esptool_boards:
        assert b["upload_protocol"] == "esptool"


def test_filter_boards_min_flash():
    big_boards = filter_boards(min_flash_kb=1024)
    for b in big_boards:
        assert b["flash_kb"] >= 1024


def test_filter_boards_min_ram():
    big_ram = filter_boards(min_ram_kb=256)
    for b in big_ram:
        assert b["ram_kb"] >= 256


def test_filter_boards_has_usb_true():
    usb_boards = filter_boards(has_usb=True)
    assert len(usb_boards) > 0
    for b in usb_boards:
        assert b["has_usb"] is True


def test_filter_boards_has_usb_false():
    no_usb = filter_boards(has_usb=False)
    assert len(no_usb) > 0
    for b in no_usb:
        assert b["has_usb"] is False


def test_filter_boards_combined():
    results = filter_boards(arch="arm-cm4f", upload_protocol="stm32flash")
    assert len(results) > 0
    for b in results:
        assert b["arch"] == "arm-cm4f"
        assert b["upload_protocol"] == "stm32flash"


def test_iter_by_arch():
    riscv_boards = list(iter_by_arch("riscv32imc"))
    assert len(riscv_boards) > 0
    for b in riscv_boards:
        assert b["arch"] == "riscv32imc"


def test_slugs_returns_all_slugs():
    all_slugs = slugs()
    assert len(all_slugs) == len(BOARDS)
    assert "arduino-uno-r3" in all_slugs
    assert "raspberry-pi-pico" in all_slugs


def test_all_6_archs_represented():
    board_archs = {b["arch"] for b in BOARDS}
    assert KNOWN_ARCHS.issubset(board_archs), (
        f"Missing archs: {KNOWN_ARCHS - board_archs}"
    )


def test_esp32_family_present():
    slugs_set = set(slugs())
    assert "esp32-wroom-32" in slugs_set
    assert "esp32-s3" in slugs_set
    assert "esp32-c3" in slugs_set


def test_rpi_pico_family_present():
    slugs_set = set(slugs())
    assert "raspberry-pi-pico" in slugs_set
    assert "raspberry-pi-pico-2" in slugs_set
    assert "raspberry-pi-pico-w" in slugs_set


def test_stm32_nucleo_family_present():
    slugs_set = set(slugs())
    assert "nucleo-f303re" in slugs_set
    assert "nucleo-f411re" in slugs_set
    assert "nucleo-h743zi" in slugs_set


def test_teensy_family_present():
    slugs_set = set(slugs())
    assert "teensy-4-0" in slugs_set
    assert "teensy-4-1" in slugs_set
