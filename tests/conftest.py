from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.backends.device import BLEDevice
from habluetooth import BluetoothServiceInfoBleak
from homeassistant.components.bluetooth import MONOTONIC_TIME
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.triki.const import DOMAIN
from custom_components.triki.protocol import (
    BATTERY_LEVEL_UUID,
    CTRL_UUID,
    FIRMWARE_REV_UUID,
    NUS_TX_UUID,
)

ADDRESS = "AA:BB:CC:DD:EE:FF"
NAME = "Triki 0000"

EVENT = "event.triki_0000_action"
BUTTON = "binary_sensor.triki_0000_button"
CONNECTED = "binary_sensor.triki_0000_connected"
LED = "light.triki_0000_led"
BATTERY = "sensor.triki_0000_battery"

ESTABLISH = "custom_components.triki.device.establish_connection"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def mock_close_stale():
    """No BlueZ in the test environment: the stale-link sweep at setup is a no-op."""
    with patch("custom_components.triki.close_stale_connections_by_address", AsyncMock()) as mock:
        yield mock


def service_info(name: str = NAME, address: str = ADDRESS) -> BluetoothServiceInfoBleak:
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=-60,
        manufacturer_data={},
        service_data={},
        service_uuids=[],
        source="local",
        device=BLEDevice(address, name, {}),
        advertisement=None,
        connectable=True,
        time=MONOTONIC_TIME(),
        tx_power=None,
    )


def make_client():
    """A connected bleak client that answers the characteristic reads we do."""
    client = MagicMock()
    client.is_connected = True
    reads = {
        FIRMWARE_REV_UUID: b"1.2.3\x00",
        BATTERY_LEVEL_UUID: bytes([87]),
        CTRL_UUID: b"\x00",
    }

    async def read(uuid):
        return reads.get(uuid, b"")

    client.read_gatt_char = AsyncMock(side_effect=read)
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.disconnect = AsyncMock()
    return client


@pytest.fixture
async def setup(hass: HomeAssistant, mock_bluetooth):
    """A set up config entry for one token, still asleep."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=ADDRESS, title=NAME, data={CONF_ADDRESS: ADDRESS}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def connect(hass: HomeAssistant, entry):
    """Wake the token: one fresh advertisement, connect succeeds, stream starts."""
    client = make_client()
    with patch(ESTABLISH, AsyncMock(return_value=client)) as est:
        entry.runtime_data._on_advertisement(service_info(), None)
        await hass.async_block_till_done()
    assert est.await_count == 1
    # the stream subscription (the battery characteristic is subscribed too)
    notify_cb = next(
        c.args[1] for c in client.start_notify.await_args_list if c.args[0] == NUS_TX_UUID
    )
    return client, notify_cb
