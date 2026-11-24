"""Żabka Triki BLE motion controller for Home Assistant."""

from __future__ import annotations

import hashlib
from pathlib import Path

from aiohttp import web
from bleak_retry_connector import close_stale_connections_by_address
from homeassistant.components import bluetooth
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_IDLE_TIMEOUT,
    CONF_SLEEP_TIMEOUT,
    CONF_WAKE_AS_PRESS,
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_SLEEP_TIMEOUT,
    DOMAIN,
    ISSUE_BATTERY_LOW,
    ISSUE_LINK_LOSSY,
    ISSUE_NOT_RESPONDING,
    ISSUE_SLEEP_NEVER,
    MANUFACTURER,
    MODEL,
    WAKE_PRESS_MARK,
)
from .device import TrikiDevice
from .models import TrikiOptions
from .websocket import async_register as async_register_websocket

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

type TrikiConfigEntry = ConfigEntry[TrikiDevice]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# The live card (custom:triki-card) and its 3D model, served by the integration.
FRONTEND_URL = f"/{DOMAIN}_frontend"
FRONTEND_DIR = Path(__file__).parent / "frontend"
FRONTEND_FILES = (
    "triki-card.js",
    "triki-cap.js",
    "triki-check.js",
    "triki-three.js",
    "triki.glb",
    "tex_metal.webp",
    "tex_resin.webp",
)


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    async_register_websocket(hass)
    # The content hash in the URL changes after an update with a restart; a frontend-only
    # update between restarts reaches the browser through "no-cache" (see the view).
    card_hash = await hass.async_add_executor_job(_card_hash)
    hass.http.register_view(TrikiFrontendView())
    if "frontend" in hass.config.components:
        add_extra_js_url(hass, f"{FRONTEND_URL}/triki-card.js?v={card_hash}")
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: TrikiConfigEntry) -> bool:
    if entry.version > 2:
        return False  # created by a newer version of the integration
    if entry.version == 1:
        # v1: idle_timeout dropped the link. v2: idle_timeout lowers the stream
        # rate and sleep_timeout drops the link, so a user-set value moves over.
        options = dict(entry.options)
        if CONF_IDLE_TIMEOUT in options and CONF_SLEEP_TIMEOUT not in options:
            options[CONF_SLEEP_TIMEOUT] = options[CONF_IDLE_TIMEOUT]
            options[CONF_IDLE_TIMEOUT] = DEFAULT_IDLE_TIMEOUT
        hass.config_entries.async_update_entry(entry, options=options, version=2)
    return True


@callback
def _async_wake_press_on_once(hass: HomeAssistant, entry: TrikiConfigEntry) -> None:
    """0.3.0: only the button wakes the token, so the waking press is reported by
    default. The old default (off) was saved with any change of options, so it is
    rarely a choice: turn it on once. A marker in the entry's data, not a version
    bump, so an older release still loads the entry after a downgrade."""
    if entry.data.get(WAKE_PRESS_MARK):
        return
    options = dict(entry.options)
    options[CONF_WAKE_AS_PRESS] = True
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, WAKE_PRESS_MARK: True}, options=options
    )


async def async_setup_entry(hass: HomeAssistant, entry: TrikiConfigEntry) -> bool:
    address: str = entry.data[CONF_ADDRESS]
    _async_wake_press_on_once(hass, entry)
    # A link left open by a previous Home Assistant process (crash, kill) stays
    # up in BlueZ; the token then neither advertises nor accepts a second link.
    await close_stale_connections_by_address(address)
    options = TrikiOptions.from_entry(entry)
    _async_update_sleep_issue(hass, entry, options)
    device = TrikiDevice(hass, address, entry.title, options, entry=entry)
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


class TrikiFrontendView(HomeAssistantView):
    """The card's files, revalidated by the browser on every load.

    A static path without cache headers still let browsers keep the files by their own
    heuristic: after a frontend-only update the owner saw the old model until the cache
    expired. "no-cache" makes the browser ask each time; an unchanged file costs a 304.
    """

    url = FRONTEND_URL + "/{filename}"
    name = "triki:frontend"
    requires_auth = False  # loaded by the browser as module and texture URLs

    async def get(self, _request: web.Request, filename: str) -> web.StreamResponse:
        if filename not in FRONTEND_FILES:  # a fixed list: no paths, no other files
            raise web.HTTPNotFound
        return web.FileResponse(FRONTEND_DIR / filename, headers={"Cache-Control": "no-cache"})


def _card_hash() -> str:
    digest = hashlib.sha256()
    for name in FRONTEND_FILES:
        digest.update((FRONTEND_DIR / name).read_bytes())
    return digest.hexdigest()[:12]


def _async_update_sleep_issue(
    hass: HomeAssistant, entry: TrikiConfigEntry, options: TrikiOptions
) -> None:
    """Warn while the link is set to be held forever: that drains the cell in days."""
    issue_id = f"{ISSUE_SLEEP_NEVER}_{entry.entry_id}"
    if options.sleep_timeout > 0:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_SLEEP_NEVER,
        translation_placeholders={"name": entry.title, "seconds": str(DEFAULT_SLEEP_TIMEOUT)},
        data={"entry_id": entry.entry_id},
    )


async def async_remove_entry(hass: HomeAssistant, entry: TrikiConfigEntry) -> None:
    for issue in (ISSUE_SLEEP_NEVER, ISSUE_BATTERY_LOW, ISSUE_NOT_RESPONDING, ISSUE_LINK_LOSSY):
        ir.async_delete_issue(hass, DOMAIN, f"{issue}_{entry.entry_id}")


async def async_unload_entry(hass: HomeAssistant, entry: TrikiConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_stop()
        # let the token be discovered again right away if the entry was removed
        bluetooth.async_rediscover_address(hass, entry.data[CONF_ADDRESS])
    return unload_ok
