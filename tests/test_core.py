import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nodes.detector_service.rules import (ILLEGAL_OPEN, SAFE, SECURE, TAMPER_ALERT, BoxRules, RuleConfig)
from shared.messages import Telemetry
from shared.processing import LidTracker, motion_rms
from shared.sensors import SensorSample


def tele(rms=0.02, lid="CLOSED", lux=1.0, seq=1):
    return Telemetry.make("box1", "b1", seq, rms, lux, 0.0, lid, None)


def samples(accel=(0, 0, 9.81), light=None, prox=None, n=5):
    return [SensorSample(float(i), accel, light, prox) for i in range(n)]


class ProcessingTests(unittest.TestCase):
    def test_rms_still_is_zero(self):
        self.assertAlmostEqual(motion_rms(samples()), 0.0, places=6)

    def test_rms_offset_one(self):
        self.assertAlmostEqual(motion_rms(samples((0, 0, 10.81))), 1.0, places=6)

    def test_lid_hysteresis(self):
        t = LidTracker("light", open_lux=15, close_lux=8, far_cm=3)
        self.assertEqual(t.update(samples(light=1.0)).state, "CLOSED")
        r = t.update(samples(light=20.0))
        self.assertEqual((r.state, r.transition), ("OPEN", "OPENED"))
        r = t.update(samples(light=10.0))          # di antara 8 dan 15 -> tetap OPEN
        self.assertEqual((r.state, r.transition), ("OPEN", None))
        r = t.update(samples(light=5.0))
        self.assertEqual((r.state, r.transition), ("CLOSED", "CLOSED"))

    def test_lid_proximity_and_both(self):
        t = LidTracker("proximity", 15, 8, 3)
        self.assertEqual(t.update(samples(prox=5.0)).state, "OPEN")
        b = LidTracker("both", 15, 8, 3)
        self.assertEqual(b.update(samples(light=100.0, prox=0.0)).state, "CLOSED")
        self.assertEqual(b.update(samples(light=100.0, prox=5.0)).state, "OPEN")


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.rules = BoxRules(RuleConfig(0.7, 5.0, 10.0), armed=True, now=0.0)

    def test_disarmed_is_safe(self):
        self.rules.disarm()
        self.assertEqual(self.rules.evaluate(tele(rms=3.0, lid="OPEN"), 10).status, SAFE)

    def test_secure_when_still(self):
        self.assertEqual(self.rules.evaluate(tele(), 10).status, SECURE)

    def test_grace_ignores_motion_but_not_open(self):
        self.assertEqual(self.rules.evaluate(tele(rms=2.0), 2).status, SECURE)
        self.assertEqual(self.rules.evaluate(tele(lid="OPEN"), 3).status, ILLEGAL_OPEN)

    def test_tamper_and_hold(self):
        self.assertEqual(self.rules.evaluate(tele(rms=1.5), 10).status, TAMPER_ALERT)
        self.assertEqual(self.rules.evaluate(tele(), 12).status, TAMPER_ALERT)   # ditahan
        self.assertEqual(self.rules.evaluate(tele(), 25).status, SECURE)

    def test_illegal_open_latches_until_ack(self):
        self.assertEqual(self.rules.evaluate(tele(lid="OPEN"), 10).status, ILLEGAL_OPEN)
        self.assertEqual(self.rules.evaluate(tele(lid="CLOSED"), 30).status, ILLEGAL_OPEN)
        self.rules.acknowledge()
        self.assertEqual(self.rules.evaluate(tele(lid="CLOSED"), 31).status, SECURE)

    def test_stale_keeps_status(self):
        self.rules.evaluate(tele(rms=1.5), 10)
        d = self.rules.evaluate(tele(), 40, stale=True)
        self.assertEqual(d.status, TAMPER_ALERT)
        self.assertIn("OFFLINE", d.reason)

    def test_telemetry_roundtrip(self):
        t = tele(rms=0.5, lid="OPEN", lux=120.0)
        t2 = Telemetry.from_dict(__import__("json").loads(t.to_json()))
        self.assertEqual(t, t2)


if __name__ == "__main__":
    unittest.main()
