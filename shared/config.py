"""Konfigurasi dari .env - dipakai semua node (box, owner, detector)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv opsional; environment variable biasa tetap terbaca
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent
TOPIC_ROOT = "smartbox"
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
LID_MODES = {"light", "proximity", "either", "both"}


def _get(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None or value.strip() == "" else value.strip()


def _bool(name: str, default: bool) -> bool:
    return _get(name, str(default)).lower() in {"1", "true", "yes", "y", "on"}


def _float(name: str, default: float) -> float:
    try:
        return float(_get(name, str(default)))
    except ValueError:
        raise SystemExit(f"[CONFIG] {name} harus berupa angka")


def _int(name: str, default: int) -> int:
    try:
        return int(_get(name, str(default)))
    except ValueError:
        raise SystemExit(f"[CONFIG] {name} harus berupa bilangan bulat")


@dataclass(frozen=True)
class Config:
    project_id: str
    mqtt_host: str
    mqtt_port: int
    mqtt_tls: bool
    mqtt_username: str
    mqtt_password: str
    mqtt_ws_url: str
    box_device_id: str
    owner_device_id: str
    window_size: int
    sample_interval: float
    tamper_rms: float
    lid_sensor: str
    light_open_lux: float
    light_close_lux: float
    proximity_far_cm: float
    arm_on_start: bool
    arm_grace_s: float
    alert_hold_s: float
    alert_repeat_s: float
    stale_s: float
    dashboard_port: int
    control_token: str

    def topic(self, suffix: str) -> str:
        """smartbox/<PROJECT_ID>/<suffix>"""
        return f"{TOPIC_ROOT}/{self.project_id}/{suffix}"


def load_config() -> Config:
    if load_dotenv:
        load_dotenv(ROOT / ".env")

    cfg = Config(
        project_id=_get("PROJECT_ID", "smartbox_demo"),
        mqtt_host=_get("MQTT_HOST", "broker.hivemq.com"),
        mqtt_port=_int("MQTT_PORT", 8883),
        mqtt_tls=_bool("MQTT_TLS", True),
        mqtt_username=_get("MQTT_USERNAME"),
        mqtt_password=_get("MQTT_PASSWORD"),
        mqtt_ws_url=_get("MQTT_WS_URL", "wss://broker.hivemq.com:8884/mqtt"),
        box_device_id=_get("BOX_DEVICE_ID", "box1"),
        owner_device_id=_get("OWNER_DEVICE_ID", "owner1"),
        window_size=_int("WINDOW_SIZE", 5),
        sample_interval=_float("SAMPLE_INTERVAL", 0.2),
        tamper_rms=_float("TAMPER_RMS", 0.7),
        lid_sensor=_get("LID_SENSOR", "light").lower(),
        light_open_lux=_float("LIGHT_OPEN_LUX", 15.0),
        light_close_lux=_float("LIGHT_CLOSE_LUX", 8.0),
        proximity_far_cm=_float("PROXIMITY_FAR_CM", 3.0),
        arm_on_start=_bool("ARM_ON_START", True),
        arm_grace_s=_float("ARM_GRACE_S", 5.0),
        alert_hold_s=_float("ALERT_HOLD_S", 10.0),
        alert_repeat_s=_float("ALERT_REPEAT_S", 10.0),
        stale_s=_float("STALE_S", 15.0),
        dashboard_port=_int("DASHBOARD_PORT", 8000),
        control_token=_get("CONTROL_TOKEN"),
    )

    for name, value in (
        ("PROJECT_ID", cfg.project_id),
        ("BOX_DEVICE_ID", cfg.box_device_id),
        ("OWNER_DEVICE_ID", cfg.owner_device_id),
    ):
        if not _ID_RE.match(value):
            raise SystemExit(f"[CONFIG] {name} hanya boleh huruf, angka, '-' dan '_'")
    if cfg.lid_sensor not in LID_MODES:
        raise SystemExit(f"[CONFIG] LID_SENSOR harus salah satu dari {sorted(LID_MODES)}")
    if cfg.light_close_lux > cfg.light_open_lux:
        raise SystemExit("[CONFIG] LIGHT_CLOSE_LUX harus <= LIGHT_OPEN_LUX (hysteresis)")
    if cfg.window_size < 2:
        raise SystemExit("[CONFIG] WINDOW_SIZE minimal 2")
    if cfg.project_id.endswith("_XX"):
        print("[CONFIG] Peringatan: ganti PROJECT_ID di .env dengan nama unik kelompokmu")
    return cfg
