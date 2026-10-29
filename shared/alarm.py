"""Alarm di HP Pemilik: getar + notifikasi + suara (TTS) via Termux:API.
Tanpa Termux (laptop) otomatis jatuh ke output konsol."""
from __future__ import annotations

import shutil
import subprocess

PROFILES = {
    "TAMPER_ALERT": dict(vibrate_ms=1500, title="SmartBox: kotak diguncang!",
                         speech="Peringatan. Kotak paket sedang diguncang."),
    "ILLEGAL_OPEN": dict(vibrate_ms=3000, title="SmartBox: tutup dibuka paksa!",
                         speech="Bahaya. Tutup kotak paket dibuka paksa."),
    "TEST": dict(vibrate_ms=400, title="SmartBox: uji alarm", speech="Uji alarm berhasil."),
}


def _spawn(args: list[str]) -> None:
    try:
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        print(f"[ALARM] gagal menjalankan {args[0]}: {exc}")


class Alarm:
    def __init__(self, use_termux: bool | None = None):
        self.use_termux = shutil.which("termux-vibrate") is not None if use_termux is None else use_termux

    def trigger(self, status: str, reason: str) -> None:
        profile = PROFILES.get(status, PROFILES["TEST"])
        print(f"\a[ALARM] {status}: {reason}")
        if not self.use_termux:
            return
        _spawn(["termux-vibrate", "-d", str(profile["vibrate_ms"]), "-f"])
        _spawn(["termux-notification", "--id", "smartbox", "--title", profile["title"],
                "--content", reason, "--priority", "max"])
        _spawn(["termux-tts-speak", profile["speech"]])
