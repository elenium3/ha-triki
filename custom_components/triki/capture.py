"""Raw session capture to /config/triki_captures/*.jsonl (debug option).

Same line format as tools/triki_probe.py, so tools/replay.py works on both:
  {"t": 0, "meta": {...}}           session header
  {"t": 1.234, "hex": "2200..."}    one BLE notification, as received
  {"t": 1.240, "event": "press", "data": {...}}
  {"t": 9.9, "disconnected": true}
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)
MAX_BYTES = 50_000_000  # per capture file: ~5-10 h of a 52 Hz stream

FLUSH_S = 1.0


class Capture:
    def __init__(self, hass: HomeAssistant, name: str) -> None:
        self.hass = hass
        self.name = name
        self.path: Path | None = None
        self._buf: list[str] = []
        self._bytes = 0
        self._t0 = 0.0
        self._unsub: CALLBACK_TYPE | None = None
        # one writer at a time, in flush order: two executor jobs in flight at
        # once could append the later batch first
        self._io_lock = asyncio.Lock()

    @callback
    def start(self, meta: dict[str, Any]) -> None:
        stamp = dt_util.now().strftime("%Y%m%d-%H%M%S")
        slug = "".join(c if c.isalnum() else "_" for c in self.name).strip("_")
        self.path = Path(self.hass.config.path("triki_captures", f"{stamp}-{slug}.jsonl"))
        self._t0 = time.monotonic()
        self._buf = []
        self._bytes = 0
        self.write({"t": 0, "meta": meta})

    @callback
    def write(self, rec: dict[str, Any]) -> None:
        if self.path is None or self._bytes >= MAX_BYTES:
            return
        rec.setdefault("t", round(time.monotonic() - self._t0, 4))
        line = json.dumps(rec)
        self._buf.append(line)
        self._bytes += len(line) + 1
        if self._bytes >= MAX_BYTES:
            # a forgotten debug option must not fill the disk: one file per link
            # is capped, a new link starts a new file
            self._buf.append(json.dumps({"t": rec["t"], "stopped": "size limit"}))
            _LOGGER.warning(
                "%s: capture file %s reached %d MB, recording stopped; turn the "
                "capture option off when you are done",
                self.name,
                self.path.name,
                MAX_BYTES // 1_000_000,
            )
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
        # eager: the lock is taken (or queued for) right here, so batches are
        # written in the order they were flushed
        self.hass.async_create_background_task(
            self._write(self.path, lines), f"triki_capture_{self.name}", eager_start=True
        )

    async def _write(self, path: Path, lines: list[str]) -> None:
        async with self._io_lock:
            await self.hass.async_add_executor_job(_append, path, lines)

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
