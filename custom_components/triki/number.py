"""Where the knob stands, 0-100 %: moved by turning the cap, settable from Home Assistant."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntityDescription, NumberMode, RestoreNumber
from homeassistant.const import PERCENTAGE, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TrikiConfigEntry
from .const import DOMAIN
from .entity import TrikiEntity
from .gestures import KNOB_EVENTS

PARALLEL_UPDATES = 0  # no I/O: the value lives in Home Assistant

DESCRIPTION = NumberEntityDescription(
    key="knob_position",
    translation_key="knob_position",
    native_min_value=0,
    native_max_value=100,
    native_step=1,
    native_unit_of_measurement=PERCENTAGE,
    mode=NumberMode.SLIDER,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrikiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    device = entry.runtime_data
    if device.options.knob:
        async_add_entities([TrikiKnobPosition(device, DESCRIPTION)])
        return
    # the knob is off: nothing moves the value, so the entity goes with it
    registry = er.async_get(hass)
    unique_id = f"{device.address}_{DESCRIPTION.key}"
    if entity_id := registry.async_get_entity_id(Platform.NUMBER, DOMAIN, unique_id):
        registry.async_remove(entity_id)


class TrikiKnobPosition(TrikiEntity, RestoreNumber):
    # set it to a lamp's brightness while the cap sleeps, then turn from there
    _requires_connection = False

    async def async_added_to_hass(self) -> None:
        # Deliberately not calling TrikiEntity.async_added_to_hass: the value
        # changes with knob events only, not with every battery or signal update.
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self.device.knob_position = min(100.0, max(0.0, float(last.native_value)))
        self.async_on_remove(self.device.async_add_event_listener(self._handle_event))

    @property
    def native_value(self) -> int:
        return round(self.device.knob_position)

    async def async_set_native_value(self, value: float) -> None:
        self.device.knob_position = float(value)
        self.async_write_ha_state()

    @callback
    def _handle_event(self, kind: str, _data: dict[str, Any]) -> None:
        if kind in KNOB_EVENTS:
            self.async_write_ha_state()
