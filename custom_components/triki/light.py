"""The green LED (CTRL characteristic bit0)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ColorMode,
    LightEntity,
    LightEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TrikiConfigEntry
from .entity import TrikiEntity

PARALLEL_UPDATES = 1  # one GATT write at a time

DESCRIPTION = LightEntityDescription(key="led", translation_key="led")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrikiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([TrikiLed(entry.runtime_data, DESCRIPTION)])


class TrikiLed(TrikiEntity, LightEntity):
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}
    # keep the last known state while the token sleeps instead of flapping
    # unavailable on every wake/sleep cycle; turning it on while asleep raises
    _requires_connection = False

    @property
    def is_on(self) -> bool | None:
        return self.device.led_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.device.async_set_led(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.device.async_set_led(False)
