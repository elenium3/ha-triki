"""Event entity: button presses, knob turns and motion gestures."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TrikiConfigEntry
from .const import EVENT_TYPES
from .entity import TrikiEntity

DESCRIPTION = EventEntityDescription(
    key="action",
    translation_key="action",
    event_types=EVENT_TYPES,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrikiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([TrikiEventEntity(entry.runtime_data, DESCRIPTION)])


class TrikiEventEntity(TrikiEntity, EventEntity):
    # Must stay available while the token sleeps, otherwise automations see
    # "unavailable" between every use.
    _requires_connection = False

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.device.async_add_event_listener(self._handle_event))

    @callback
    def _handle_event(self, kind: str, data: dict[str, Any]) -> None:
        self._trigger_event(kind, data)
        self.async_write_ha_state()
