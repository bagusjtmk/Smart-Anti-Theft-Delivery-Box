"""Pengolahan data sensor.

A. Motion RMS (accelerometer)  -> intensitas guncangan kotak
B. Lid state tracker (light/proximity) -> deteksi transisi OPEN/CLOSED dengan
   threshold + hysteresis
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from math import sqrt
from typing import List, Optional, Sequence

from .sensors import SensorSample

GRAVITY = 9.81
CLOSED = "CLOSED"
OPEN = "OPEN"


# ---------------------------------------------------------------- A. RMS getaran
def motion_rms(samples: Sequence[SensorSample]) -> float:
    """magnitude = sqrt(x^2+y^2+z^2); error = magnitude - g; RMS(error)."""
    if not samples:
        return 0.0
    errors: List[float] = []
    for sample in samples:
        x, y, z = sample.acceleration
        errors.append(sqrt(x * x + y * y + z * z) - GRAVITY)
    return sqrt(sum(e * e for e in errors) / len(errors))


# ---------------------------------------------------------------- B. status tutup
def _median(values: Sequence[Optional[float]]) -> Optional[float]:
    clean = [v for v in values if v is not None]
    return statistics.median(clean) if clean else None


@dataclass(frozen=True)
class LidReading:
    state: str                    # CLOSED | OPEN
    transition: Optional[str]     # OPENED | CLOSED | None (hanya saat berubah)
    lux: Optional[float]
    proximity_cm: Optional[float]


class LidTracker:
    """Deteksi transisi status tutup kotak.

    - light     : OPEN bila lux >= open_lux; kembali CLOSED bila lux <= close_lux
                  (hysteresis supaya tidak 'berkedip' di sekitar ambang).
    - proximity : OPEN bila jarak >= far_cm (sensor menghadap tutup: dekat = tertutup).
    - either/both menggabungkan keduanya.
    Nilai tiap window = median sampel (tahan terhadap noise sesaat).
    """

    def __init__(self, mode: str, open_lux: float, close_lux: float, far_cm: float):
        self.mode = mode
        self.open_lux = open_lux
        self.close_lux = close_lux
        self.far_cm = far_cm
        self.state = CLOSED

    def update(self, samples: Sequence[SensorSample]) -> LidReading:
        lux = _median([s.light for s in samples])
        prox = _median([s.proximity for s in samples])

        votes: List[bool] = []   # True = sensor bilang "terbuka"
        if self.mode in ("light", "either", "both") and lux is not None:
            if self.state == CLOSED:
                votes.append(lux >= self.open_lux)
            else:
                votes.append(lux > self.close_lux)
        if self.mode in ("proximity", "either", "both") and prox is not None:
            votes.append(prox >= self.far_cm)

        transition = None
        if votes:
            is_open = all(votes) if self.mode == "both" else any(votes)
            new_state = OPEN if is_open else CLOSED
            if new_state != self.state:
                transition = "OPENED" if new_state == OPEN else "CLOSED"
                self.state = new_state
        return LidReading(self.state, transition, lux, prox)
