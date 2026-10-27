"""Base entity for Triki."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription

from .device import TrikiDevice


class TrikiEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    # Only meaningful while the token is awake and linked.
    _requires_connection = True

    def __init__(self, device: TrikiDevice, description: EntityDescription) -> None:
        self.device = device
        self.entity_description = description
        self._attr_unique_id = f"{device.address}_{description.key}"
        self._attr_device_info = DeviceInfo(
            connections={(dr.CONNECTION_BLUETOOTH, device.address)}
        )

    @property
    def available(self) -> bool:
        return self.device.connected or not self._requires_connection

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.device.async_add_listener(self.async_write_ha_state))
