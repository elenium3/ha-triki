"""Raw session capture to /config/triki_captures/*.jsonl (debug option).

Same line format as tools/triki_probe.py, so tools/replay.py works on both:
  {"t": 0, "meta": {...}}           session header
  {"t": 1.234, "hex": "2200..."}    one BLE notification, as received
  {"t": 1.240, "event": "press", "data": {...}}
  {"t": 9.9, "disconnected": true}
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

FLUSH_S = 1.0


class Capture:
    def __init__(self, hass: HomeAssistant, name: str) -> None:
        self.hass = hass
        self.name = name
        self.path: Path | None = None
        self._buf: list[str] = []
        self._t0 = 0.0
        self._unsub = None

    @callback
    def start(self, meta: dict[str, Any]) -> None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        slug = "".join(c if c.isalnum() else "_" for c in self.name).strip("_")
        self.path = Path(self.hass.config.path("triki_captures", f"{stamp}-{slug}.jsonl"))
        self._t0 = time.monotonic()
        self._buf = []
        self.write({"t": 0, "meta": meta})

    @callback
    def write(self, rec: dict[str, Any]) -> None:
        if self.path is None:
            return
        rec.setdefault("t", round(time.monotonic() - self._t0, 4))
        self._buf.append(json.dumps(rec))
        if self._unsub is None:
            self._unsub = async_call_later(self.hass, FLUSH_S, self._flush_cb)

    @callback
    def _flush_cb(self, _now: Any) -> None:
        self._unsub = None
        self._flush()

    @callback
    def _flush(self) -> None:
        if not self._buf or self.path is None:
            return
        lines, self._buf = self._buf, []
        self.hass.async_add_executor_job(_append, self.path, lines)

    @callback
    def stop(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None
        self._flush()
        self.path = None


def _append(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
