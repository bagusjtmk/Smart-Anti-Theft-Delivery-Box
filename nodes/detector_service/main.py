"""Detector (laptop): subscribe telemetry -> rules -> publish status (retained) & alerts."""
from __future__ import annotations

import argparse
import hmac
import json
import threading
import time
from typing import Optional

from shared.config import Config, load_config
from shared.messages import Telemetry
from shared.mqtt_client import build_client

from .dashboard_server import lan_ip, start_dashboard
from .rules import BoxRules, RuleConfig

TICK_S = 0.5
STATUS_EVERY_S = 1.0


class DetectorService:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.base = cfg.topic("")
        self.lock = threading.Lock()
        self.rules = BoxRules(
            RuleConfig(cfg.tamper_rms, cfg.arm_grace_s, cfg.alert_hold_s),
            armed=cfg.arm_on_start, now=time.monotonic())
        self.box: Optional[Telemetry] = None
        self.box_rx = 0.0
        self._box_key = ("", -1)
        self.owner_online = False
        self._last_status: Optional[str] = None
        self._last_status_pub = 0.0
        self._last_alert = 0.0
        self.client = build_client(cfg, "detector")
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    # ------------------------------------------------------------ MQTT callbacks
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[DETECTOR] Gagal konek broker: {reason_code}")
            return
        print(f"[DETECTOR] Terhubung ke {self.cfg.mqtt_host}:{self.cfg.mqtt_port} (TLS={self.cfg.mqtt_tls})")
        client.subscribe([(self.base + "edge/+/telemetry", 1),
                          (self.base + "edge/+/presence", 1),
                          (self.base + "control", 1)])

    def _on_message(self, client, userdata, msg):
        if not msg.topic.startswith(self.base):
            return
        rel = msg.topic[len(self.base):]
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(data, dict):
            return
        if rel == "control":
            self._on_control(data)
            return
        parts = rel.split("/")
        if len(parts) == 3 and parts[0] == "edge":
            device, kind = parts[1], parts[2]
            if kind == "telemetry" and device == self.cfg.box_device_id:
                self._on_box(data)
            elif kind == "presence" and device == self.cfg.owner_device_id:
                with self.lock:
                    self.owner_online = bool(data.get("online"))

    def _on_box(self, data: dict) -> None:
        try:
            tele = Telemetry.from_dict(data)
        except ValueError as exc:
            print(f"[DETECTOR] {exc}")
            return
        with self.lock:
            boot, seq = self._box_key
            if tele.boot_id == boot and tele.sequence <= seq:
                return   # duplikat QoS1 / pesan lama
            self._box_key = (tele.boot_id, tele.sequence)
            self.box, self.box_rx = tele, time.monotonic()
        if tele.lid_transition:
            print(f"[DETECTOR] Tutup kotak: {tele.lid_transition}")

    def _on_control(self, data: dict) -> None:
        token = self.cfg.control_token
        if token and not hmac.compare_digest(str(data.get("token", "")), token):
            print("[DETECTOR] Perintah ditolak: token salah")
            return
        cmd, who = str(data.get("cmd", "")).lower(), data.get("from", "?")
        now = time.monotonic()
        with self.lock:
            if cmd == "arm":
                self.rules.arm(now)
            elif cmd == "disarm":
                self.rules.disarm()
            elif cmd == "ack":
                self.rules.acknowledge()
            elif cmd != "test_alarm":
                return
            self._last_status_pub = 0.0   # paksa publish status segera
        print(f"[DETECTOR] Perintah '{cmd}' dari {who}")
        if cmd == "test_alarm":
            self._publish("alerts", {"status": "TEST", "reason": f"Uji alarm dari {who}",
                                     "sent_at_ms": int(time.time() * 1000)}, qos=1)

    # ------------------------------------------------------------ publish helpers
    def _publish(self, suffix: str, obj: dict, qos: int = 0, retain: bool = False) -> None:
        self.client.publish(self.base + suffix, json.dumps(obj, separators=(",", ":")),
                            qos=qos, retain=retain)

    def _status_payload(self, decision, box, age, stale) -> dict:
        return {
            "status": decision.status,
            "reason": decision.reason,
            "score": round(decision.score, 3),
            "armed": self.rules.armed,
            "box_online": not stale,
            "owner_online": self.owner_online,
            "box": None if box is None else {
                "motion_rms": box.motion_rms, "lux": box.lux, "proximity_cm": box.proximity_cm,
                "lid_state": box.lid_state, "sequence": box.sequence,
                "age_s": round(age, 1) if age is not None else None},
            "thresholds": {"tamper_rms": self.cfg.tamper_rms,
                           "light_open_lux": self.cfg.light_open_lux,
                           "light_close_lux": self.cfg.light_close_lux},
            "sent_at_ms": int(time.time() * 1000),
        }

    # ------------------------------------------------------------ loop
    def tick(self) -> None:
        now = time.monotonic()
        with self.lock:
            box = self.box
            age = (now - self.box_rx) if box is not None else None
            stale = box is None or age > self.cfg.stale_s
            decision = self.rules.evaluate(box, now, stale=stale)
            payload = self._status_payload(decision, box, age, stale)
            force = self._last_status_pub == 0.0

        changed = decision.status != self._last_status
        if changed:
            print(f"[DETECTOR] {self._last_status or '-'} -> {decision.status}: {decision.reason}")
            self._last_status = decision.status

        if decision.is_alert and (changed or now - self._last_alert >= self.cfg.alert_repeat_s):
            self._last_alert = now
            self._publish("alerts", {"status": decision.status, "reason": decision.reason,
                                     "score": round(decision.score, 3),
                                     "sent_at_ms": payload["sent_at_ms"]}, qos=1)
            print(f"[DETECTOR] ALERT dikirim ke HP Pemilik: {decision.status}")

        if changed or force or now - self._last_status_pub >= STATUS_EVERY_S:
            self._last_status_pub = now
            self._publish("status", payload, qos=0, retain=True)

    def run(self) -> None:
        self.client.connect_async(self.cfg.mqtt_host, self.cfg.mqtt_port, keepalive=30)
        self.client.loop_start()
        try:
            while True:
                self.tick()
                time.sleep(TICK_S)
        except KeyboardInterrupt:
            print("\n[DETECTOR] Berhenti.")
        finally:
            self.client.loop_stop()
            self.client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="SmartBox - Detector (laptop)")
    parser.add_argument("--no-dashboard", action="store_true", help="jangan jalankan server dashboard")
    parser.add_argument("--port", type=int, default=None, help="port dashboard (default DASHBOARD_PORT)")
    args = parser.parse_args()

    cfg = load_config()
    print("SmartBox - NODE 3 / Laptop")
    if not args.no_dashboard:
        port = args.port or cfg.dashboard_port
        start_dashboard(cfg, port)
        print(f"[DASHBOARD] Laptop : http://localhost:{port}")
        print(f"[DASHBOARD] HP/LAN : http://{lan_ip()}:{port}  (satu WiFi/hotspot)")
    print(f"[CONFIG] PROJECT_ID: {cfg.project_id} | ARM_ON_START: {cfg.arm_on_start}")
    print("[DETECTOR] Menunggu Edge 1 (kotak) dan Edge 2 (pemilik) dari MQTT Cloud...")
    DetectorService(cfg).run()
