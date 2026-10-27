"""Sensors: battery (restored across sleep), RSSI, tilt."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TrikiConfigEntry
from .device import TrikiDevice
from .entity import TrikiEntity


@dataclass(frozen=True, kw_only=True)
class TrikiSensorDescription(SensorEntityDescription):
    value_fn: Callable[[TrikiDevice], float | int | None]
    requires_connection: bool = True
    restore: bool = False


DESCRIPTIONS = (
    TrikiSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.battery,
        requires_connection=False,
        restore=True,
    ),
    TrikiSensorDescription(
        key="rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.rssi,
        requires_connection=False,
    ),
    TrikiSensorDescription(
        key="pitch",
        translation_key="pitch",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.pitch,
    ),
    TrikiSensorDescription(
        key="roll",
        translation_key="roll",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.roll,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TrikiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(TrikiSensor(entry.runtime_data, d) for d in DESCRIPTIONS)


class TrikiSensor(TrikiEntity, RestoreSensor):
    entity_description: TrikiSensorDescription

    def __init__(self, device: TrikiDevice, description: TrikiSensorDescription) -> None:
        super().__init__(device, description)
        self._requires_connection = description.requires_connection
        self._restored: float | int | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.entity_description.restore and (
            last := await self.async_get_last_sensor_data()
        ):
            self._restored = last.native_value  # type: ignore[assignment]

    @property
    def native_value(self) -> float | int | None:
        value = self.entity_description.value_fn(self.device)
        if value is None and self.entity_description.restore:
            return self._restored
        return value
