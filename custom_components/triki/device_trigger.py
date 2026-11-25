"""Device triggers: "Triki was pressed" in the automation editor.

The event entity is the main interface, but a State trigger on it needs a
template condition on ``event_type`` (an attribute trigger misses the second of
two identical gestures, the attribute does not change). Device triggers give
the editor a plain list of gestures instead. They listen to the bus event the
device fires for every gesture.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import ATTR_PRESS_COUNT, BUS_EVENT, DOMAIN, EVENT_MULTI_PRESS, TRIGGER_TYPES
from .models import TrikiOptions

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend({vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES)})

# a trigger that is one count of the multi_press event
_PRESS_COUNT = {"double_press": 2, "triple_press": 3}

# gestures offered only while their option is on; the rest are always there
_BY_OPTION = {
    "double_press": "multi_press",
    "triple_press": "multi_press",
    "rotate_cw": "knob",
    "rotate_ccw": "knob",
    "tilt_right": "tilt",
    "tilt_left": "tilt",
    "shake": "shake",
    "tap": "motion_gestures",
    "throw": "motion_gestures",
    "flip": "motion_gestures",
}


def _options(hass: HomeAssistant, device_id: str) -> TrikiOptions | None:
    # by the Bluetooth address, which is the entry's unique id: a device's
    # config entries are read differently across the supported cores
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    connections: set[tuple[str, str]] = getattr(device, "connections", set())  # not on a child
    addresses = {a.upper() for kind, a in connections if kind == dr.CONNECTION_BLUETOOTH}
    for entry in hass.config_entries.async_entries(DOMAIN):
        if (entry.unique_id or "").upper() in addresses:
            return TrikiOptions.from_entry(entry)
    return None


async def async_get_triggers(hass: HomeAssistant, device_id: str) -> list[dict[str, Any]]:
    """The gestures the cap can send with its current options."""
    opts = _options(hass, device_id)
    if opts is None:
        return []
    return [
        {CONF_PLATFORM: "device", CONF_DOMAIN: DOMAIN, CONF_DEVICE_ID: device_id, CONF_TYPE: kind}
        for kind in TRIGGER_TYPES
        if kind not in _BY_OPTION or getattr(opts, _BY_OPTION[kind])
    ]


def _bus_match(kind: str) -> dict[str, Any]:
    if kind in _PRESS_COUNT:
        return {CONF_TYPE: EVENT_MULTI_PRESS, ATTR_PRESS_COUNT: _PRESS_COUNT[kind]}
    return {CONF_TYPE: kind}


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Listen for the bus event of this cap and gesture."""
    event_config = event_trigger.TRIGGER_SCHEMA(
        {
            event_trigger.CONF_PLATFORM: "event",
            event_trigger.CONF_EVENT_TYPE: BUS_EVENT,
            event_trigger.CONF_EVENT_DATA: {
                CONF_DEVICE_ID: config[CONF_DEVICE_ID],
                **_bus_match(config[CONF_TYPE]),
            },
        }
    )
    return await event_trigger.async_attach_trigger(
        hass, event_config, action, trigger_info, platform_type="device"
    )
