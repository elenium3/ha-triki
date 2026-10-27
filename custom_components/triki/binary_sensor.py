"""Binary sensors: link state and button."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TrikiConfigEntry
from .device import TrikiDevice
from .entity import TrikiEntity


@dataclass(frozen=True, kw_only=True)
class TrikiBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[TrikiDevice], bool]
    requires_connection: bool = True


DESCRIPTIONS = (
    TrikiBinaryDescription(
        key="connected",
        translation_key="connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.connected,
        requires_connection=False,
    ),
    TrikiBinaryDescription(
        key="button",
        translation_key="button",
        value_fn=lambda d: d.button,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrikiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(TrikiBinarySensor(entry.runtime_data, d) for d in DESCRIPTIONS)


class TrikiBinarySensor(TrikiEntity, BinarySensorEntity):
    entity_description: TrikiBinaryDescription

    def __init__(self, device: TrikiDevice, description: TrikiBinaryDescription) -> None:
        super().__init__(device, description)
        self._requires_connection = description.requires_connection

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.device)
