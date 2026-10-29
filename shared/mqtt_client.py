"""Pembuat client MQTT (paho-mqtt 2.x) + presence (online/offline lewat LWT)."""
from __future__ import annotations

import json
import random
import string
import time

import paho.mqtt.client as mqtt

from .config import Config


def build_client(cfg: Config, name: str, presence_topic: str | None = None) -> mqtt.Client:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=f"{cfg.project_id}-{name}-{suffix}",
                         protocol=mqtt.MQTTv311)
    if cfg.mqtt_tls:
        client.tls_set()   # memakai CA bawaan sistem (Termux: pkg install ca-certificates)
    if cfg.mqtt_username:
        client.username_pw_set(cfg.mqtt_username, cfg.mqtt_password)
    if presence_topic:
        client.will_set(presence_topic, json.dumps({"online": False}), qos=1, retain=True)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    return client


def announce(client: mqtt.Client, topic: str, device_id: str, boot_id: str, online: bool = True) -> None:
    payload = {"device_id": device_id, "boot_id": boot_id, "online": online,
               "sent_at_ms": int(time.time() * 1000)}
    client.publish(topic, json.dumps(payload), qos=1, retain=True)
