import numpy as np


def smith_to_cartesian(z: complex) -> tuple[float, float]:
    gamma = (z - 50.0) / (z + 50.0)
    return (gamma.real, gamma.imag)


def impedance_from_gamma(gamma: complex, z0: float = 50.0) -> complex:
    return z0 * (1 + gamma) / (1 - gamma)


def cartesian_to_smith(x: float, y: float) -> complex:
    gamma = complex(x, y)
    return impedance_from_gamma(gamma)


def _draw_smith_chart_grid(ax, annotations: bool = True):
    real_vals = np.linspace(0, 1, 11)
    for r in real_vals:
        if r == 0:
            circle = plt.Circle((0, 0), 1.0, fill=False, color='gray', linewidth=0.5, alpha=0.5)
        else:
            center = r / (1 + r)
            radius = 1.0 / (1 + r)
            circle = plt.Circle((center, 0), radius, fill=False, color='gray', linewidth=0.5, alpha=0.5)
        ax.add_patch(circle)
    imag_vals = np.linspace(-1, 1, 21)
    for x in imag_vals:
        if x == 0:
            ax.axvline(x=1, color='gray', linewidth=0.5, alpha=0.5)
        else:
            r = 1.0 / abs(x)
            center = 0.5 * (1 + x / abs(x))
            radius = r / 2.0
            arc_x = center - radius if x < 0 else center + radius
            arc = plt.Circle((arc_x, 0.5 if x > 0 else -0.5), radius,
                           fill=False, color='gray', linewidth=0.5, alpha=0.5)
            ax.add_patch(arc)
    ax.axhline(y=0, color='gray', linewidth=0.5, alpha=0.3)
    ax.axvline(x=0, color='gray', linewidth=0.5, alpha=0.3)


def smith_chart(ax, network, param: str = "S11", style: str = "log_magnitude"):
    import matplotlib.pyplot as plt
    param_map = {
        "S11": (0, 0),
        "S12": (0, 1),
        "S21": (1, 0),
        "S22": (1, 1),
    }
    if param not in param_map:
        raise ValueError(f"Unknown param: {param}. Must be one of {list(param_map.keys())}")
    i, j = param_map[param]
    s_data = network.s_params[i, j, :]
    ax.set_aspect('equal')
    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-1.1, 1.1)
    ax.axis('off')
    _draw_smith_chart_grid(ax)
    if style == "log_magnitude":
        mag = np.abs(s_data)
        phase = np.angle(s_data)
        x_data = mag * np.cos(phase)
        y_data = mag * np.sin(phase)
        ax.plot(x_data, y_data, '-', color='#22d3ee', linewidth=1.0, alpha=0.7)
        for idx in range(0, len(s_data), max(1, len(s_data) // 20)):
            ax.plot(x_data[idx], y_data[idx], 'o', markersize=4, color='#22d3ee', zorder=5)
    elif style == "phase":
        phase = np.angle(s_data, deg=True)
        for idx in range(len(s_data)):
            gamma = s_data[idx]
            ax.plot(gamma.real, gamma.imag, 'o', markersize=3, color='blue', zorder=5)
        ax.set_title(f"{param} Phase", fontsize=10)
    elif style == "real":
        for idx in range(len(s_data)):
            gamma = s_data[idx]
            ax.plot(gamma.real, gamma.imag, 'o', markersize=3, color='green', zorder=5)
        ax.set_title(f"{param} Real Part", fontsize=10)
    elif style == "imag":
        for idx in range(len(s_data)):
            gamma = s_data[idx]
            ax.plot(gamma.real, gamma.imag, 'o', markersize=3, color='red', zorder=5)
        ax.set_title(f"{param} Imaginary Part", fontsize=10)
    elif style == "vswr":
        vswr = (1 + np.abs(s_data)) / (1 - np.abs(s_data))
        for idx in range(len(s_data)):
            gamma = s_data[idx]
            ax.plot(gamma.real, gamma.imag, 'o', markersize=4, color='orange', zorder=5)
        ax.set_title(f"{param} VSWR", fontsize=10)
    else:
        raise ValueError(f"Unknown style: {style}")
    ax.set_title(f"Smith Chart - {param}", fontsize=10, pad=8)
    return ax


def generate_smith_chart_svg(freq, s11_data, port_z0=50.0, freq_unit="GHz"):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import tempfile
    import os
    fig, ax = plt.subplots(1, 1, figsize=(6, 6), dpi=120)
    ax.set_aspect('equal')
    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-1.1, 1.1)
    ax.axis('off')
    _draw_smith_chart_grid(ax)
    if len(freq) > 0 and len(s11_data) == len(freq):
        s11_complex = [complex(s.get('re', 0), s.get('im', 0)) if isinstance(s, dict) else s
                      for s in s11_data]
        marker_count = min(len(freq), 20)
        step = max(1, len(freq) // marker_count)
        indices = list(range(0, len(freq), step))
        cmap = plt.cm.viridis
        for i, idx in enumerate(indices):
            z = s11_complex[idx]
            if z != 0:
                gamma = z / port_z0 if isinstance(z, (int, float)) else z
            else:
                gamma = 0
            x_pos = gamma.real if hasattr(gamma, 'real') else gamma
            y_pos = gamma.imag if hasattr(gamma, 'imag') else 0
            color = cmap(i / len(indices))
            ax.plot(x_pos, y_pos, 'o', markersize=4, color=color, zorder=5)
        s11_x = [s.real if hasattr(s, 'real') else 0 for s in s11_complex]
        s11_y = [s.imag if hasattr(s, 'imag') else 0 for s in s11_complex]
        ax.plot(s11_x, s11_y, '-', color='#22d3ee', linewidth=1.0, alpha=0.7, zorder=4)
    ax.set_title(f"S11 Smith Chart ({freq_unit})", fontsize=10, pad=8)
    tmp = tempfile.NamedTemporaryFile(suffix='.svg', delete=False)
    tmp.close()
    try:
        plt.savefig(tmp.name, format='svg', bbox_inches='tight', transparent=True)
        with open(tmp.name, 'r', encoding='utf-8') as f:
            svg_content = f.read()
    finally:
        os.unlink(tmp.name)
    plt.close(fig)
    return svg_content
