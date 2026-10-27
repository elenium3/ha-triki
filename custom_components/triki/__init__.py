"""Żabka Triki BLE motion controller for Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_CAPTURE,
    CONF_IDLE_TIMEOUT,
    CONF_INVERT_ROTATION,
    CONF_KNOB_STEP,
    CONF_RATE,
    CONF_WAKE_AS_PRESS,
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_INVERT_ROTATION,
    DEFAULT_WAKE_AS_PRESS,
    DEFAULT_KNOB_STEP,
    DEFAULT_RATE,
    MANUFACTURER,
    MODEL,
)
from .device import TrikiDevice

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.LIGHT,
    Platform.SENSOR,
]

type TrikiConfigEntry = ConfigEntry[TrikiDevice]


async def async_setup_entry(hass: HomeAssistant, entry: TrikiConfigEntry) -> bool:
    address: str = entry.data[CONF_ADDRESS]
    opts = entry.options
    device = TrikiDevice(
        hass,
        address,
        entry.title,
        rate=int(opts.get(CONF_RATE, DEFAULT_RATE)),
        idle_timeout=int(opts.get(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT)),
        knob_step=float(opts.get(CONF_KNOB_STEP, DEFAULT_KNOB_STEP)),
        invert_rotation=bool(opts.get(CONF_INVERT_ROTATION, DEFAULT_INVERT_ROTATION)),
        capture=bool(opts.get(CONF_CAPTURE, False)),
        wake_as_press=bool(opts.get(CONF_WAKE_AS_PRESS, DEFAULT_WAKE_AS_PRESS)),
    )
    dev = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_BLUETOOTH, address)},
        name=entry.title,
        manufacturer=MANUFACTURER,
        model=MODEL,
    )
    device.device_id = dev.id
    entry.runtime_data = device

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    device.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: TrikiConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: TrikiConfigEntry) -> bool:
    await entry.runtime_data.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
