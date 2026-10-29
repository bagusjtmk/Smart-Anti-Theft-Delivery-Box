"""Rule-based sensor fusion untuk status keamanan kotak.

Masukan : telemetry Edge 1 (motion_rms dari accelerometer + lid_state dari light/proximity)
          dan mode ARM/DISARM dari pemilik.
Keluaran: salah satu dari
  SAFE          - DISARM: pemilik mengizinkan akses (mis. mengambil paket)
  SECURE        - ARM, tutup tertutup, kotak diam
  TAMPER_ALERT  - ARM, tutup tertutup tetapi kotak diguncang (>= ambang RMS)
  ILLEGAL_OPEN  - ARM, tutup terbuka (dengan/tanpa guncangan)

Prioritas: ILLEGAL_OPEN > TAMPER_ALERT > SECURE.
Latching : ILLEGAL_OPEN ditahan sampai pemilik ACK/DISARM (pencuri bisa menutup lagi);
           TAMPER_ALERT ditahan ALERT_HOLD_S detik agar tidak berkedip.
Grace    : ARM_GRACE_S detik setelah ARM, guncangan diabaikan (pemilik masih menutup kotak).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Optional

SAFE = "SAFE"
SECURE = "SECURE"
TAMPER_ALERT = "TAMPER_ALERT"
ILLEGAL_OPEN = "ILLEGAL_OPEN"
ALERT_STATES = {TAMPER_ALERT, ILLEGAL_OPEN}


@dataclass(frozen=True)
class Decision:
    status: str
    reason: str
    score: float = 0.0

    @property
    def is_alert(self) -> bool:
        return self.status in ALERT_STATES


@dataclass(frozen=True)
class RuleConfig:
    tamper_rms: float = 0.7
    arm_grace_s: float = 5.0
    alert_hold_s: float = 10.0


class BoxRules:
    def __init__(self, cfg: RuleConfig, armed: bool = True, now: float = 0.0):
        self.cfg = cfg
        self.armed = armed
        self._armed_at = now
        self._latched: Optional[Decision] = None
        self._latched_until = 0.0
        self._last = Decision(SECURE if armed else SAFE, "Menunggu telemetri Edge 1 (kotak)")

    # -- kontrol dari pemilik
    def arm(self, now: float) -> None:
        self.armed, self._armed_at = True, now
        self._clear()

    def disarm(self) -> None:
        self.armed = False
        self._clear()

    def acknowledge(self) -> None:
        self._clear()

    def _clear(self) -> None:
        self._latched, self._latched_until = None, 0.0

    # -- evaluasi
    def evaluate(self, box, now: float, stale: bool = False) -> Decision:
        if not self.armed:
            return self._remember(Decision(SAFE, "Mode DISARM: pemilik mengizinkan akses kotak"))
        if box is None:
            return self._remember(Decision(SECURE, "Menunggu telemetri Edge 1 (kotak)"))
        if stale:
            # jangan mengubah status; hanya tandai bahwa data sudah basi
            return replace(self._last, reason=f"OFFLINE - telemetri kotak berhenti. Terakhir: {self._last.reason}")

        lid_open = box.lid_state == "OPEN"
        moving = box.motion_rms >= self.cfg.tamper_rms
        in_grace = (now - self._armed_at) < self.cfg.arm_grace_s

        if lid_open:
            lux = "-" if box.lux is None else f"{box.lux:.0f}"
            reason = f"Tutup terbuka saat ARM (lux={lux})"
            if moving:
                reason += f", disertai guncangan {box.motion_rms:.2f} m/s2"
            raw = Decision(ILLEGAL_OPEN, reason, box.motion_rms)
        elif moving and not in_grace:
            raw = Decision(TAMPER_ALERT,
                           f"Guncangan {box.motion_rms:.2f} m/s2 saat tutup terkunci (ambang {self.cfg.tamper_rms})",
                           box.motion_rms)
        elif in_grace:
            raw = Decision(SECURE, "Masa tenang setelah ARM", box.motion_rms)
        else:
            raw = Decision(SECURE, "Tutup tertutup, kotak diam", box.motion_rms)
        return self._latch(raw, now)

    def _latch(self, raw: Decision, now: float) -> Decision:
        if raw.status == ILLEGAL_OPEN:
            self._latched, self._latched_until = raw, math.inf
            return self._remember(raw)
        held = self._latched
        if held is not None and held.status == ILLEGAL_OPEN:
            return self._remember(replace(
                held, reason=f"Pelanggaran tercatat: {held.reason}. Tekan ACK atau DISARM"))
        if raw.status == TAMPER_ALERT:
            self._latched, self._latched_until = raw, now + self.cfg.alert_hold_s
            return self._remember(raw)
        if held is not None and now < self._latched_until:
            return self._remember(replace(held, reason=f"{held.reason} [ditahan]"))
        self._latched = None
        return self._remember(raw)

    def _remember(self, decision: Decision) -> Decision:
        self._last = decision
        return decision
