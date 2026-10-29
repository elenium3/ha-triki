"""End-to-end: advertisement -> connect -> stream -> HA entities/events."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    CONF_ADDRESS,
    EVENT_HOMEASSISTANT_STOP,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.triki.const import (
    BUS_EVENT,
    CONF_IDLE_TIMEOUT,
    CONF_RATE,
    CONF_SLEEP_TIMEOUT,
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_SLEEP_TIMEOUT,
    DOMAIN,
)
from custom_components.triki.protocol import (
    CTRL_UUID,
    DEFAULT_RATE,
    NUS_RX_UUID,
    NUS_TX_UUID,
    start_command,
)

from .conftest import (
    ADDRESS,
    BATTERY,
    BUTTON,
    CONNECTED,
    EVENT,
    LED,
    NAME,
    connect,
    service_info,
)
from .helpers import frame


async def test_asleep_state(hass: HomeAssistant, setup) -> None:
    assert hass.states.get(EVENT).state == STATE_UNKNOWN
    assert hass.states.get(CONNECTED).state == "off"
    assert hass.states.get(BUTTON).state == "off"  # not pressed while asleep
    assert hass.states.get(LED).state != STATE_UNAVAILABLE  # last known state kept
    with pytest.raises(HomeAssistantError):
        await setup.runtime_data.async_set_led(True)


async def test_stale_advertisement_ignored(hass: HomeAssistant, setup) -> None:
    info = service_info()
    info.time -= 60
    with patch("custom_components.triki.device.establish_connection", AsyncMock()) as est:
        setup.runtime_data._on_advertisement(info, None)
        await hass.async_block_till_done()
    est.assert_not_awaited()


async def test_wake_stream_events(hass: HomeAssistant, setup) -> None:
    bus = async_capture_events(hass, BUS_EVENT)
    client, notify = await connect(hass, setup)

    client.write_gatt_char.assert_any_await(NUS_RX_UUID, start_command(DEFAULT_RATE), response=True)
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
    assert hass.states.get(BUTTON).state == "off"
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


async def test_capture_option(hass: HomeAssistant, mock_bluetooth, tmp_path) -> None:
    import json as _json

    hass.config.config_dir = str(tmp_path)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ADDRESS,
        title=NAME,
        data={CONF_ADDRESS: ADDRESS},
        options={"capture": True},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client, notify = await connect(hass, entry)
    notify(None, bytearray(frame() * 2))
    entry.runtime_data._on_disconnect(client)
    await hass.async_block_till_done()
    # the capture file is written from an executor job that block_till_done
    # does not wait for, so poll for it briefly
    for _ in range(50):
        files = list((tmp_path / "triki_captures").glob("*.jsonl"))
        if files:
            break
        await asyncio.sleep(0.02)
    assert len(files) == 1
    recs = [_json.loads(x) for x in files[0].read_text().splitlines()]
    assert recs[0]["meta"]["rate"] == DEFAULT_RATE
    assert any(r.get("event") == "wake" for r in recs)
    assert any("hex" in r for r in recs)
    assert recs[-1]["disconnected"] is True


async def test_ha_stop_closes_the_link(hass: HomeAssistant, setup) -> None:
    """HA does not unload entries on shutdown; the link must still be closed."""
    client, _ = await connect(hass, setup)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    client.disconnect.assert_awaited()
    assert setup.runtime_data.connected is False


async def test_unload_rediscovers_address(hass: HomeAssistant, setup) -> None:
    with patch("custom_components.triki.bluetooth.async_rediscover_address") as redisc:
        assert await hass.config_entries.async_unload(setup.entry_id)
    redisc.assert_called_once_with(hass, ADDRESS)


async def test_own_disconnect_echo_is_silent(hass: HomeAssistant, setup, caplog) -> None:
    """bleak reports the disconnect we asked for; that is not an 'old client'."""
    import logging

    dev = setup.runtime_data
    client, _ = await connect(hass, setup)
    caplog.set_level(logging.DEBUG, logger="custom_components.triki")
    await dev.async_disconnect()
    dev._on_disconnect(client)
    await hass.async_block_till_done()
    assert "ignoring drop" not in caplog.text


async def test_own_disconnect_sends_stop_first(hass: HomeAssistant, setup) -> None:
    from custom_components.triki.protocol import stop_command

    dev = setup.runtime_data
    client, _ = await connect(hass, setup)
    dev._last_activity -= 10_000
    dev._idle_check(None)
    await hass.async_block_till_done()
    calls = [c.args for c in client.write_gatt_char.await_args_list]
    assert calls[-1] == (NUS_RX_UUID, stop_command())
    client.disconnect.assert_awaited()

    # a failing stop write must not keep the link open
    dev._await_sleep = False  # the idle gate would otherwise refuse this connect
    dev._no_connect_until = dev._last_attempt = 0
    client, _ = await connect(hass, setup)
    client.write_gatt_char.side_effect = BleakError("gone")
    await dev.async_disconnect()
    client.disconnect.assert_awaited()
    assert dev.connected is False


async def _setup_entry(hass: HomeAssistant, **kwargs) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=ADDRESS, title=NAME, data={CONF_ADDRESS: ADDRESS}, **kwargs
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_migrate_v1_idle_timeout_becomes_sleep_timeout(
    hass: HomeAssistant, mock_bluetooth
) -> None:
    """In v1 idle_timeout dropped the link; that value now belongs to sleep_timeout."""
    entry = await _setup_entry(hass, version=1, options={CONF_IDLE_TIMEOUT: 45, CONF_RATE: 26})
    assert entry.version == 2
    assert entry.options[CONF_SLEEP_TIMEOUT] == 45
    assert entry.options[CONF_IDLE_TIMEOUT] == DEFAULT_IDLE_TIMEOUT
    assert entry.options[CONF_RATE] == 26
    assert entry.runtime_data.options.sleep_timeout == 45


async def test_migrate_v1_without_idle_timeout_keeps_defaults(
    hass: HomeAssistant, mock_bluetooth
) -> None:
    entry = await _setup_entry(hass, version=1)
    assert entry.version == 2
    assert CONF_SLEEP_TIMEOUT not in entry.options
    assert entry.runtime_data.options.sleep_timeout == DEFAULT_SLEEP_TIMEOUT


async def test_migrate_refuses_newer_entry(hass: HomeAssistant, mock_bluetooth) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=ADDRESS, title=NAME, data={CONF_ADDRESS: ADDRESS}, version=3
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.MIGRATION_ERROR
