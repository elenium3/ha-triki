"""Żabka Triki BLE motion controller for Home Assistant."""

from __future__ import annotations

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import MANUFACTURER, MODEL
from .device import TrikiDevice
from .models import TrikiOptions

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.LIGHT,
    Platform.SENSOR,
]

type TrikiConfigEntry = ConfigEntry[TrikiDevice]


async def async_setup_entry(hass: HomeAssistant, entry: TrikiConfigEntry) -> bool:
    address: str = entry.data[CONF_ADDRESS]
    device = TrikiDevice(hass, address, entry.title, TrikiOptions.from_entry(entry), entry=entry)
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

    async def _async_stop(_event: Event) -> None:
        # Home Assistant does not unload entries on shutdown: close the link
        # ourselves so the token is not left connected to a dying BlueZ.
        await device.async_stop()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TrikiConfigEntry) -> bool:
    await entry.runtime_data.async_stop()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # let the token be discovered again right away if the entry was removed
        bluetooth.async_rediscover_address(hass, entry.data[CONF_ADDRESS])
    return unload_ok
