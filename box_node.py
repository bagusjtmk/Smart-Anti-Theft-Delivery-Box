"""Edge 1 - HP di dalam/menempel pada kotak paket.
Sensor: accelerometer (guncangan) + light/proximity (tutup kotak)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared.config import load_config
from shared.edge_runner import run_box
from shared.sensors import SensorError, make_source


def main() -> None:
    parser = argparse.ArgumentParser(description="SmartBox - Edge 1 (kotak paket)")
    parser.add_argument("--source", choices=["auto", "termux", "simulator"], default="auto")
    parser.add_argument("--scenario", choices=["still", "shake", "open", "demo"], default="demo",
                        help="hanya untuk simulator")
    args = parser.parse_args()

    cfg = load_config()
    want_light = cfg.lid_sensor in ("light", "either", "both")
    want_prox = cfg.lid_sensor in ("proximity", "either", "both")
    try:
        source = make_source(args.source, args.scenario, want_light, want_prox)
    except SensorError as exc:
        raise SystemExit(f"[BOX] {exc}")

    print("SmartBox - EDGE 1 / Kotak Paket")
    print(f"[BOX] Source: {source.name} / scenario: {args.scenario if source.name == 'simulator' else '-'}")
    print(f"[BOX] Publishes to: {cfg.topic(f'edge/{cfg.box_device_id}/telemetry')}")
    run_box(cfg, source)


if __name__ == "__main__":
    main()
