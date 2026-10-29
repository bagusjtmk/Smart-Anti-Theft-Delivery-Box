"""Edge 2 - HP Pemilik di dalam rumah.
Subscribe alerts dari detector -> getar/notifikasi/suara (Termux:API).
Kontrol konsol: a=ARM  d=DISARM  k=ACK  t=TEST  q=keluar"""
import argparse
import json
import sys
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared.alarm import Alarm
from shared.config import load_config
from shared.mqtt_client import announce, build_client

COOLDOWN_S = 6.0   # jangan membunyikan alarm yang sama berturut-turut terlalu rapat


def main() -> None:
    parser = argparse.ArgumentParser(description="SmartBox - Edge 2 (HP pemilik)")
    parser.add_argument("--source", choices=["auto", "termux", "simulator"], default="auto",
                        help="termux = alarm asli via Termux:API; simulator = hanya cetak ke konsol")
    args = parser.parse_args()

    cfg = load_config()
    device_id = cfg.owner_device_id
    boot_id = uuid.uuid4().hex[:8]
    presence_topic = cfg.topic(f"edge/{device_id}/presence")
    alerts_topic = cfg.topic("alerts")
    status_topic = cfg.topic("status")
    control_topic = cfg.topic("control")

    use_termux = None if args.source == "auto" else (args.source == "termux")
    alarm = Alarm(use_termux)
    stop = threading.Event()
    state = {"last_alarm": 0.0, "last_status": None, "last_alert_status": None}

    client = build_client(cfg, device_id, presence_topic=presence_topic)

    def on_connect(c, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[OWNER] Gagal konek broker: {reason_code}")
            return
        print(f"[OWNER] Terhubung. Subscribed {alerts_topic}")
        c.subscribe([(alerts_topic, 1), (status_topic, 0)])
        announce(c, presence_topic, device_id, boot_id, online=True)

    def on_message(c, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(data, dict):
            return
        if msg.topic == status_topic:
            if data.get("status") != state["last_status"]:
                state["last_status"] = data.get("status")
                print(f"[OWNER] Status kotak: {data.get('status')} - {data.get('reason')}")
            return
        if msg.topic == alerts_topic:
            status = str(data.get("status", "TEST"))
            now = time.monotonic()
            if status == state["last_alert_status"] and now - state["last_alarm"] < COOLDOWN_S:
                return
            state["last_alarm"], state["last_alert_status"] = now, status
            alarm.trigger(status, str(data.get("reason", "")))

    def send(cmd: str) -> None:
        client.publish(control_topic, json.dumps({"cmd": cmd, "token": cfg.control_token,
                                                  "from": device_id}), qos=1)
        print(f"[OWNER] Kirim perintah: {cmd}")

    def console() -> None:
        print("[OWNER] Perintah: a=ARM  d=DISARM  k=ACK  t=TEST alarm  q=keluar")
        names = {"a": "arm", "d": "disarm", "k": "ack", "t": "test_alarm"}
        while not stop.is_set():
            try:
                line = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                return
            if line[:1] == "q":
                stop.set()
            elif line[:1] in names:
                send(names[line[:1]])

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect_async(cfg.mqtt_host, cfg.mqtt_port, keepalive=30)
    client.loop_start()

    print("SmartBox - EDGE 2 / HP Pemilik")
    print(f"[OWNER] Alarm: {'Termux:API' if alarm.use_termux else 'konsol (simulasi)'}")
    threading.Thread(target=console, daemon=True).start()
    try:
        while not stop.is_set():
            stop.wait(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        announce(client, presence_topic, device_id, boot_id, online=False)
        time.sleep(0.3)
        client.loop_stop()
        client.disconnect()
        print("[OWNER] Berhenti.")


if __name__ == "__main__":
    main()
