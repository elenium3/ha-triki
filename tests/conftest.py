import pytest
from bleak.backends.device import BLEDevice
from habluetooth import BluetoothServiceInfoBleak

from homeassistant.components.bluetooth import MONOTONIC_TIME

ADDRESS = "AA:BB:CC:DD:EE:FF"
NAME = "Triki 0000"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


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
