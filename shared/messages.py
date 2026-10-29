"""Format pesan telemetry (payload JSON)."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class Telemetry:
    device_id: str
    boot_id: str
    sequence: int
    motion_rms: float
    lux: Optional[float]
    proximity_cm: Optional[float]
    lid_state: str                      # "CLOSED" | "OPEN"
    lid_transition: Optional[str]       # "OPENED" | "CLOSED" | None
    sent_at_ms: int

    @classmethod
    def make(cls, device_id, boot_id, sequence, motion_rms, lux, proximity_cm,
             lid_state, lid_transition=None) -> "Telemetry":
        return cls(
            device_id=device_id,
            boot_id=boot_id,
            sequence=int(sequence),
            motion_rms=round(float(motion_rms), 4),
            lux=None if lux is None else round(float(lux), 2),
            proximity_cm=None if proximity_cm is None else round(float(proximity_cm), 2),
            lid_state=lid_state,
            lid_transition=lid_transition,
            sent_at_ms=int(time.time() * 1000),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Telemetry":
        try:
            return cls(
                device_id=str(data["device_id"]),
                boot_id=str(data.get("boot_id", "")),
                sequence=int(data.get("sequence", 0)),
                motion_rms=float(data["motion_rms"]),
                lux=None if data.get("lux") is None else float(data["lux"]),
                proximity_cm=None if data.get("proximity_cm") is None else float(data["proximity_cm"]),
                lid_state=str(data.get("lid_state", "CLOSED")).upper(),
                lid_transition=data.get("lid_transition"),
                sent_at_ms=int(data.get("sent_at_ms", 0)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"telemetry tidak valid: {exc}") from exc
