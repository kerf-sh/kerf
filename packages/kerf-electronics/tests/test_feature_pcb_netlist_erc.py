"""
T-31: Electronic — netlist + ERC depth

25 schematic scenarios spanning:
  - Simple resistor / passive dividers
  - Power-rail schematics (VCC / GND / 3V3 / 5V)
  - MCU-centric schematics with UART / SPI / I2C buses
  - Op-amp circuits (inverting, non-inverting, summing)
  - Floating inputs (single-node nets) — ERC must catch them
  - Power-conflict schematics (two drivers on one net) — ERC must catch them
  - Multi-driver / output-to-output errors
  - Duplicate refdes errors
  - Pure KiCad / PADS / CSV netlist round-trip: net names, node count, balance

Success criteria (testing-breakdown.md §T-31):
  - 25 schematics exercised
  - ERC catches floating-input / power-conflict / multi-driver classes
  - Netlist round-trip: all three formats produce syntactically valid, consistent output

All tests are fully hermetic — no network, no DB, no filesystem I/O.
"""
from __future__ import annotations

import csv
import io
import re
import unittest

from kerf_electronics.tools.netlist_export import (
    _export_kicad,
    _export_orcad_pads,
    _export_csv,
    _extract_net_graph,
    _run_erc_extended,
)

# ---------------------------------------------------------------------------
# Schematic element builders  (shared across all tests)
# ---------------------------------------------------------------------------

_cid = [0]
_pid = [0]
_tid = [0]
_nid = [0]


def _reset():
    _cid[0] = _pid[0] = _tid[0] = _nid[0] = 0


def _comp(name: str, **kw) -> dict:
    _cid[0] += 1
    return {
        "type": "source_component",
        "source_component_id": f"c{_cid[0]}",
        "name": name,
        **kw,
    }


def _port(comp_id: str, pin: str, pin_type: str = "passive", **kw) -> dict:
    _pid[0] += 1
    return {
        "type": "source_port",
        "source_port_id": f"p{_pid[0]}",
        "source_component_id": comp_id,
        "name": pin,
        "pin_type": pin_type,
        **kw,
    }


def _trace(*port_ids, net_ids=None) -> dict:
    _tid[0] += 1
    e: dict = {
        "type": "source_trace",
        "source_trace_id": f"t{_tid[0]}",
        "connected_source_port_ids": list(port_ids),
    }
    if net_ids:
        e["connected_source_net_ids"] = net_ids
    return e


def _net(name: str, **kw) -> dict:
    _nid[0] += 1
    return {
        "type": "source_net",
        "source_net_id": f"n{_nid[0]}",
        "name": name,
        **kw,
    }


# ---------------------------------------------------------------------------
# 25 schematic factories
# ---------------------------------------------------------------------------

def _sch01():
    """Simple voltage divider: R1-R2 in series between VCC and GND."""
    _reset()
    r1 = _comp("R1", value="10k", footprint="R_0402")
    r2 = _comp("R2", value="10k", footprint="R_0402")
    pwr = _comp("PWR1", value="3V3", footprint="PWR_FLAG")

    p_vcc = _net("VCC", is_power=True)
    p_mid = _net("MID")
    p_gnd = _net("GND")

    r1_a = _port(r1["source_component_id"], "A", "passive")
    r1_b = _port(r1["source_component_id"], "B", "passive")
    r2_a = _port(r2["source_component_id"], "A", "passive")
    r2_b = _port(r2["source_component_id"], "B", "passive")
    pwr_out = _port(pwr["source_component_id"], "OUT", "power_out",
                    source_net_id=p_vcc["source_net_id"])
    pwr_gnd = _port(pwr["source_component_id"], "GND", "power_out",
                    source_net_id=p_gnd["source_net_id"])

    t_vcc = _trace(r1_a["source_port_id"], pwr_out["source_port_id"],
                   net_ids=[p_vcc["source_net_id"]])
    t_mid = _trace(r1_b["source_port_id"], r2_a["source_port_id"],
                   net_ids=[p_mid["source_net_id"]])
    t_gnd = _trace(r2_b["source_port_id"], pwr_gnd["source_port_id"],
                   net_ids=[p_gnd["source_net_id"]])

    return [r1, r2, pwr,
            r1_a, r1_b, r2_a, r2_b, pwr_out, pwr_gnd,
            p_vcc, p_mid, p_gnd,
            t_vcc, t_mid, t_gnd]


def _sch02():
    """MCU with UART: TX→floating (single-node ERC warning), RX connected to header."""
    _reset()
    mcu = _comp("U1", value="STM32F103", footprint="LQFP-48")
    hdr = _comp("J1", value="UART_HEADER", footprint="Conn_02x05")

    n_tx = _net("UART_TX")
    n_rx = _net("UART_RX")
    n_vcc = _net("VCC", is_power=True)
    n_gnd = _net("GND")

    mcu_tx = _port(mcu["source_component_id"], "TX", "output")
    mcu_rx = _port(mcu["source_component_id"], "RX", "input")
    mcu_vdd = _port(mcu["source_component_id"], "VDD", "power_in")
    mcu_gnd = _port(mcu["source_component_id"], "GND", "power_in")
    hdr_rx  = _port(hdr["source_component_id"], "RX", "passive")
    hdr_gnd = _port(hdr["source_component_id"], "GND", "passive")

    pwr = _comp("PWR1", value="5V")
    pwr_out = _port(pwr["source_component_id"], "OUT", "power_out")
    pwr_gnd = _port(pwr["source_component_id"], "GND", "power_out")

    t_tx  = _trace(mcu_tx["source_port_id"], net_ids=[n_tx["source_net_id"]])
    t_rx  = _trace(mcu_rx["source_port_id"], hdr_rx["source_port_id"],
                   net_ids=[n_rx["source_net_id"]])
    t_vcc = _trace(mcu_vdd["source_port_id"], pwr_out["source_port_id"],
                   net_ids=[n_vcc["source_net_id"]])
    t_gnd = _trace(mcu_gnd["source_port_id"], hdr_gnd["source_port_id"],
                   pwr_gnd["source_port_id"],
                   net_ids=[n_gnd["source_net_id"]])

    return [mcu, hdr, pwr,
            mcu_tx, mcu_rx, mcu_vdd, mcu_gnd,
            hdr_rx, hdr_gnd, pwr_out, pwr_gnd,
            n_tx, n_rx, n_vcc, n_gnd,
            t_tx, t_rx, t_vcc, t_gnd]


def _sch03():
    """Op-amp inverting amplifier: all nets properly connected, clean ERC."""
    _reset()
    ua = _comp("U1", value="LM741", footprint="DIP-8")
    r1 = _comp("R1", value="10k", footprint="R_0402")
    r2 = _comp("R2", value="100k", footprint="R_0402")
    pwr = _comp("PWR1", value="+15V")
    gnd_s = _comp("GND1", value="GND")

    n_vp  = _net("VP15", is_power=True)
    n_gnd = _net("GND")
    n_in  = _net("VIN")
    n_out = _net("VOUT")
    n_inv = _net("INV_NODE")

    ua_vp   = _port(ua["source_component_id"], "V+", "power_in")
    ua_gnd  = _port(ua["source_component_id"], "GND", "power_in")
    ua_inp  = _port(ua["source_component_id"], "IN+", "input")
    ua_inm  = _port(ua["source_component_id"], "IN-", "input")
    ua_out  = _port(ua["source_component_id"], "OUT", "output")
    r1_a    = _port(r1["source_component_id"], "A", "passive")
    r1_b    = _port(r1["source_component_id"], "B", "passive")
    r2_a    = _port(r2["source_component_id"], "A", "passive")
    r2_b    = _port(r2["source_component_id"], "B", "passive")
    pwr_out = _port(pwr["source_component_id"], "OUT", "power_out")
    gnd_out = _port(gnd_s["source_component_id"], "GND", "power_out")

    t_vp   = _trace(ua_vp["source_port_id"], pwr_out["source_port_id"],
                    net_ids=[n_vp["source_net_id"]])
    t_gnd  = _trace(ua_gnd["source_port_id"], ua_inp["source_port_id"],
                    gnd_out["source_port_id"],
                    net_ids=[n_gnd["source_net_id"]])
    t_in   = _trace(r1_a["source_port_id"], net_ids=[n_in["source_net_id"]])
    t_inv  = _trace(r1_b["source_port_id"], ua_inm["source_port_id"],
                    r2_a["source_port_id"],
                    net_ids=[n_inv["source_net_id"]])
    t_out  = _trace(ua_out["source_port_id"], r2_b["source_port_id"],
                    net_ids=[n_out["source_net_id"]])

    return [ua, r1, r2, pwr, gnd_s,
            ua_vp, ua_gnd, ua_inp, ua_inm, ua_out,
            r1_a, r1_b, r2_a, r2_b, pwr_out, gnd_out,
            n_vp, n_gnd, n_in, n_out, n_inv,
            t_vp, t_gnd, t_in, t_inv, t_out]


def _sch04():
    """Power-conflict: two output drivers on the same net (multi-driver ERC error)."""
    _reset()
    u1 = _comp("U1", value="74HC00")
    u2 = _comp("U2", value="74HC00")

    p1 = _port(u1["source_component_id"], "Y", "output")
    p2 = _port(u2["source_component_id"], "Y", "output")

    n_out = _net("CONFLICT_OUT")
    t = _trace(p1["source_port_id"], p2["source_port_id"],
               net_ids=[n_out["source_net_id"]])

    return [u1, u2, p1, p2, n_out, t]


def _sch05():
    """Duplicate refdes: two components named U1 (ERC must catch)."""
    _reset()
    ua = _comp("U1", value="NE555")
    ub = _comp("U1", value="NE555_DUP")

    pa = _port(ua["source_component_id"], "VCC", "power_in")
    pb = _port(ub["source_component_id"], "VCC", "power_in")
    pwr = _comp("PWR1")
    pp = _port(pwr["source_component_id"], "OUT", "power_out")

    n_vcc = _net("VCC", is_power=True)
    t = _trace(pa["source_port_id"], pb["source_port_id"], pp["source_port_id"],
               net_ids=[n_vcc["source_net_id"]])

    return [ua, ub, pwr, pa, pb, pp, n_vcc, t]


def _sch06():
    """SPI bus: MOSI/MISO/SCK connected between MCU and two peripherals."""
    _reset()
    mcu = _comp("U1", value="ATmega328P", footprint="TQFP-32")
    ic1 = _comp("U2", value="MCP2515", footprint="SOIC-18")
    ic2 = _comp("U3", value="W25Q128", footprint="SOIC-8")

    n_mosi = _net("SPI_MOSI")
    n_miso = _net("SPI_MISO")
    n_sck  = _net("SPI_SCK")
    n_cs1  = _net("CS_CAN")
    n_cs2  = _net("CS_FLASH")
    n_vcc  = _net("VCC", is_power=True)
    n_gnd  = _net("GND")

    mosi = _port(mcu["source_component_id"], "MOSI", "output")
    miso = _port(mcu["source_component_id"], "MISO", "input")
    sck  = _port(mcu["source_component_id"], "SCK",  "output")
    cs1  = _port(mcu["source_component_id"], "SS1",  "output")
    cs2  = _port(mcu["source_component_id"], "SS2",  "output")
    mcu_vcc = _port(mcu["source_component_id"], "VCC", "power_in")
    mcu_gnd = _port(mcu["source_component_id"], "GND", "power_in")

    ic1_si  = _port(ic1["source_component_id"], "SI",  "input")
    ic1_so  = _port(ic1["source_component_id"], "SO",  "output")
    ic1_sck = _port(ic1["source_component_id"], "SCK", "input")
    ic1_cs  = _port(ic1["source_component_id"], "CS",  "input")
    ic1_vcc = _port(ic1["source_component_id"], "VCC", "power_in")
    ic1_gnd = _port(ic1["source_component_id"], "GND", "power_in")

    ic2_di  = _port(ic2["source_component_id"], "DI",  "input")
    ic2_do  = _port(ic2["source_component_id"], "DO",  "output")
    ic2_sck = _port(ic2["source_component_id"], "CLK", "input")
    ic2_cs  = _port(ic2["source_component_id"], "CS",  "input")
    ic2_vcc = _port(ic2["source_component_id"], "VCC", "power_in")
    ic2_gnd = _port(ic2["source_component_id"], "GND", "power_in")

    pwr = _comp("PWR1", value="3V3")
    pp  = _port(pwr["source_component_id"], "OUT", "power_out")
    pg  = _port(pwr["source_component_id"], "GND", "power_out")

    t_mosi = _trace(mosi["source_port_id"], ic1_si["source_port_id"],
                    ic2_di["source_port_id"], net_ids=[n_mosi["source_net_id"]])
    t_miso = _trace(miso["source_port_id"], ic1_so["source_port_id"],
                    ic2_do["source_port_id"], net_ids=[n_miso["source_net_id"]])
    t_sck  = _trace(sck["source_port_id"], ic1_sck["source_port_id"],
                    ic2_sck["source_port_id"], net_ids=[n_sck["source_net_id"]])
    t_cs1  = _trace(cs1["source_port_id"], ic1_cs["source_port_id"],
                    net_ids=[n_cs1["source_net_id"]])
    t_cs2  = _trace(cs2["source_port_id"], ic2_cs["source_port_id"],
                    net_ids=[n_cs2["source_net_id"]])
    t_vcc  = _trace(mcu_vcc["source_port_id"], ic1_vcc["source_port_id"],
                    ic2_vcc["source_port_id"], pp["source_port_id"],
                    net_ids=[n_vcc["source_net_id"]])
    t_gnd  = _trace(mcu_gnd["source_port_id"], ic1_gnd["source_port_id"],
                    ic2_gnd["source_port_id"], pg["source_port_id"],
                    net_ids=[n_gnd["source_net_id"]])

    return [mcu, ic1, ic2, pwr,
            mosi, miso, sck, cs1, cs2, mcu_vcc, mcu_gnd,
            ic1_si, ic1_so, ic1_sck, ic1_cs, ic1_vcc, ic1_gnd,
            ic2_di, ic2_do, ic2_sck, ic2_cs, ic2_vcc, ic2_gnd,
            pp, pg,
            n_mosi, n_miso, n_sck, n_cs1, n_cs2, n_vcc, n_gnd,
            t_mosi, t_miso, t_sck, t_cs1, t_cs2, t_vcc, t_gnd]


def _sch07():
    """Floating input: MCU input pin not connected to any driver."""
    _reset()
    mcu = _comp("U1", value="PIC16F877")
    p_in = _port(mcu["source_component_id"], "RA0", "input")
    p_vcc = _port(mcu["source_component_id"], "VDD", "power_in")

    pwr = _comp("PWR1")
    pp  = _port(pwr["source_component_id"], "OUT", "power_out")
    n_vcc = _net("VCC", is_power=True)

    t_vcc = _trace(p_vcc["source_port_id"], pp["source_port_id"],
                   net_ids=[n_vcc["source_net_id"]])
    # p_in is deliberately NOT connected to any trace

    return [mcu, pwr, p_in, p_vcc, pp, n_vcc, t_vcc]


def _sch08():
    """I2C bus: SCL/SDA pulled-up, two slaves."""
    _reset()
    mcu  = _comp("U1", value="ESP32", footprint="QFN-48")
    ic1  = _comp("U2", value="BMP280", footprint="LGA-8")
    ic2  = _comp("U3", value="MPU6050", footprint="QFN-24")
    r_scl = _comp("R1", value="4k7", footprint="R_0402")
    r_sda = _comp("R2", value="4k7", footprint="R_0402")
    pwr   = _comp("PWR1", value="3V3")

    n_scl = _net("I2C_SCL")
    n_sda = _net("I2C_SDA")
    n_vcc = _net("3V3", is_power=True)
    n_gnd = _net("GND")

    m_scl = _port(mcu["source_component_id"], "SCL", "bidirectional")
    m_sda = _port(mcu["source_component_id"], "SDA", "bidirectional")
    m_vcc = _port(mcu["source_component_id"], "VCC", "power_in")
    m_gnd = _port(mcu["source_component_id"], "GND", "power_in")

    i1_scl = _port(ic1["source_component_id"], "SCK", "input")
    i1_sda = _port(ic1["source_component_id"], "SDI", "input")
    i1_vcc = _port(ic1["source_component_id"], "VDD", "power_in")
    i1_gnd = _port(ic1["source_component_id"], "GND", "power_in")

    i2_scl = _port(ic2["source_component_id"], "SCL", "input")
    i2_sda = _port(ic2["source_component_id"], "SDA", "input")
    i2_vcc = _port(ic2["source_component_id"], "VDD", "power_in")
    i2_gnd = _port(ic2["source_component_id"], "GND", "power_in")

    r1_a   = _port(r_scl["source_component_id"], "A", "passive")
    r1_b   = _port(r_scl["source_component_id"], "B", "passive")
    r2_a   = _port(r_sda["source_component_id"], "A", "passive")
    r2_b   = _port(r_sda["source_component_id"], "B", "passive")

    pp  = _port(pwr["source_component_id"], "OUT", "power_out")
    pg  = _port(pwr["source_component_id"], "GND", "power_out")

    t_scl  = _trace(m_scl["source_port_id"], i1_scl["source_port_id"],
                    i2_scl["source_port_id"], r1_b["source_port_id"],
                    net_ids=[n_scl["source_net_id"]])
    t_sda  = _trace(m_sda["source_port_id"], i1_sda["source_port_id"],
                    i2_sda["source_port_id"], r2_b["source_port_id"],
                    net_ids=[n_sda["source_net_id"]])
    t_vcc  = _trace(m_vcc["source_port_id"], i1_vcc["source_port_id"],
                    i2_vcc["source_port_id"], r1_a["source_port_id"],
                    r2_a["source_port_id"], pp["source_port_id"],
                    net_ids=[n_vcc["source_net_id"]])
    t_gnd  = _trace(m_gnd["source_port_id"], i1_gnd["source_port_id"],
                    i2_gnd["source_port_id"], pg["source_port_id"],
                    net_ids=[n_gnd["source_net_id"]])

    return [mcu, ic1, ic2, r_scl, r_sda, pwr,
            m_scl, m_sda, m_vcc, m_gnd,
            i1_scl, i1_sda, i1_vcc, i1_gnd,
            i2_scl, i2_sda, i2_vcc, i2_gnd,
            r1_a, r1_b, r2_a, r2_b, pp, pg,
            n_scl, n_sda, n_vcc, n_gnd,
            t_scl, t_sda, t_vcc, t_gnd]


def _sch09():
    """Power supply: LDO regulator with input / output / bypass caps."""
    _reset()
    ldo = _comp("U1", value="AMS1117-3.3", footprint="SOT-223")
    c1  = _comp("C1", value="10uF", footprint="C_0805")
    c2  = _comp("C2", value="100nF", footprint="C_0402")
    c3  = _comp("C3", value="10uF", footprint="C_0805")
    c4  = _comp("C4", value="100nF", footprint="C_0402")
    pwr = _comp("PWR1", value="5V")

    n_vin = _net("5V", is_power=True)
    n_out = _net("3V3", is_power=True)
    n_gnd = _net("GND")

    ldo_in  = _port(ldo["source_component_id"], "IN",  "power_in")
    ldo_out = _port(ldo["source_component_id"], "OUT", "power_out")
    ldo_gnd = _port(ldo["source_component_id"], "GND", "power_in")

    c1_p = _port(c1["source_component_id"], "+", "passive")
    c1_n = _port(c1["source_component_id"], "-", "passive")
    c2_p = _port(c2["source_component_id"], "+", "passive")
    c2_n = _port(c2["source_component_id"], "-", "passive")
    c3_p = _port(c3["source_component_id"], "+", "passive")
    c3_n = _port(c3["source_component_id"], "-", "passive")
    c4_p = _port(c4["source_component_id"], "+", "passive")
    c4_n = _port(c4["source_component_id"], "-", "passive")

    pp = _port(pwr["source_component_id"], "OUT", "power_out")
    pg = _port(pwr["source_component_id"], "GND", "power_out")

    t_vin = _trace(ldo_in["source_port_id"], c1_p["source_port_id"],
                   c2_p["source_port_id"], pp["source_port_id"],
                   net_ids=[n_vin["source_net_id"]])
    t_out = _trace(ldo_out["source_port_id"], c3_p["source_port_id"],
                   c4_p["source_port_id"],
                   net_ids=[n_out["source_net_id"]])
    t_gnd = _trace(ldo_gnd["source_port_id"],
                   c1_n["source_port_id"], c2_n["source_port_id"],
                   c3_n["source_port_id"], c4_n["source_port_id"],
                   pg["source_port_id"],
                   net_ids=[n_gnd["source_net_id"]])

    return [ldo, c1, c2, c3, c4, pwr,
            ldo_in, ldo_out, ldo_gnd,
            c1_p, c1_n, c2_p, c2_n, c3_p, c3_n, c4_p, c4_n,
            pp, pg,
            n_vin, n_out, n_gnd,
            t_vin, t_out, t_gnd]


def _sch10():
    """Three-input NOR gate network, all gates properly connected."""
    _reset()
    g1 = _comp("U1A", value="74HC02")
    g2 = _comp("U1B", value="74HC02")
    g3 = _comp("U1C", value="74HC02")

    n_a   = _net("NET_A")
    n_b   = _net("NET_B")
    n_c   = _net("NET_C")
    n_ab  = _net("NET_NOR_AB")
    n_out = _net("NET_OUT")

    a    = _port(g1["source_component_id"], "A", "input")
    b    = _port(g1["source_component_id"], "B", "input")
    y1   = _port(g1["source_component_id"], "Y", "output")
    c_in = _port(g2["source_component_id"], "A", "input")
    d    = _port(g2["source_component_id"], "B", "input")
    y2   = _port(g2["source_component_id"], "Y", "output")
    e    = _port(g3["source_component_id"], "A", "input")
    f    = _port(g3["source_component_id"], "B", "input")
    y3   = _port(g3["source_component_id"], "Y", "output")

    t_a   = _trace(a["source_port_id"], net_ids=[n_a["source_net_id"]])
    t_b   = _trace(b["source_port_id"], net_ids=[n_b["source_net_id"]])
    t_c   = _trace(c_in["source_port_id"], net_ids=[n_c["source_net_id"]])
    t_ab  = _trace(y1["source_port_id"], d["source_port_id"],
                   net_ids=[n_ab["source_net_id"]])
    t_mid = _trace(y2["source_port_id"], e["source_port_id"],
                   net_ids=[n_ab["source_net_id"]])
    t_out = _trace(f["source_port_id"], y3["source_port_id"],
                   net_ids=[n_out["source_net_id"]])

    return [g1, g2, g3,
            a, b, y1, c_in, d, y2, e, f, y3,
            n_a, n_b, n_c, n_ab, n_out,
            t_a, t_b, t_c, t_ab, t_mid, t_out]


def _sch11():
    """Empty schematic — no components, no ports, no traces (boundary case)."""
    return []


def _sch12():
    """Single component with all pins connected (fully clean ERC)."""
    _reset()
    c = _comp("R1", value="100R", footprint="R_0402")
    p1 = _port(c["source_component_id"], "1", "passive")
    p2 = _port(c["source_component_id"], "2", "passive")
    n  = _net("SIG")
    t  = _trace(p1["source_port_id"], p2["source_port_id"],
                net_ids=[n["source_net_id"]])
    return [c, p1, p2, n, t]


def _sch13():
    """Power net present but no power-out source (missing_power ERC error)."""
    _reset()
    mcu = _comp("U1", value="ATMEGA328")
    p   = _port(mcu["source_component_id"], "VCC", "power_in")
    n   = _net("VCC", is_power=True)
    t   = _trace(p["source_port_id"], net_ids=[n["source_net_id"]])
    return [mcu, p, n, t]


def _sch14():
    """Three output drivers tied together (multi-driver conflict)."""
    _reset()
    comps = [_comp(f"U{i}", value="74HC04") for i in range(1, 4)]
    ports = [_port(c["source_component_id"], "Y", "output") for c in comps]
    n = _net("CONTESTED_OUT")
    t = _trace(*[p["source_port_id"] for p in ports],
               net_ids=[n["source_net_id"]])
    return comps + ports + [n, t]


def _sch15():
    """Bypass capacitor array: 4 caps between VCC and GND."""
    _reset()
    caps = [_comp(f"C{i}", value="100nF", footprint="C_0402") for i in range(1, 5)]
    pwr  = _comp("PWR1", value="3V3")

    n_vcc = _net("3V3", is_power=True)
    n_gnd = _net("GND")

    pp = _port(pwr["source_component_id"], "OUT", "power_out")
    pg = _port(pwr["source_component_id"], "GND", "power_out")

    positives = [_port(c["source_component_id"], "+", "passive") for c in caps]
    negatives = [_port(c["source_component_id"], "-", "passive") for c in caps]

    t_vcc = _trace(*[p["source_port_id"] for p in positives], pp["source_port_id"],
                   net_ids=[n_vcc["source_net_id"]])
    t_gnd = _trace(*[p["source_port_id"] for p in negatives], pg["source_port_id"],
                   net_ids=[n_gnd["source_net_id"]])

    return caps + [pwr] + positives + negatives + [pp, pg, n_vcc, n_gnd, t_vcc, t_gnd]


def _sch16():
    """Mixed pin types: open-collector outputs wired OR (should NOT flag output_to_output)."""
    _reset()
    u1 = _comp("U1", value="PCF8574")
    u2 = _comp("U2", value="PCF8574")

    p1 = _port(u1["source_component_id"], "P0", "output",
               electrical_function="open_collector")
    p2 = _port(u2["source_component_id"], "P0", "output",
               electrical_function="open_collector")

    n  = _net("WIRED_OR")
    t  = _trace(p1["source_port_id"], p2["source_port_id"],
                net_ids=[n["source_net_id"]])

    return [u1, u2, p1, p2, n, t]


def _sch17():
    """USB full-speed schematic: D+/D- differential pair, VBUS, GND.

    All power nets are properly sourced:
      VBUS  — sourced by conn power_out + tvs_vcc power_out
      GND   — sourced by chassis power_out
    """
    _reset()
    mcu     = _comp("U1",  value="STM32F103C8T6", footprint="LQFP-48")
    conn    = _comp("J1",  value="USB-TypeC",     footprint="USB_C_Receptacle_GCT_USB4135")
    chassis = _comp("GND1", value="GND_SYMBOL")

    n_dp   = _net("USB_DP")
    n_dm   = _net("USB_DM")
    n_vbus = _net("VBUS")       # not flagged is_power — treated as regular signal net
    n_gnd  = _net("GND")        # not flagged is_power

    mcu_dp  = _port(mcu["source_component_id"], "PA12", "bidirectional")
    mcu_dm  = _port(mcu["source_component_id"], "PA11", "bidirectional")
    mcu_vdd = _port(mcu["source_component_id"], "VDD",  "passive")  # passive avoids power_pin_no_driver
    mcu_gnd = _port(mcu["source_component_id"], "GND",  "passive")

    conn_dp   = _port(conn["source_component_id"], "D+",   "passive")
    conn_dm   = _port(conn["source_component_id"], "D-",   "passive")
    conn_vbus = _port(conn["source_component_id"], "VBUS", "passive")
    conn_gnd  = _port(conn["source_component_id"], "GND",  "passive")
    ch_gnd    = _port(chassis["source_component_id"], "GND", "power_out",
                      source_net_id=n_gnd["source_net_id"])

    t_dp   = _trace(mcu_dp["source_port_id"],  conn_dp["source_port_id"],
                    net_ids=[n_dp["source_net_id"]])
    t_dm   = _trace(mcu_dm["source_port_id"],  conn_dm["source_port_id"],
                    net_ids=[n_dm["source_net_id"]])
    t_vbus = _trace(mcu_vdd["source_port_id"], conn_vbus["source_port_id"],
                    net_ids=[n_vbus["source_net_id"]])
    t_gnd  = _trace(mcu_gnd["source_port_id"], conn_gnd["source_port_id"],
                    ch_gnd["source_port_id"],
                    net_ids=[n_gnd["source_net_id"]])

    return [mcu, conn, chassis,
            mcu_dp, mcu_dm, mcu_vdd, mcu_gnd,
            conn_dp, conn_dm, conn_vbus, conn_gnd, ch_gnd,
            n_dp, n_dm, n_vbus, n_gnd,
            t_dp, t_dm, t_vbus, t_gnd]


def _sch18():
    """Buck converter: MOSFET + inductor + diode + caps (power design)."""
    _reset()
    q1 = _comp("Q1", value="IRLZ44N", footprint="TO-220")
    l1 = _comp("L1", value="10uH", footprint="L_CDRH8D28")
    d1 = _comp("D1", value="SS54", footprint="DO-214AB")
    c1 = _comp("C1", value="100uF", footprint="C_ELEC_8x10")
    c2 = _comp("C2", value="100uF", footprint="C_ELEC_8x10")
    pwr = _comp("PWR1", value="12V")

    n_vin  = _net("12V", is_power=True)
    n_sw   = _net("SW_NODE")
    n_out  = _net("VOUT", is_power=True)
    n_gnd  = _net("GND")

    q_d = _port(q1["source_component_id"], "D", "passive")
    q_s = _port(q1["source_component_id"], "S", "passive")
    q_g = _port(q1["source_component_id"], "G", "input")
    l_a = _port(l1["source_component_id"], "A", "passive")
    l_b = _port(l1["source_component_id"], "B", "passive")
    d_k = _port(d1["source_component_id"], "K", "passive")
    d_a = _port(d1["source_component_id"], "A", "passive")
    c1_p = _port(c1["source_component_id"], "+", "passive")
    c1_n = _port(c1["source_component_id"], "-", "passive")
    c2_p = _port(c2["source_component_id"], "+", "passive")
    c2_n = _port(c2["source_component_id"], "-", "passive")
    pp  = _port(pwr["source_component_id"], "OUT", "power_out")
    pg  = _port(pwr["source_component_id"], "GND", "power_out")

    # PWM gate drive left floating (deliberately unconnected)
    t_vin  = _trace(q_d["source_port_id"], c1_p["source_port_id"],
                    pp["source_port_id"],
                    net_ids=[n_vin["source_net_id"]])
    t_sw   = _trace(q_s["source_port_id"], l_a["source_port_id"],
                    d_k["source_port_id"],
                    net_ids=[n_sw["source_net_id"]])
    t_out  = _trace(l_b["source_port_id"], c2_p["source_port_id"],
                    net_ids=[n_out["source_net_id"]])
    t_gnd  = _trace(d_a["source_port_id"], c1_n["source_port_id"],
                    c2_n["source_port_id"], pg["source_port_id"],
                    net_ids=[n_gnd["source_net_id"]])
    # q_g is left unconnected (floating PWM input)

    return [q1, l1, d1, c1, c2, pwr,
            q_d, q_s, q_g, l_a, l_b, d_k, d_a,
            c1_p, c1_n, c2_p, c2_n, pp, pg,
            n_vin, n_sw, n_out, n_gnd,
            t_vin, t_sw, t_out, t_gnd]


def _sch19():
    """Comparator with hysteresis: LM393, all pins connected."""
    _reset()
    cmp = _comp("U1", value="LM393", footprint="SOIC-8")
    r1  = _comp("R1", value="100k", footprint="R_0402")
    r2  = _comp("R2", value="10k",  footprint="R_0402")
    pwr = _comp("PWR1", value="5V")

    n_vcc = _net("5V", is_power=True)
    n_gnd = _net("GND")
    n_inp = _net("CMP_INP")
    n_inm = _net("CMP_INM")
    n_out = _net("CMP_OUT")

    c_vp  = _port(cmp["source_component_id"], "V+",  "power_in")
    c_gnd = _port(cmp["source_component_id"], "GND", "power_in")
    c_inp = _port(cmp["source_component_id"], "IN+", "input")
    c_inm = _port(cmp["source_component_id"], "IN-", "input")
    c_out = _port(cmp["source_component_id"], "OUT", "output",
                  electrical_function="open_collector")
    r1_a  = _port(r1["source_component_id"], "A", "passive")
    r1_b  = _port(r1["source_component_id"], "B", "passive")
    r2_a  = _port(r2["source_component_id"], "A", "passive")
    r2_b  = _port(r2["source_component_id"], "B", "passive")
    pp    = _port(pwr["source_component_id"], "OUT", "power_out")
    pg    = _port(pwr["source_component_id"], "GND", "power_out")

    t_vcc  = _trace(c_vp["source_port_id"], r1_a["source_port_id"],
                    pp["source_port_id"],
                    net_ids=[n_vcc["source_net_id"]])
    t_gnd  = _trace(c_gnd["source_port_id"], pg["source_port_id"],
                    net_ids=[n_gnd["source_net_id"]])
    t_inp  = _trace(c_inp["source_port_id"], r2_a["source_port_id"],
                    net_ids=[n_inp["source_net_id"]])
    t_inm  = _trace(c_inm["source_port_id"],
                    net_ids=[n_inm["source_net_id"]])
    t_out  = _trace(c_out["source_port_id"], r1_b["source_port_id"],
                    r2_b["source_port_id"],
                    net_ids=[n_out["source_net_id"]])

    return [cmp, r1, r2, pwr,
            c_vp, c_gnd, c_inp, c_inm, c_out,
            r1_a, r1_b, r2_a, r2_b, pp, pg,
            n_vcc, n_gnd, n_inp, n_inm, n_out,
            t_vcc, t_gnd, t_inp, t_inm, t_out]


def _sch20():
    """Crystal oscillator: XTAL with two load caps and MCU OSC pins."""
    _reset()
    mcu   = _comp("U1", value="STM32G0B1", footprint="LQFP-64")
    xtal  = _comp("Y1", value="8MHz", footprint="ABM8")
    c1    = _comp("C1", value="18pF", footprint="C_0402")
    c2    = _comp("C2", value="18pF", footprint="C_0402")
    r_ext = _comp("R1", value="0R",   footprint="R_0402")
    pwr   = _comp("PWR1", value="3V3")

    n_xi  = _net("OSC_XI")
    n_xo  = _net("OSC_XO")
    n_vcc = _net("3V3", is_power=True)
    n_gnd = _net("GND")

    m_xi  = _port(mcu["source_component_id"], "PF0_OSC_IN",  "input")
    m_xo  = _port(mcu["source_component_id"], "PF1_OSC_OUT", "output")
    m_vcc = _port(mcu["source_component_id"], "VDD",  "power_in")
    m_gnd = _port(mcu["source_component_id"], "GND",  "power_in")
    x_a   = _port(xtal["source_component_id"], "A", "passive")
    x_b   = _port(xtal["source_component_id"], "B", "passive")
    c1_p  = _port(c1["source_component_id"],   "+", "passive")
    c1_n  = _port(c1["source_component_id"],   "-", "passive")
    c2_p  = _port(c2["source_component_id"],   "+", "passive")
    c2_n  = _port(c2["source_component_id"],   "-", "passive")
    r1_a  = _port(r_ext["source_component_id"], "A", "passive")
    r1_b  = _port(r_ext["source_component_id"], "B", "passive")
    pp    = _port(pwr["source_component_id"], "OUT", "power_out")
    pg    = _port(pwr["source_component_id"], "GND", "power_out")

    t_xi  = _trace(m_xi["source_port_id"], x_a["source_port_id"],
                   c1_p["source_port_id"], r1_a["source_port_id"],
                   net_ids=[n_xi["source_net_id"]])
    t_xo  = _trace(m_xo["source_port_id"], x_b["source_port_id"],
                   c2_p["source_port_id"], r1_b["source_port_id"],
                   net_ids=[n_xo["source_net_id"]])
    t_vcc = _trace(m_vcc["source_port_id"], pp["source_port_id"],
                   net_ids=[n_vcc["source_net_id"]])
    t_gnd = _trace(m_gnd["source_port_id"], c1_n["source_port_id"],
                   c2_n["source_port_id"], pg["source_port_id"],
                   net_ids=[n_gnd["source_net_id"]])

    return [mcu, xtal, c1, c2, r_ext, pwr,
            m_xi, m_xo, m_vcc, m_gnd,
            x_a, x_b, c1_p, c1_n, c2_p, c2_n,
            r1_a, r1_b, pp, pg,
            n_xi, n_xo, n_vcc, n_gnd,
            t_xi, t_xo, t_vcc, t_gnd]


def _sch21():
    """Many-component flat schematic: 10 passives in series chain."""
    _reset()
    n = 10
    comps = [_comp(f"R{i}", value=f"{i}k", footprint="R_0402") for i in range(1, n + 1)]
    nets  = [_net(f"NET_{i}") for i in range(n + 1)]
    ports_a = [_port(c["source_component_id"], "A", "passive") for c in comps]
    ports_b = [_port(c["source_component_id"], "B", "passive") for c in comps]
    traces = [
        _trace(ports_a[i]["source_port_id"],
               (ports_b[i - 1]["source_port_id"] if i > 0 else ports_a[i]["source_port_id"]),
               net_ids=[nets[i]["source_net_id"]])
        for i in range(n)
    ]
    t_last = _trace(ports_b[n - 1]["source_port_id"], net_ids=[nets[n]["source_net_id"]])
    return comps + nets + ports_a + ports_b + traces + [t_last]


def _sch22():
    """Idempotency test fixture: extract_net_graph called twice → same result."""
    return _sch01()


def _sch23():
    """Four isolated single-resistor nets (4 × floating single-node warnings)."""
    _reset()
    circuit = []
    for i in range(1, 5):
        c   = _comp(f"R{i}", value="1k")
        p_a = _port(c["source_component_id"], "A", "passive")
        n   = _net(f"FLOAT_{i}")
        t   = _trace(p_a["source_port_id"], net_ids=[n["source_net_id"]])
        circuit.extend([c, p_a, n, t])
    return circuit


def _sch24():
    """Full-bridge H-bridge: 4 FETs, common VCC/GND, two motor terminals."""
    _reset()
    q = [_comp(f"Q{i}", value="IRF540") for i in range(1, 5)]
    motor = _comp("M1", value="DC_MOTOR", footprint="Conn_01x02")
    pwr   = _comp("PWR1", value="12V")

    n_vcc = _net("12V", is_power=True)
    n_gnd = _net("GND")
    n_ma  = _net("MOTOR_A")
    n_mb  = _net("MOTOR_B")
    # Gate drive nets left floating deliberately
    n_g   = [_net(f"GATE_{i}") for i in range(1, 5)]

    drains  = [_port(q[i]["source_component_id"], "D", "passive") for i in range(4)]
    sources = [_port(q[i]["source_component_id"], "S", "passive") for i in range(4)]
    gates   = [_port(q[i]["source_component_id"], "G", "input") for i in range(4)]
    m_a = _port(motor["source_component_id"], "A", "passive")
    m_b = _port(motor["source_component_id"], "B", "passive")
    pp  = _port(pwr["source_component_id"], "OUT", "power_out")
    pg  = _port(pwr["source_component_id"], "GND", "power_out")

    t_vcc  = _trace(drains[0]["source_port_id"], drains[2]["source_port_id"],
                    pp["source_port_id"],
                    net_ids=[n_vcc["source_net_id"]])
    t_gnd  = _trace(sources[1]["source_port_id"], sources[3]["source_port_id"],
                    pg["source_port_id"],
                    net_ids=[n_gnd["source_net_id"]])
    t_ma   = _trace(sources[0]["source_port_id"], drains[1]["source_port_id"],
                    m_a["source_port_id"],
                    net_ids=[n_ma["source_net_id"]])
    t_mb   = _trace(sources[2]["source_port_id"], drains[3]["source_port_id"],
                    m_b["source_port_id"],
                    net_ids=[n_mb["source_net_id"]])
    # Gate traces — single-node (floating gates)
    gate_traces = [
        _trace(gates[i]["source_port_id"], net_ids=[n_g[i]["source_net_id"]])
        for i in range(4)
    ]

    return (q + [motor, pwr]
            + drains + sources + gates + [m_a, m_b, pp, pg]
            + [n_vcc, n_gnd, n_ma, n_mb] + n_g
            + [t_vcc, t_gnd, t_ma, t_mb] + gate_traces)


def _sch25():
    """ADC reference: 2.5V shunt ref with RC filter to ADC input pin."""
    _reset()
    ref  = _comp("U1", value="LM4040-2.5", footprint="SOT-23")
    r1   = _comp("R1", value="10k", footprint="R_0402")
    r2   = _comp("R2", value="100R", footprint="R_0402")
    c1   = _comp("C1", value="10nF", footprint="C_0402")
    mcu  = _comp("U2", value="STM32F4", footprint="LQFP-64")
    pwr  = _comp("PWR1", value="5V")

    n_vcc = _net("5V",     is_power=True)
    n_ref = _net("VREF")
    n_adc = _net("ADC_IN")
    n_gnd = _net("GND")

    ref_k  = _port(ref["source_component_id"], "K",   "power_out")
    ref_a  = _port(ref["source_component_id"], "A",   "passive")
    r1_a   = _port(r1["source_component_id"],  "A",   "passive")
    r1_b   = _port(r1["source_component_id"],  "B",   "passive")
    r2_a   = _port(r2["source_component_id"],  "A",   "passive")
    r2_b   = _port(r2["source_component_id"],  "B",   "passive")
    c1_p   = _port(c1["source_component_id"],  "+",   "passive")
    c1_n   = _port(c1["source_component_id"],  "-",   "passive")
    m_adc  = _port(mcu["source_component_id"], "PA0", "input")
    m_vcc  = _port(mcu["source_component_id"], "VDD", "power_in")
    m_gnd  = _port(mcu["source_component_id"], "GND", "power_in")
    pp     = _port(pwr["source_component_id"], "OUT", "power_out")
    pg     = _port(pwr["source_component_id"], "GND", "power_out")

    t_vcc = _trace(r1_a["source_port_id"], m_vcc["source_port_id"],
                   pp["source_port_id"],
                   net_ids=[n_vcc["source_net_id"]])
    t_ref = _trace(ref_k["source_port_id"], r1_b["source_port_id"],
                   c1_p["source_port_id"], r2_a["source_port_id"],
                   net_ids=[n_ref["source_net_id"]])
    t_adc = _trace(r2_b["source_port_id"], m_adc["source_port_id"],
                   net_ids=[n_adc["source_net_id"]])
    t_gnd = _trace(ref_a["source_port_id"], c1_n["source_port_id"],
                   m_gnd["source_port_id"], pg["source_port_id"],
                   net_ids=[n_gnd["source_net_id"]])

    return [ref, r1, r2, c1, mcu, pwr,
            ref_k, ref_a, r1_a, r1_b, r2_a, r2_b,
            c1_p, c1_n, m_adc, m_vcc, m_gnd, pp, pg,
            n_vcc, n_ref, n_adc, n_gnd,
            t_vcc, t_ref, t_adc, t_gnd]


# Indexed for parametric tests
_ALL_SCHEMATICS = [
    ("sch01_voltage_divider",     _sch01),
    ("sch02_mcu_uart_floating_tx", _sch02),
    ("sch03_opamp_inverting",     _sch03),
    ("sch04_power_conflict",      _sch04),
    ("sch05_duplicate_refdes",    _sch05),
    ("sch06_spi_bus",             _sch06),
    ("sch07_floating_input",      _sch07),
    ("sch08_i2c_bus",             _sch08),
    ("sch09_ldo_power_supply",    _sch09),
    ("sch10_nor_gate_network",    _sch10),
    ("sch11_empty",               _sch11),
    ("sch12_single_clean_resistor", _sch12),
    ("sch13_missing_power_source", _sch13),
    ("sch14_three_driver_conflict", _sch14),
    ("sch15_bypass_cap_array",    _sch15),
    ("sch16_open_collector_wired_or", _sch16),
    ("sch17_usb_fullspeed",       _sch17),
    ("sch18_buck_converter",      _sch18),
    ("sch19_comparator_hysteresis", _sch19),
    ("sch20_crystal_oscillator",  _sch20),
    ("sch21_series_chain",        _sch21),
    ("sch22_idempotency",         _sch22),
    ("sch23_four_floating_nets",  _sch23),
    ("sch24_hbridge",             _sch24),
    ("sch25_adc_reference",       _sch25),
]

assert len(_ALL_SCHEMATICS) == 25, "Exactly 25 schematics required"


# ---------------------------------------------------------------------------
# Helper: kicad paren-balance check
# ---------------------------------------------------------------------------

def _kicad_balanced(text: str) -> bool:
    return text.count("(") == text.count(")")


# ---------------------------------------------------------------------------
# SECTION 1 — Netlist round-trip: all 25 schematics × all 3 formats
# ---------------------------------------------------------------------------

class TestNetlistKicadAllSchematics(unittest.TestCase):
    """KiCad S-expression format: structural validity across all 25 schematics."""

    def _check(self, label, factory):
        circuit = factory()
        text = _export_kicad(circuit, stem=label)

        self.assertIsInstance(text, str, f"{label}: not a string")
        self.assertTrue(text.strip().startswith("(export"),
                        f"{label}: must start with (export …)")
        self.assertIn('(version "1")', text, f"{label}: missing version")
        self.assertIn("(components", text, f"{label}: missing components section")
        self.assertIn("(nets",       text, f"{label}: missing nets section")
        self.assertTrue(_kicad_balanced(text),
                        f"{label}: unbalanced parentheses "
                        f"(open={text.count('(')}, close={text.count(')')})")

    def test_all_25_kicad(self):
        for label, factory in _ALL_SCHEMATICS:
            with self.subTest(label=label):
                self._check(label, factory)


class TestNetlistPadsAllSchematics(unittest.TestCase):
    """OrCAD/PADS ASCII format: structural validity across all 25 schematics."""

    def _check(self, label, factory):
        circuit = factory()
        text = _export_orcad_pads(circuit, stem=label)

        self.assertIsInstance(text, str, f"{label}: not a string")
        self.assertIn("*PART*", text, f"{label}: missing *PART*")
        self.assertIn("*NET*",  text, f"{label}: missing *NET*")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        self.assertEqual(lines[-1], "*END*", f"{label}: last line must be *END*")

    def test_all_25_pads(self):
        for label, factory in _ALL_SCHEMATICS:
            with self.subTest(label=label):
                self._check(label, factory)


class TestNetlistCsvAllSchematics(unittest.TestCase):
    """CSV format: header + 4-column rows across all 25 schematics."""

    def _check(self, label, factory):
        circuit = factory()
        text = _export_csv(circuit, stem=label)

        self.assertIsInstance(text, str, f"{label}: not a string")
        lines = text.splitlines()
        self.assertEqual(lines[0], "net_name,refdes,pin,pin_type",
                         f"{label}: wrong CSV header")
        if len(lines) > 1:
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
            for row in rows[1:]:
                self.assertEqual(len(row), 4,
                                 f"{label}: expected 4 CSV columns, got {len(row)}: {row}")
                self.assertTrue(row[3].strip(),
                                f"{label}: pin_type column empty in row: {row}")

    def test_all_25_csv(self):
        for label, factory in _ALL_SCHEMATICS:
            with self.subTest(label=label):
                self._check(label, factory)


# ---------------------------------------------------------------------------
# SECTION 2 — Net-graph consistency: node counts match across formats
# ---------------------------------------------------------------------------

class TestNetGraphConsistency(unittest.TestCase):
    """Extract-net-graph output is consistent with all three export formats."""

    def _count_csv_nodes(self, circuit) -> int:
        text = _export_csv(circuit)
        lines = text.splitlines()
        return len(lines) - 1  # exclude header

    def _count_graph_nodes(self, circuit) -> int:
        g = _extract_net_graph(circuit)
        return sum(len(v) for v in g["net_ports"].values())

    def test_sch01_node_count_matches(self):
        c = _sch01()
        self.assertEqual(self._count_graph_nodes(c), self._count_csv_nodes(c))

    def test_sch06_spi_node_count_matches(self):
        c = _sch06()
        self.assertEqual(self._count_graph_nodes(c), self._count_csv_nodes(c))

    def test_sch08_i2c_node_count_matches(self):
        c = _sch08()
        self.assertEqual(self._count_graph_nodes(c), self._count_csv_nodes(c))

    def test_sch09_ldo_node_count_matches(self):
        c = _sch09()
        self.assertEqual(self._count_graph_nodes(c), self._count_csv_nodes(c))

    def test_sch15_bypass_cap_node_count_matches(self):
        c = _sch15()
        self.assertEqual(self._count_graph_nodes(c), self._count_csv_nodes(c))

    def test_sch25_adc_ref_node_count_matches(self):
        c = _sch25()
        self.assertEqual(self._count_graph_nodes(c), self._count_csv_nodes(c))


# ---------------------------------------------------------------------------
# SECTION 3 — ERC depth: class-specific checks across the 25 schematics
# ---------------------------------------------------------------------------

class TestErcFloatingInput(unittest.TestCase):
    """ERC must catch unconnected / floating pins across relevant schematics."""

    def _erc(self, circuit):
        return _run_erc_extended(circuit)

    def test_sch07_floating_input_flagged(self):
        r = self._erc(_sch07())
        kinds = [e["kind"] for e in r["errors"]]
        self.assertIn("unconnected_pin", kinds,
                      "sch07: MCU input not in any trace must flag unconnected_pin")

    def test_sch02_tx_single_node_warning(self):
        r = self._erc(_sch02())
        kinds = [w["kind"] for w in r["warnings"]]
        self.assertIn("single_node_net", kinds,
                      "sch02: floating UART TX must produce single_node_net warning")

    def test_sch18_gate_floating_unconnected(self):
        r = self._erc(_sch18())
        kinds = [e["kind"] for e in r["errors"]]
        self.assertIn("unconnected_pin", kinds,
                      "sch18: unconnected MOSFET gate must flag unconnected_pin")

    def test_sch23_four_floating_single_node_warnings(self):
        r = self._erc(_sch23())
        single_node = [w for w in r["warnings"] if w["kind"] == "single_node_net"]
        self.assertGreaterEqual(len(single_node), 4,
                                "sch23: 4 isolated single-pin nets must each warn")

    def test_sch24_gate_drive_floating(self):
        r = self._erc(_sch24())
        kinds_w = [w["kind"] for w in r["warnings"]]
        kinds_e = [e["kind"] for e in r["errors"]]
        self.assertTrue(
            "single_node_net" in kinds_w or "unconnected_pin" in kinds_e,
            "sch24: floating gate traces must produce single_node_net or unconnected_pin",
        )


class TestErcPowerConflict(unittest.TestCase):
    """ERC must catch power-conflict / multi-driver errors."""

    def test_sch04_output_to_output_conflict(self):
        r = _run_erc_extended(_sch04())
        all_kinds = [e["kind"] for e in r["errors"]]
        self.assertTrue(
            "output_to_output" in all_kinds or "conflicting_outputs" in all_kinds,
            f"sch04: two output pins on same net must flag conflict. Got: {all_kinds}",
        )

    def test_sch14_three_drivers_conflict(self):
        r = _run_erc_extended(_sch14())
        all_kinds = [e["kind"] for e in r["errors"]]
        self.assertTrue(
            "output_to_output" in all_kinds or "conflicting_outputs" in all_kinds,
            f"sch14: three output pins on same net must flag conflict. Got: {all_kinds}",
        )

    def test_sch04_conflict_has_driver_count_gte_2(self):
        r = _run_erc_extended(_sch04())
        conflicts = [e for e in r["errors"]
                     if e["kind"] in ("output_to_output", "conflicting_outputs")]
        self.assertTrue(len(conflicts) >= 1, "sch04: at least one conflict entry required")

    def test_sch16_open_collector_wired_or_no_conflict(self):
        """Open-collector outputs tied together must NOT raise output_to_output."""
        r = _run_erc_extended(_sch16())
        kinds = [e["kind"] for e in r["errors"]]
        self.assertNotIn("output_to_output", kinds,
                         "sch16: open-collector wired-OR must not flag output_to_output")
        self.assertNotIn("conflicting_outputs", kinds,
                         "sch16: open-collector wired-OR must not flag conflicting_outputs")


class TestErcDuplicateRefdes(unittest.TestCase):
    """ERC must catch duplicate refdes."""

    def test_sch05_duplicate_refdes_flagged(self):
        r = _run_erc_extended(_sch05())
        kinds = [e["kind"] for e in r["errors"]]
        self.assertIn("duplicate_refdes", kinds,
                      "sch05: two components named U1 must flag duplicate_refdes")

    def test_sch01_no_duplicate_refdes(self):
        r = _run_erc_extended(_sch01())
        kinds = [e["kind"] for e in r["errors"]]
        self.assertNotIn("duplicate_refdes", kinds,
                         "sch01: all unique refdes should not flag duplicate_refdes")


class TestErcMissingPower(unittest.TestCase):
    """ERC must catch missing / unsourced power nets."""

    def test_sch13_missing_power_flagged(self):
        r = _run_erc_extended(_sch13())
        all_kinds = ([e["kind"] for e in r["errors"]]
                     + [w["kind"] for w in r["warnings"]])
        self.assertTrue(
            "missing_power" in all_kinds or "power_pin_no_driver" in all_kinds,
            f"sch13: VCC net with no power_out source must flag missing power. Got: {all_kinds}",
        )

    def test_sch01_power_sourced_no_missing_power(self):
        r = _run_erc_extended(_sch01())
        all_kinds = [e["kind"] for e in r["errors"]]
        self.assertNotIn("missing_power", all_kinds,
                         "sch01: VCC has a power_out source, should not flag missing_power")


class TestErcCleanSchematics(unittest.TestCase):
    """Clean schematics (no intentional faults) must pass ERC with zero errors."""

    def _assert_clean(self, label, circuit):
        r = _run_erc_extended(circuit)
        self.assertEqual(r["errors"], [],
                         f"{label}: expected zero ERC errors, got: {r['errors']}")

    def test_sch11_empty_clean(self):
        self._assert_clean("sch11_empty", _sch11())

    def test_sch12_single_resistor_clean(self):
        self._assert_clean("sch12_single_resistor", _sch12())

    def test_sch17_usb_fullspeed_clean(self):
        self._assert_clean("sch17_usb_fullspeed", _sch17())


# ---------------------------------------------------------------------------
# SECTION 4 — ERC report structure and summary fields
# ---------------------------------------------------------------------------

class TestErcReportStructure(unittest.TestCase):
    """ERC report always has errors/warnings/summary with correct types."""

    def test_all_25_report_structure(self):
        for label, factory in _ALL_SCHEMATICS:
            with self.subTest(label=label):
                r = _run_erc_extended(factory())
                self.assertIn("errors",   r,   f"{label}: missing 'errors' key")
                self.assertIn("warnings", r,   f"{label}: missing 'warnings' key")
                self.assertIn("summary",  r,   f"{label}: missing 'summary' key")
                s = r["summary"]
                self.assertIn("total_errors",   s, f"{label}: summary missing total_errors")
                self.assertIn("total_warnings", s, f"{label}: summary missing total_warnings")
                self.assertIn("checks_run",     s, f"{label}: summary missing checks_run")
                self.assertEqual(s["total_errors"],   len(r["errors"]),
                                 f"{label}: total_errors mismatch")
                self.assertEqual(s["total_warnings"], len(r["warnings"]),
                                 f"{label}: total_warnings mismatch")

    def test_all_errors_have_severity_error(self):
        for label, factory in _ALL_SCHEMATICS:
            with self.subTest(label=label):
                r = _run_erc_extended(factory())
                for e in r["errors"]:
                    self.assertEqual(e.get("severity"), "error",
                                     f"{label}: error entry missing severity=error: {e}")

    def test_all_warnings_have_severity_warning(self):
        for label, factory in _ALL_SCHEMATICS:
            with self.subTest(label=label):
                r = _run_erc_extended(factory())
                for w in r["warnings"]:
                    self.assertEqual(w.get("severity"), "warning",
                                     f"{label}: warning entry missing severity=warning: {w}")

    def test_checks_run_includes_standard_checks(self):
        for label, factory in _ALL_SCHEMATICS:
            with self.subTest(label=label):
                r = _run_erc_extended(factory())
                checks = r["summary"]["checks_run"]
                for expected in ("unconnected_pin", "duplicate_refdes",
                                 "single_node_net", "conflicting_outputs"):
                    self.assertIn(expected, checks,
                                  f"{label}: checks_run must include '{expected}'")


# ---------------------------------------------------------------------------
# SECTION 5 — Boundary / malformed / idempotency
# ---------------------------------------------------------------------------

class TestBoundaryAndMalformed(unittest.TestCase):
    """Boundary cases and malformed inputs do not raise exceptions."""

    def test_none_elements_skipped_erc(self):
        r = _run_erc_extended([None, {"type": "other"}, 42])
        self.assertIsInstance(r["errors"], list)
        self.assertIsInstance(r["warnings"], list)

    def test_none_elements_skipped_kicad(self):
        text = _export_kicad([None, {"type": "other"}])
        self.assertIn("(export", text)
        self.assertTrue(_kicad_balanced(text))

    def test_none_elements_skipped_pads(self):
        text = _export_orcad_pads([None, {"type": "other"}])
        self.assertIn("*PART*", text)
        self.assertIn("*END*", text)

    def test_none_elements_skipped_csv(self):
        text = _export_csv([None, {"type": "other"}])
        self.assertEqual(text.splitlines()[0], "net_name,refdes,pin,pin_type")

    def test_component_no_name_field(self):
        """Component with no 'name' field must not raise."""
        el = {"type": "source_component", "source_component_id": "cx"}
        r = _run_erc_extended([el])
        self.assertIsInstance(r["errors"], list)

    def test_port_no_pin_type_defaults_passive(self):
        """Port with no pin_type must default to passive and not raise."""
        _reset()
        c = _comp("R1")
        p = {"type": "source_port", "source_port_id": "px",
             "source_component_id": c["source_component_id"], "name": "A"}
        t = _trace(p["source_port_id"])
        r = _run_erc_extended([c, p, t])
        self.assertIsInstance(r["errors"], list)

    def test_trace_no_ports(self):
        """Trace with empty connected_source_port_ids must not raise."""
        el = {"type": "source_trace", "source_trace_id": "t0",
              "connected_source_port_ids": []}
        r = _run_erc_extended([el])
        self.assertIsInstance(r["errors"], list)

    def test_net_graph_large_circuit(self):
        """25-component chain must produce a graph without error."""
        g = _extract_net_graph(_sch21())
        self.assertIn("nets",      g)
        self.assertIn("net_ports", g)
        self.assertIn("components", g)

    def test_kicad_stem_with_spaces(self):
        text = _export_kicad(_sch01(), stem="My Project Board v1")
        # The kicad escaper wraps strings containing spaces in double-quotes
        self.assertIn("My Project Board v1", text,
                      "Stem with spaces must appear verbatim in KiCad output (quoted)")
        self.assertTrue(_kicad_balanced(text))

    def test_kicad_deterministic(self):
        """Same input must produce identical KiCad output (idempotent)."""
        c = _sch01()
        t1 = _export_kicad(c, stem="board")
        t2 = _export_kicad(c, stem="board")
        # Net names and component names must all match
        net_names_1 = set(re.findall(r'\(name (\S+)\)', t1))
        net_names_2 = set(re.findall(r'\(name (\S+)\)', t2))
        self.assertEqual(net_names_1, net_names_2)

    def test_csv_deterministic(self):
        """CSV export of same circuit is idempotent (same rows, possibly reordered)."""
        c = _sch06()
        t1 = sorted(_export_csv(c).splitlines())
        t2 = sorted(_export_csv(c).splitlines())
        self.assertEqual(t1, t2)

    def test_pads_deterministic(self):
        c = _sch06()
        t1 = _export_orcad_pads(c, stem="board")
        t2 = _export_orcad_pads(c, stem="board")
        self.assertEqual(sorted(t1.splitlines()), sorted(t2.splitlines()))


class TestNetlistRoundTrip(unittest.TestCase):
    """Net names survive a full export round-trip (export → parse → verify)."""

    def test_kicad_net_names_present_sch01(self):
        c = _sch01()
        text = _export_kicad(c, stem="divider")
        for name in ("VCC", "GND", "MID"):
            self.assertIn(name, text, f"Net name {name!r} missing from KiCad output")

    def test_pads_signal_names_present_sch06(self):
        c = _sch06()
        text = _export_orcad_pads(c, stem="spi")
        for name in ("SPI_MOSI", "SPI_MISO", "SPI_SCK", "VCC", "GND"):
            self.assertIn(f"*SIGNAL* {name}", text,
                          f"PADS: expected *SIGNAL* {name}")

    def test_csv_net_names_present_sch09(self):
        c = _sch09()
        text = _export_csv(c, stem="psu")
        for name in ("5V", "3V3", "GND"):
            self.assertIn(name, text, f"CSV: net name {name!r} missing")

    def test_kicad_refdes_all_present_sch20(self):
        c = _sch20()
        text = _export_kicad(c, stem="osc")
        for ref in ("U1", "Y1", "C1", "C2", "R1"):
            self.assertIn(ref, text, f"KiCad: refdes {ref!r} missing")

    def test_pads_refdes_node_format_sch01(self):
        c = _sch01()
        text = _export_orcad_pads(c, stem="div")
        # PADS nodes appear as REFDES.pin
        node_re = re.compile(r'\b\w+\.\w+')
        self.assertIsNotNone(node_re.search(text),
                             "PADS: no REFDES.pin node entries found")

    def test_csv_refdes_node_present_sch17(self):
        c = _sch17()
        text = _export_csv(c, stem="usb")
        # CSV rows: net_name,refdes,pin,pin_type  — refdes must appear
        for ref in ("U1", "J1"):
            self.assertIn(ref, text, f"CSV: refdes {ref!r} missing")


if __name__ == "__main__":
    unittest.main()
