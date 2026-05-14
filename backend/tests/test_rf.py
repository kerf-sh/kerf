import unittest
import numpy as np
import tempfile
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geom.rf_analysis import (
    RFNetwork, vswr, return_loss, insertion_loss,
    impedance_from_s11, match_target, cascade_2ports
)
from geom.touchstone import read_touchstone, write_touchstone, read_touchstone_from_string
from geom.smith_chart import smith_to_cartesian, cartesian_to_smith


class TestRFNetwork(unittest.TestCase):
    def test_s_parameters_shape(self):
        freq = np.linspace(1e9, 10e9, 101)
        s_params = np.zeros((2, 2, 101), dtype=complex)
        s_params[0, 0, :] = 0.1 + 0.1j
        s_params[1, 1, :] = 0.2 + 0.2j
        s_params[0, 1, :] = 0.01
        s_params[1, 0, :] = 0.01
        network = RFNetwork(freq, s_params, z0=50.0)
        self.assertEqual(network.s_parameters().shape, (2, 2, 101))

    def test_vswr(self):
        freq = np.linspace(1e9, 10e9, 10)
        s_params = np.zeros((2, 2, 10), dtype=complex)
        s_params[0, 0, :] = 0.5
        network = RFNetwork(freq, s_params)
        vswr_result = network.vswr()
        self.assertEqual(len(vswr_result), 10)
        self.assertTrue(np.all(vswr_result > 1))

    def test_vswr_perfect_match(self):
        result = vswr(0.0)
        self.assertEqual(result, 1.0)

    def test_vswr_open(self):
        result = vswr(1.0)
        self.assertEqual(result, float('inf'))

    def test_return_loss(self):
        result = return_loss(-10.0)
        self.assertAlmostEqual(result, 10.0)

    def test_insertion_loss(self):
        result = insertion_loss(-3.0)
        self.assertAlmostEqual(result, 3.0)

    def test_impedance_from_s11(self):
        z = impedance_from_s11(0.0, 50.0)
        self.assertEqual(z, 50.0)
        z = impedance_from_s11(0.5, 50.0)
        self.assertAlmostEqual(z, 150.0)

    def test_match_target(self):
        s = complex(0.1, 0.1)
        z_target = complex(75, 0)
        result = match_target(s, z_target, 50.0)
        self.assertIsInstance(result, float)

    def test_stability_factor_k(self):
        freq = np.linspace(1e9, 10e9, 10)
        s_params = np.zeros((2, 2, 10), dtype=complex)
        s_params[0, 0, :] = 0.1
        s_params[1, 1, :] = 0.1
        s_params[0, 1, :] = 0.01
        s_params[1, 0, :] = 10.0
        network = RFNetwork(freq, s_params)
        k = network.stability_factor_k()
        self.assertEqual(len(k), 10)

    def test_cascade_2ports(self):
        freq = np.linspace(1e9, 10e9, 10)
        s1 = np.zeros((2, 2, 10), dtype=complex)
        s1[0, 0, :] = 0.1
        s1[1, 1, :] = 0.1
        s1[0, 1, :] = 0.9
        s1[1, 0, :] = 0.9
        nw1 = RFNetwork(freq, s1)
        s2 = np.zeros((2, 2, 10), dtype=complex)
        s2[0, 0, :] = 0.2
        s2[1, 1, :] = 0.2
        s2[0, 1, :] = 0.8
        s2[1, 0, :] = 0.8
        nw2 = RFNetwork(freq, s2)
        cascaded = cascade_2ports(nw1, nw2)
        self.assertEqual(cascaded._n_ports, 2)
        self.assertEqual(len(cascaded.freq), 10)


class TestTouchstone(unittest.TestCase):
    def test_read_write_s2p(self):
        freq = np.linspace(1e9, 2e9, 5)
        s_params = np.zeros((2, 2, 5), dtype=complex)
        for i in range(5):
            s_params[0, 0, i] = 0.1 + 0.1j * i
            s_params[1, 1, i] = 0.2 + 0.2j * i
            s_params[0, 1, i] = 0.01 * (i + 1)
            s_params[1, 0, i] = 0.01 * (i + 1) + 0.1j
        network = RFNetwork(freq, s_params, z0=50.0)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.s2p', delete=False) as f:
            tmp_path = f.name
        try:
            write_touchstone(network, tmp_path, freq_unit="GHz")
            network_read = read_touchstone(tmp_path)
            self.assertEqual(network_read._n_ports, 2)
            self.assertEqual(len(network_read.freq), 5)
        finally:
            os.unlink(tmp_path)

    def test_parse_s2p_string(self):
        content = """# Hz GHz S RI R 50
1.0e9 0.1 0.0 0.01 0.0 0.01 0.0 0.1 0.0
2.0e9 0.2 0.0 0.02 0.0 0.02 0.0 0.2 0.0
"""
        network = read_touchstone_from_string(content)
        self.assertEqual(network._n_ports, 2)
        self.assertEqual(len(network.freq), 2)


class TestSmithChart(unittest.TestCase):
    def test_smith_to_cartesian(self):
        z = complex(50, 0)
        x, y = smith_to_cartesian(z)
        self.assertAlmostEqual(x, 0.0)
        self.assertAlmostEqual(y, 0.0)

    def test_smith_to_cartesian_open(self):
        z = complex(1e12, 0)
        x, y = smith_to_cartesian(z)
        self.assertAlmostEqual(x, 1.0, places=2)
        self.assertAlmostEqual(y, 0.0)

    def test_smith_to_cartesian_short(self):
        z = complex(1e-6, 0)
        x, y = smith_to_cartesian(z)
        self.assertAlmostEqual(x, -1.0, places=2)
        self.assertAlmostEqual(y, 0.0)

    def test_roundtrip(self):
        z = complex(75, 30)
        x, y = smith_to_cartesian(z)
        z_back = cartesian_to_smith(x, y)
        self.assertAlmostEqual(z.real, z_back.real, places=1)
        self.assertAlmostEqual(z.imag, z_back.imag, places=1)


class TestRFCalculations(unittest.TestCase):
    def test_vswr_calculation(self):
        self.assertAlmostEqual(vswr(0.0), 1.0)
        self.assertAlmostEqual(vswr(0.5), 3.0)
        self.assertEqual(vswr(1.0), float('inf'))

    def test_return_loss_calculation(self):
        self.assertAlmostEqual(return_loss(-10.0), 10.0)
        self.assertAlmostEqual(return_loss(-20.0), 20.0)

    def test_insertion_loss_calculation(self):
        self.assertAlmostEqual(insertion_loss(-3.0), 3.0)
        self.assertAlmostEqual(insertion_loss(-0.5), 0.5)


if __name__ == '__main__':
    unittest.main()
