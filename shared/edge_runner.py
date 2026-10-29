"""Loop Edge 1 (kotak): baca sensor -> olah per window -> publish telemetry (bukan data mentah)."""
from __future__ import annotations

import time
import uuid

from .config import Config
from .messages import Telemetry
from .mqtt_client import announce, build_client
from .processing import LidTracker, motion_rms
from .sensors import SensorError


def run_box(cfg: Config, source, device_id: str | None = None) -> None:
    device_id = device_id or cfg.box_device_id
    boot_id = uuid.uuid4().hex[:8]
    telemetry_topic = cfg.topic(f"edge/{device_id}/telemetry")
    presence_topic = cfg.topic(f"edge/{device_id}/presence")

    client = build_client(cfg, device_id, presence_topic=presence_topic)

    def on_connect(c, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[BOX] Gagal konek broker: {reason_code}")
            return
        print(f"[BOX] Terhubung ke {cfg.mqtt_host}:{cfg.mqtt_port} (TLS={cfg.mqtt_tls})")
        announce(c, presence_topic, device_id, boot_id, online=True)

    def on_disconnect(c, userdata, flags, reason_code, properties):
        print(f"[BOX] Terputus ({reason_code}), mencoba lagi otomatis...")

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.connect_async(cfg.mqtt_host, cfg.mqtt_port, keepalive=30)
    client.loop_start()

    tracker = LidTracker(cfg.lid_sensor, cfg.light_open_lux, cfg.light_close_lux, cfg.proximity_far_cm)
    sequence = 0
    try:
        while True:
            samples = []
            for _ in range(cfg.window_size):
                started = time.monotonic()
                try:
                    samples.append(source.read())
                except SensorError as exc:
                    print(f"[BOX] Sensor error: {exc}")
                time.sleep(max(0.0, cfg.sample_interval - (time.monotonic() - started)))
            if not samples:
                continue

            sequence += 1
            rms = motion_rms(samples)
            lid = tracker.update(samples)
            telemetry = Telemetry.make(device_id, boot_id, sequence, rms, lid.lux,
                                       lid.proximity_cm, lid.state, lid.transition)
            client.publish(telemetry_topic, telemetry.to_json(), qos=1)
            extra = f"  <-- {lid.transition}" if lid.transition else ""
            lux = "-" if lid.lux is None else f"{lid.lux:.1f}"
            prox = "-" if lid.proximity_cm is None else f"{lid.proximity_cm:.1f}"
            print(f"[BOX] #{sequence} rms={rms:.3f} lux={lux} prox={prox} lid={lid.state}{extra}")
    except KeyboardInterrupt:
        print("\n[BOX] Berhenti.")
    finally:
        announce(client, presence_topic, device_id, boot_id, online=False)
        time.sleep(0.3)
        client.loop_stop()
        client.disconnect()
