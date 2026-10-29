"""Sumber data sensor: Termux:API (HP Android asli) atau simulator (laptop/latihan)."""
from __future__ import annotations

import json
import random
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


class SensorError(RuntimeError):
    pass


@dataclass(frozen=True)
class SensorSample:
    seconds: float
    acceleration: Tuple[float, float, float]
    light: Optional[float] = None        # lux
    proximity: Optional[float] = None    # cm


def _json_objects(text: str) -> List[dict]:
    """termux-sensor bisa mencetak beberapa objek JSON berurutan; ambil semuanya."""
    decoder = json.JSONDecoder()
    text = text.strip()
    idx, out = 0, []
    while idx < len(text):
        try:
            obj, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            out.append(obj)
        idx = end
        while idx < len(text) and text[idx].isspace():
            idx += 1
    return out


def _pick(names: List[str], keyword: str) -> Optional[str]:
    """Cari nama sensor yang mengandung keyword; utamakan varian Non-wakeup."""
    candidates = [n for n in names if keyword in n.lower() and "uncalibrated" not in n.lower()]
    candidates.sort(key=lambda n: 0 if "non-wakeup" in n.lower() else 1)
    return candidates[0] if candidates else None


class TermuxSource:
    name = "android"

    def __init__(self, want_light: bool = True, want_proximity: bool = False):
        try:
            out = subprocess.run(["termux-sensor", "-l"], capture_output=True, text=True,
                                 timeout=12, check=True).stdout
            names = [str(n) for n in json.loads(out).get("sensors", [])]
        except (subprocess.SubprocessError, OSError, ValueError) as exc:
            raise SensorError(f"termux-sensor -l gagal: {exc}") from exc

        self.accel_name = _pick(names, "accelerometer")
        if not self.accel_name:
            raise SensorError("Accelerometer tidak ditemukan di HP ini")
        self.light_name = _pick(names, "light") if want_light else None
        self.prox_name = _pick(names, "proximity") if want_proximity else None
        if want_light and not self.light_name:
            print("[SENSOR] Peringatan: light sensor tidak ditemukan")
        if want_proximity and not self.prox_name:
            print("[SENSOR] Peringatan: proximity sensor tidak ditemukan")
        print(f"[SENSOR] accel={self.accel_name} | light={self.light_name} | proximity={self.prox_name}")
        # sensor 'on-change' kadang tidak mengirim event; simpan nilai terakhir
        self._light: Optional[float] = None
        self._prox: Optional[float] = None

    def read(self) -> SensorSample:
        wanted = [n for n in (self.accel_name, self.light_name, self.prox_name) if n]
        try:
            proc = subprocess.run(["termux-sensor", "-s", ",".join(wanted), "-n", "1"],
                                  capture_output=True, text=True, timeout=12, check=True)
        except (subprocess.SubprocessError, OSError) as exc:
            raise SensorError(f"termux-sensor gagal: {exc}") from exc

        data: Dict[str, dict] = {}
        for obj in _json_objects(proc.stdout):
            data.update(obj)

        accel = data.get(self.accel_name, {}).get("values")
        if not accel or len(accel) < 3:
            raise SensorError("Output accelerometer kosong - izinkan Termux:API di pengaturan Android")
        if self.light_name:
            vals = data.get(self.light_name, {}).get("values")
            if vals:
                self._light = float(vals[0])
        if self.prox_name:
            vals = data.get(self.prox_name, {}).get("values")
            if vals:
                self._prox = float(vals[0])
        return SensorSample(time.monotonic(), tuple(float(v) for v in accel[:3]), self._light, self._prox)


class SimulatorSource:
    """Skenario: still | shake | open | demo (siklus otomatis ~60 detik)."""
    name = "simulator"

    def __init__(self, scenario: str = "demo"):
        self.scenario = scenario
        self._t0 = time.monotonic()
        self.light_name = "sim-light"
        self.prox_name = "sim-proximity"

    def _phase(self, t: float) -> str:
        if self.scenario == "shake":
            return "shake" if t >= 6 else "still"
        if self.scenario == "open":
            return "open" if t >= 6 else "still"
        if self.scenario == "demo":
            c = t % 60
            if 15 <= c < 25:
                return "shake"
            if 35 <= c < 50:
                return "open"
        return "still"

    def read(self) -> SensorSample:
        now = time.monotonic()
        phase = self._phase(now - self._t0)
        x, y, z = random.gauss(0, 0.03), random.gauss(0, 0.03), 9.81 + random.gauss(0, 0.03)
        if phase == "shake":
            x += random.gauss(0, 2.5)
            y += random.gauss(0, 2.5)
            z += random.gauss(0, 2.5)
        lux, prox = max(0.0, random.gauss(1.5, 0.4)), 0.0
        if phase == "open":
            lux, prox = max(0.0, random.gauss(150, 15)), 5.0
        return SensorSample(now, (x, y, z), lux, prox)


def make_source(kind: str = "auto", scenario: str = "demo",
                want_light: bool = True, want_proximity: bool = False):
    if kind == "auto":
        kind = "termux" if shutil.which("termux-sensor") else "simulator"
    if kind == "termux":
        return TermuxSource(want_light, want_proximity)
    return SimulatorSource(scenario)
