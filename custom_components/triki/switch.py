"""The green LED (CTRL characteristic bit0), as a configuration switch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import STATE_OFF, STATE_ON, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

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


class TrikiLed(TrikiEntity, SwitchEntity, RestoreEntity):
    # keep the last known state while the token sleeps instead of flapping
    # unavailable on every wake/sleep cycle; turning it on while asleep raises
    _requires_connection = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # the token may sleep for hours: without this the LED reads unknown after
        # every Home Assistant restart until it wakes and the CTRL read runs
        if (
            self.device.led_on is None
            and (last := await self.async_get_last_state())
            and last.state in (STATE_ON, STATE_OFF)
        ):
            self.device.led_on = last.state == STATE_ON

    @property
    def is_on(self) -> bool | None:
        return self.device.led_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.device.async_set_led(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.device.async_set_led(False)
