"""End-to-end: advertisement -> connect -> stream -> HA entities/events."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.triki.const import BUS_EVENT, DOMAIN
from custom_components.triki.protocol import (
    CTRL_UUID,
    BATTERY_LEVEL_UUID,
    FIRMWARE_REV_UUID,
    NUS_RX_UUID,
    NUS_TX_UUID,
    start_command,
)

from .conftest import ADDRESS, NAME, service_info
from .helpers import frame

EVENT = "event.triki_0000_action"
BUTTON = "binary_sensor.triki_0000_button"
CONNECTED = "binary_sensor.triki_0000_connected"
LED = "light.triki_0000_led"
BATTERY = "sensor.triki_0000_battery"


def make_client():
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
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=ADDRESS, title=NAME, data={CONF_ADDRESS: ADDRESS}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def connect(hass, entry):
    client = make_client()
    with patch(
        "custom_components.triki.device.establish_connection",
        AsyncMock(return_value=client),
    ) as est:
        entry.runtime_data._on_advertisement(service_info(), None)
        await hass.async_block_till_done()
    assert est.await_count == 1
    notify_cb = client.start_notify.await_args.args[1]
    return client, notify_cb


async def test_asleep_state(hass: HomeAssistant, setup) -> None:
    assert hass.states.get(EVENT).state == STATE_UNKNOWN
    assert hass.states.get(CONNECTED).state == "off"
    assert hass.states.get(BUTTON).state == STATE_UNAVAILABLE
    assert hass.states.get(LED).state == STATE_UNAVAILABLE
    with pytest.raises(HomeAssistantError):
        await setup.runtime_data.async_set_led(True)


async def test_stale_advertisement_ignored(hass: HomeAssistant, setup) -> None:
    info = service_info()
    info.time -= 60
    with patch(
        "custom_components.triki.device.establish_connection", AsyncMock()
    ) as est:
        setup.runtime_data._on_advertisement(info, None)
        await hass.async_block_till_done()
    est.assert_not_awaited()


async def test_wake_stream_events(hass: HomeAssistant, setup) -> None:
    bus = async_capture_events(hass, BUS_EVENT)
    client, notify = await connect(hass, setup)

    client.write_gatt_char.assert_any_await(NUS_RX_UUID, start_command(104), response=True)
    assert client.start_notify.await_args.args[0] == NUS_TX_UUID
    assert hass.states.get(CONNECTED).state == "on"
    assert hass.states.get(BATTERY).state == "87"
    assert hass.states.get(EVENT).attributes["event_type"] == "wake"
    assert bus[-1].data["type"] == "wake"
    assert bus[-1].data["device_id"]

    # 20 noise frames are discarded, then settle, then a short button press
    stream = frame() * 80 + frame(button=True) * 10 + frame() * 60
    for i in range(0, len(stream), 20):
        notify(None, bytearray(stream[i : i + 20]))
    await hass.async_block_till_done()
    assert hass.states.get(EVENT).attributes["event_type"] == "press"
    assert [e.data["type"] for e in bus] == ["wake", "press"]

    # LED
    await hass.services.async_call("light", "turn_on", {"entity_id": LED}, blocking=True)
    client.write_gatt_char.assert_awaited_with(CTRL_UUID, b"\x01", response=True)
    assert hass.states.get(LED).state == "on"


async def test_drop_and_idle(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    client, _ = await connect(hass, setup)
    # link drop from the token going to sleep
    dev._on_disconnect(client)
    await hass.async_block_till_done()
    assert hass.states.get(CONNECTED).state == "off"
    assert hass.states.get(BUTTON).state == STATE_UNAVAILABLE
    # battery survives sleep
    assert hass.states.get(BATTERY).state == "87"

    # idle disconnect
    dev._last_attempt = 0
    client, _ = await connect(hass, setup)
    dev._last_activity -= 10_000
    dev._idle_check(None)
    await hass.async_block_till_done()
    client.disconnect.assert_awaited()
    assert hass.states.get(CONNECTED).state == "off"


async def test_unload(hass: HomeAssistant, setup) -> None:
    client, _ = await connect(hass, setup)
    assert await hass.config_entries.async_unload(setup.entry_id)
    await hass.async_block_till_done()
    client.disconnect.assert_awaited()
