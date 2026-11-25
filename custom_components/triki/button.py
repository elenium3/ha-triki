"""Identify: blink the cap's LED to tell which cap this is."""

from __future__ import annotations

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TrikiConfigEntry
from .entity import TrikiEntity

PARALLEL_UPDATES = 1  # one GATT write at a time

# named by its device class: Home Assistant translates "Identify" itself
DESCRIPTION = ButtonEntityDescription(
    key="identify",
    device_class=ButtonDeviceClass.IDENTIFY,
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrikiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([TrikiIdentify(entry.runtime_data, DESCRIPTION)])


class TrikiIdentify(TrikiEntity, ButtonEntity):
    # available while the cap sleeps, like the LED switch: pressed then, it
    # says the cap is asleep instead of sitting greyed out with no reason
    _requires_connection = False

    async def async_added_to_hass(self) -> None:
        """Nothing to follow: a button has no state of its own."""

    async def async_press(self) -> None:
        await self.device.async_identify()
