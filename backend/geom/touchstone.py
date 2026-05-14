import numpy as np
import re
from pathlib import Path
from geom.rf_analysis import RFNetwork


def read_touchstone(filename: str) -> RFNetwork:
    path = Path(filename)
    if not path.exists():
        raise FileNotFoundError(f"Touchstone file not found: {filename}")
    with open(path, 'r') as f:
        content = f.read()
    return _parse_touchstone_string(content)


def _parse_touchstone_string(content: str) -> RFNetwork:
    lines = content.strip().split('\n')
    freq = []
    s_params = []
    num_ports = 0
    freq_unit = "GHz"
    z0 = 50.0
    format_type = "RI"
    param_count = 0
    in_data = False
    for line in lines:
        line = line.strip()
        if not line or line.startswith('!'):
            continue
        if line.startswith('#'):
            in_data = True
            parts = line[1:].strip().split()
            for i, p in enumerate(parts):
                if p.lower() in ['hz', 'khz', 'mhz', 'ghz']:
                    freq_unit = p.lower()
                elif p.lower() == 'hz':
                    freq_unit = 'hz'
                elif p.lower() == 'khz':
                    freq_unit = 'khz'
                elif p.lower() == 'mhz':
                    freq_unit = 'mhz'
                elif p.lower() == 'ghz':
                    freq_unit = 'ghz'
            continue
        if not in_data:
            m = re.match(r'\.S(\d)P', line, re.IGNORECASE)
            if m:
                num_ports = int(m.group(1))
                param_count = num_ports * num_ports * 2 + 1
            m = re.match(r'\s*(!.*)?\s*([\d.]+)\s+([\d.]+)\s', line)
            if m and not line.startswith('!'):
                try:
                    num_ports = int(np.sqrt((len(m.group(0).split()) - 1) / 2))
                    num_ports = max(1, min(4, int(np.sqrt((len(line.split()) - 1) / 2 + 0.5))))
                except:
                    pass
            m = re.match(r'\s*[Rr]\s*[Ii]', line)
            if m:
                format_type = "RI"
            m = re.match(r'\s*[Dd]\s*[Bb]\s*[Aa]', line)
            if m:
                format_type = "dB/MA"
            m = re.match(r'\s*[Mm]\s*[Aa]', line)
            if m:
                format_type = "MA"
            continue
        values = line.split()
        if len(values) < 2:
            continue
        try:
            f_val = float(values[0])
            freq.append(f_val)
            s_vals = [float(v) for v in values[1:]]
            if param_count == 0:
                param_count = len(s_vals)
                num_ports = int(np.sqrt(param_count - 1 + 0.5))
            if format_type == "RI":
                s_complex = []
                for i in range(0, len(s_vals) - 1, 2):
                    s_complex.append(complex(s_vals[i], s_vals[i + 1]))
            elif format_type == "MA":
                s_complex = []
                for i in range(0, len(s_vals) - 1, 2):
                    mag = s_vals[i]
                    ang = s_vals[i + 1]
                    s_complex.append(mag * np.exp(1j * np.radians(ang)))
            elif format_type == "dB/MA":
                s_complex = []
                for i in range(0, len(s_vals) - 1, 2):
                    db = s_vals[i]
                    mag = 10 ** (db / 20)
                    ang = s_vals[i + 1]
                    s_complex.append(mag * np.exp(1j * np.radians(ang)))
            else:
                s_complex = [complex(0)] * (num_ports * num_ports)
            s_params.append(s_complex)
        except ValueError:
            continue
    if not freq:
        raise ValueError("No data found in Touchstone file")
    freq = np.array(freq)
    freq = _normalize_freq(freq, freq_unit)
    s_array = np.array(s_params, dtype=complex)
    n_points = len(freq)
    s_reshaped = np.zeros((num_ports, num_ports, n_points), dtype=complex)
    idx = 0
    for i in range(num_ports):
        for j in range(num_ports):
            for k in range(n_points):
                if idx < s_array.shape[1]:
                    s_reshaped[i, j, k] = s_array[k, idx]
                idx += 1
    return RFNetwork(freq, s_reshaped, z0)


def _normalize_freq(freq: np.ndarray, unit: str) -> np.ndarray:
    multipliers = {
        'hz': 1.0,
        'khz': 1e3,
        'mhz': 1e6,
        'ghz': 1e9,
    }
    if unit.lower() in multipliers:
        return freq / multipliers[unit.lower()]
    return freq


def write_touchstone(network: RFNetwork, filename: str, format: str = "s", freq_unit: str = "GHz") -> None:
    with open(filename, 'w') as f:
        f.write(f"# Hz {freq_unit.upper()} S RI R 50\n")
        n_ports = network._n_ports
        for idx in range(len(network.freq)):
            f_val = network.freq[idx]
            if freq_unit.upper() == "GHZ":
                f_val = f_val * 1e9
            elif freq_unit.upper() == "MHZ":
                f_val = f_val * 1e6
            elif freq_unit.upper() == "KHZ":
                f_val = f_val * 1e3
            line = f"{f_val:.6e}"
            for i in range(n_ports):
                for j in range(n_ports):
                    s_val = network.s_params[i, j, idx]
                    line += f" {s_val.real:.6e} {s_val.imag:.6e}"
            f.write(line + "\n")


def read_touchstone_from_string(content: str) -> RFNetwork:
    return _parse_touchstone_string(content)
