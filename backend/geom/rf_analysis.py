import numpy as np


class RFNetwork:
    def __init__(self, freq: np.ndarray, s_params: np.ndarray, z0: float = 50.0):
        self.freq = np.asarray(freq)
        n_ports = s_params.shape[0]
        self.s_params = np.asarray(s_params)
        self.z0 = z0
        self._n_ports = n_ports

    def s_parameters(self) -> np.ndarray:
        return self.s_params

    def z_parameters(self) -> np.ndarray:
        z = np.zeros_like(self.s_params, dtype=complex)
        for i in range(self._n_ports):
            for j in range(self._n_ports):
                delta = np.ones_like(self.s_params[0, 0], dtype=complex)
                for k in range(self._n_ports):
                    if k != i:
                        delta = delta * (np.ones_like(self.s_params[0, 0]) - self.s_params[k, k])
                s_ij = self.s_params[i, j]
                z[i, j] = self.z0 * (s_ij + self.s_params[i, i] * self.s_params[j, j] - self.s_params[i, i] - self.s_params[j, j] + delta) / (1 - np.sum([self.s_params[k, k] for k in range(self._n_ports)], axis=0) + np.prod([self.s_params[k, k] for k in range(self._n_ports)], axis=0))
        return z

    def y_parameters(self) -> np.ndarray:
        y = np.zeros_like(self.s_params, dtype=complex)
        for i in range(self._n_ports):
            for j in range(self._n_ports):
                y[i, j] = (1 / self.z0) * ((np.eye(self._n_ports) - self.s_params).dot(np.linalg.inv(np.eye(self._n_ports) + self.s_params)))[i, j]
        return y

    def stability_factor_k(self) -> np.ndarray:
        if self._n_ports != 2:
            return np.array([np.nan] * len(self.freq))
        s = self.s_params
        k = np.zeros(len(self.freq))
        for idx in range(len(self.freq)):
            s11 = s[0, 0, idx]
            s12 = s[0, 1, idx]
            s21 = s[1, 0, idx]
            s22 = s[1, 1, idx]
            delta = s11 * s22 - s12 * s21
            denom = 1 - np.abs(s11)**2 - np.abs(s22)**2 + np.abs(delta)**2
            if denom > 0:
                k_val = (1 - np.abs(s11)**2 - np.abs(s22)**2 + np.abs(delta)**2) / (2 * np.abs(s12 * s21))
                k[idx] = max(0, k_val) if np.isfinite(k_val) else np.nan
            else:
                k[idx] = np.nan
        return k

    def max_gain(self) -> np.ndarray:
        if self._n_ports != 2:
            return np.array([np.nan] * len(self.freq))
        g_max = np.zeros(len(self.freq))
        for idx in range(len(self.freq)):
            s11 = self.s_params[0, 0, idx]
            s12 = self.s_params[0, 1, idx]
            s21 = self.s_params[1, 0, idx]
            s22 = self.s_params[1, 1, idx]
            k = self.stability_factor_k()[idx]
            if k > 1:
                msg = np.abs(s21 / s12) * (k - np.sqrt(k**2 - 1))
                g_max[idx] = 10 * np.log10(max(0, msg)) if msg > 0 else np.nan
            else:
                g_max[idx] = np.nan
        return g_max

    def noise_figure(self) -> np.ndarray:
        if self._n_ports != 2:
            return np.array([np.nan] * len(self.freq))
        nf = np.zeros(len(self.freq))
        for idx in range(len(self.freq)):
            s11 = self.s_params[0, 0, idx]
            s21 = self.s_params[1, 0, idx]
            s12 = self.s_params[0, 1, idx]
            s22 = self.s_params[1, 1, idx]
            if np.abs(s21) > 1e-12 and np.abs(s12) > 1e-12:
                g = np.abs(s21)**2 / (1 - np.abs(s11)**2) if np.abs(s11) < 1 else np.nan
                if np.isfinite(g) and g > 0:
                    nf[idx] = 1 + 4 * self.z0 * np.abs(s12 * s11) / (np.abs(s21) * (1 - np.abs(s11)**2))
                else:
                    nf[idx] = np.nan
            else:
                nf[idx] = np.nan
        return nf

    def vswr(self) -> np.ndarray:
        if self._n_ports < 1:
            return np.array([np.nan] * len(self.freq))
        vswr = np.zeros(len(self.freq))
        for idx in range(len(self.freq)):
            s11_mag = np.abs(self.s_params[0, 0, idx])
            if s11_mag < 1.0:
                vswr[idx] = (1 + s11_mag) / (1 - s11_mag)
            else:
                vswr[idx] = np.inf
        return vswr

    def return_loss_db(self) -> np.ndarray:
        if self._n_ports < 1:
            return np.array([np.nan] * len(self.freq))
        rl = np.zeros(len(self.freq))
        for idx in range(len(self.freq)):
            s11_mag = np.abs(self.s_params[0, 0, idx])
            if s11_mag > 0:
                rl[idx] = -20 * np.log10(s11_mag)
            else:
                rl[idx] = np.inf
        return rl

    def insertion_loss_db(self) -> np.ndarray:
        if self._n_ports < 2:
            return np.array([np.nan] * len(self.freq))
        il = np.zeros(len(self.freq))
        for idx in range(len(self.freq)):
            s21_mag = np.abs(self.s_params[1, 0, idx])
            if s21_mag > 0:
                il[idx] = -20 * np.log10(s21_mag)
            else:
                il[idx] = np.inf
        return il


def vswr(s: float) -> float:
    if abs(s) >= 1.0:
        return float('inf')
    return (1 + abs(s)) / (1 - abs(s))


def return_loss(s_db: float) -> float:
    return -s_db


def insertion_loss(s21_db: float) -> float:
    return -s21_db


def impedance_from_s11(s11: complex, z0: float = 50.0) -> complex:
    return z0 * (1 + s11) / (1 - s11)


def match_target(s: complex, z_target: complex, z0: float = 50.0) -> float:
    z_measured = impedance_from_s11(s, z0)
    gamma_target = (z_target - z0) / (z_target + z0)
    gamma_measured = (z_measured - z0) / (z_measured + z0)
    if np.abs(gamma_target) < 1e-12:
        return 0.0
    return 20 * np.log10(np.abs(gamma_measured - gamma_target) + 1e-12)


def cascade_2ports(nw1: RFNetwork, nw2: RFNetwork) -> RFNetwork:
    if nw1._n_ports != 2 or nw2._n_ports != 2:
        raise ValueError("Both networks must be 2-port")
    if len(nw1.freq) != len(nw2.freq):
        raise ValueError("Frequency arrays must have same length")
    s_cascade = np.zeros((2, 2, len(nw1.freq)), dtype=complex)
    for idx in range(len(nw1.freq)):
        s11a = nw1.s_params[0, 0, idx]
        s12a = nw1.s_params[0, 1, idx]
        s21a = nw1.s_params[1, 0, idx]
        s22a = nw1.s_params[1, 1, idx]
        s11b = nw2.s_params[0, 0, idx]
        s12b = nw2.s_params[0, 1, idx]
        s21b = nw2.s_params[1, 0, idx]
        s22b = nw2.s_params[1, 1, idx]
        s11c = s11a + s12a * s11b * s21a / (1 - s22a * s11b)
        s12c = s12a * s12b / (1 - s22a * s11b)
        s21c = s21a * s21b / (1 - s22a * s11b)
        s22c = s22b + s11b * s22a * s21b / (1 - s22a * s11b)
        s_cascade[0, 0, idx] = s11c
        s_cascade[0, 1, idx] = s12c
        s_cascade[1, 0, idx] = s21c
        s_cascade[1, 1, idx] = s22c
    return RFNetwork(nw1.freq, s_cascade, nw1.z0)


def lumped_match(z_src: complex, z_load: complex, z0: float = 50.0) -> list[dict]:
    results = []
    r_src = z_src.real
    x_src = z_src.imag
    r_load = z_load.real
    x_load = z_load.imag
    if r_src <= 0 or r_load <= 0:
        return [{"type": "error", "message": "Resistances must be positive"}]
    q_l = np.sqrt(r_load * (r_src / r_load - 1))
    if q_l > 0:
        x_series = q_l * r_load / (q_l**2 + 1)
        l_series = x_series / (2 * np.pi * 1e9) if x_series > 0 else 0
        c_series = -1 / (x_series * 2 * np.pi * 1e9) if x_series < 0 else 0
        if l_series > 0:
            results.append({"type": "inductor", "value": l_series})
        if c_series < 0:
            results.append({"type": "capacitor", "value": abs(c_series)})
        x_shunt = -q_l * r_src
        l_shunt = x_shunt / (2 * np.pi * 1e9) if x_shunt > 0 else 0
        c_shunt = -1 / (x_shunt * 2 * np.pi * 1e9) if x_shunt < 0 else 0
        if l_shunt > 0:
            results.append({"type": "inductor", "value": l_shunt})
        if c_shunt < 0:
            results.append({"type": "capacitor", "value": abs(c_shunt)})
    q_h = np.sqrt(r_load * (1 - r_src / r_load))
    if q_h > 0 and r_src > r_load:
        x_shunt = q_h * r_load / (q_h**2 + 1)
        l_shunt = x_shunt / (2 * np.pi * 1e9) if x_shunt > 0 else 0
        c_shunt = -1 / (x_shunt * 2 * np.pi * 1e9) if x_shunt < 0 else 0
        if l_shunt > 0:
            results.append({"type": "inductor", "value": l_shunt})
        if c_shunt < 0:
            results.append({"type": "capacitor", "value": abs(c_shunt)})
        x_series = -q_h * r_load
        l_series = x_series / (2 * np.pi * 1e9) if x_series > 0 else 0
        c_series = -1 / (x_series * 2 * np.pi * 1e9) if x_series < 0 else 0
        if l_series > 0:
            results.append({"type": "inductor", "value": l_series})
        if c_series < 0:
            results.append({"type": "capacitor", "value": abs(c_series)})
    if not results:
        results.append({"type": "capacitor", "value": 1e-12})
    return results
