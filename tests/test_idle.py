"""Idle handling: low-rate stream first, link drop only after a long idle."""

import asyncio
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.triki.const import BUS_EVENT, IDLE_RATE
from custom_components.triki.protocol import DEFAULT_RATE, NUS_RX_UUID, start_command

from .conftest import MEASURED_BATTERY, connect, settle
from .helpers import frame


async def test_idle_drops_to_low_rate_and_activity_restores_it(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    client, notify = await connect(hass, setup)
    assert dev.stream_rate == DEFAULT_RATE

    dev._last_activity -= 100  # past idle_timeout (30 s), not past sleep_timeout (300 s)
    dev._idle_check(None)
    await settle(hass, dev)  # the first idle switch includes the battery pause
    client.write_gatt_char.assert_awaited_with(NUS_RX_UUID, start_command(IDLE_RATE), response=True)
    assert dev.battery == MEASURED_BATTERY
    client.disconnect.assert_not_awaited()
    assert dev.connected and dev.stream_rate == IDLE_RATE
    assert dev.stats.rate_switches == 1

    # another idle check must not re-send the same command
    client.write_gatt_char.reset_mock()
    dev._idle_check(None)
    await hass.async_block_till_done()
    client.write_gatt_char.assert_not_awaited()

    # motion (after the start-up frames are skipped) brings the full rate back
    notify(None, bytearray(frame() * 22 + frame(gz=500.0) * 10))
    await hass.async_block_till_done()
    client.write_gatt_char.assert_awaited_with(
        NUS_RX_UUID, start_command(DEFAULT_RATE), response=True
    )
    assert dev.stream_rate == DEFAULT_RATE
    assert dev.stats.rate_switches == 2


async def test_button_press_restores_full_rate(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    client, notify = await connect(hass, setup)
    notify(None, bytearray(frame() * 22))  # start-up frames discarded
    bus = async_capture_events(hass, BUS_EVENT)
    dev._last_activity -= 100
    dev._idle_check(None)
    await settle(hass, dev)
    assert dev.stream_rate == IDLE_RATE
    # a press right after the switch must still be reported: the rate change
    # does not re-arm the start-up discard
    notify(None, bytearray(frame(button=True) * 2))
    await hass.async_block_till_done()
    assert dev.stream_rate == DEFAULT_RATE
    assert dev.button is True
    notify(None, bytearray(frame() * 2))
    await hass.async_block_till_done()
    assert [e.data["type"] for e in bus] == ["press"]


async def test_activity_during_idle_write_restores_full_rate(hass: HomeAssistant, setup) -> None:
    """Frames that arrive while the idle-rate write is in flight are not lost."""
    dev = setup.runtime_data
    client, notify = await connect(hass, setup)
    notify(None, bytearray(frame() * 22))
    gate = asyncio.Event()
    writes: list[bytes] = []

    async def slow_write(_uuid, data, response=False):
        writes.append(bytes(data))
        if len(writes) == 1:
            await gate.wait()

    client.write_gatt_char = AsyncMock(side_effect=slow_write)
    dev._battery_refreshed = dev._last_activity  # no battery pause in this test
    dev._last_activity -= 100
    dev._idle_check(None)
    await asyncio.sleep(0)  # the idle write is now in flight
    assert dev._rate_write_pending
    notify(None, bytearray(frame(gz=500.0) * 10))  # motion while waiting for the ack
    assert len(writes) == 1  # no second write queued while one is pending
    gate.set()
    await hass.async_block_till_done()
    assert writes == [start_command(IDLE_RATE), start_command(DEFAULT_RATE)]
    assert dev.stream_rate == DEFAULT_RATE
    assert dev.stats.rate_switches == 2


async def test_long_idle_drops_the_link(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    client, _ = await connect(hass, setup)
    dev._last_activity -= 1000  # past sleep_timeout
    dev._idle_check(None)
    await hass.async_block_till_done()
    client.disconnect.assert_awaited()
    assert dev.connected is False


async def test_held_button_is_not_idle(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    client, notify = await connect(hass, setup)
    notify(None, bytearray(frame() * 22 + frame(button=True) * 2))
    dev._last_activity -= 1000
    dev._idle_check(None)
    await hass.async_block_till_done()
    client.disconnect.assert_not_awaited()
    assert dev.stream_rate == DEFAULT_RATE
