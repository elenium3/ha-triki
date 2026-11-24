"""The green LED (CTRL characteristic bit0), as a configuration switch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TrikiConfigEntry
from .entity import TrikiEntity

PARALLEL_UPDATES = 1  # one GATT write at a time

# an indicator LED, not a lamp: a config switch keeps it out of area light
# groups and "turn off all the lights"
DESCRIPTION = SwitchEntityDescription(
    key="led", translation_key="led", entity_category=EntityCategory.CONFIG
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrikiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([TrikiLed(entry.runtime_data, DESCRIPTION)])


class TrikiLed(TrikiEntity, SwitchEntity):
    # The token's LED cannot be read back (CTRL reads ff whatever it shows), so
    # the state is only what Home Assistant set during the current link: on and
    # off are offered as two buttons, not a toggle that claims to know.
    _attr_assumed_state = True
    # available while the token sleeps; turning it on then says it is asleep
    _requires_connection = False

    @property
    def is_on(self) -> bool | None:
        return self.device.led_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.device.async_set_led(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.device.async_set_led(False)
