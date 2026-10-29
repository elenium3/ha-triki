"""Diagnostics: entry options, device state and link statistics."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant

from . import TrikiConfigEntry

# the scanner source is the MAC of the adapter/proxy the link went through
TO_REDACT = {CONF_ADDRESS, "source", "last_source"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TrikiConfigEntry
) -> dict[str, Any]:
    dev = entry.runtime_data
    info = bluetooth.async_last_service_info(hass, dev.address, connectable=True)
    data: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "options": asdict(dev.options),
        "device": {
            "connected": dev.connected,
            "stream_rate": dev.stream_rate if dev.connected else None,
            "firmware": dev.firmware,
            "hardware": dev.hardware,
            "battery": dev.battery,
            "rssi": dev.rssi,
            "led_on": dev.led_on,
            "button": dev.button,
            "pitch": dev.pitch,
            "roll": dev.roll,
        },
        "link": asdict(dev.stats),
        "advertisements": dev.advertisement_cadence,
        "last_advertisement": None
        if info is None
        else {
            "source": info.source,
            "rssi": info.rssi,
            "age_s": round(bluetooth.MONOTONIC_TIME() - info.time, 1),
            "connectable": info.connectable,
        },
    }
    return async_redact_data(data, TO_REDACT)
