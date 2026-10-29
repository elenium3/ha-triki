"""TrikiDevice failure paths: connect errors, setup errors, gating, polling."""

import asyncio
import logging
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError
from bleak_retry_connector import BleakNotFoundError, BleakOutOfConnectionSlotsError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.triki.const import BUS_EVENT
from custom_components.triki.protocol import (
    BATTERY_LEVEL_UUID,
    CTRL_UUID,
    FIRMWARE_REV_UUID,
    HARDWARE_REV_UUID,
)

from .conftest import BATTERY, CONNECTED, ESTABLISH, make_client, service_info, settle


async def advertise(hass: HomeAssistant, entry, client=None, side_effect=None):
    """Send one fresh advertisement with establish_connection mocked."""
    mock = AsyncMock(return_value=client, side_effect=side_effect)
    with patch(ESTABLISH, mock):
        entry.runtime_data._on_advertisement(service_info(), None)
        await hass.async_block_till_done()
    return mock


@pytest.mark.parametrize(
    "exc",
    [
        BleakNotFoundError("gone"),
        BleakOutOfConnectionSlotsError("no slots"),
        BleakError("boom"),
        TimeoutError(),
    ],
)
async def test_connect_errors_leave_device_asleep(hass: HomeAssistant, setup, exc) -> None:
    est = await advertise(hass, setup, side_effect=exc)
    assert est.await_count == 1
    assert hass.states.get(CONNECTED).state == "off"
    assert setup.runtime_data._client is None


async def test_session_setup_failure_disconnects(hass: HomeAssistant, setup) -> None:
    client = make_client()
    client.start_notify = AsyncMock(side_effect=BleakError("notify failed"))
    await advertise(hass, setup, client)
    client.disconnect.assert_awaited()
    assert hass.states.get(CONNECTED).state == "off"
    assert setup.runtime_data.connected is False


async def test_optional_reads_may_fail(hass: HomeAssistant, setup) -> None:
    """Firmware, battery and LED reads failing must not abort the session."""
    client = make_client()

    async def read(uuid):
        if uuid in (FIRMWARE_REV_UUID, BATTERY_LEVEL_UUID, CTRL_UUID):
            raise BleakError("not readable")
        return b""

    client.read_gatt_char = AsyncMock(side_effect=read)
    await advertise(hass, setup, client)
    dev = setup.runtime_data
    assert dev.connected is True
    assert dev.firmware is None
    assert dev.battery is None
    assert dev.led_on is None


async def test_hung_connect_does_not_swallow_next_wakeup(hass: HomeAssistant, setup) -> None:
    """A connect that never returns must release the lock so the next wake-up works."""
    dev = setup.runtime_data

    async def hang(*args, **kwargs):
        await asyncio.Event().wait()

    with patch("custom_components.triki.device._CONNECT_TIMEOUT_S", 0.05):
        est = await advertise(hass, setup, side_effect=hang)
        assert est.await_count == 1
        # the connect runs as a background task: wait for the timeout for real
        for _ in range(100):
            if not dev._lock.locked():
                break
            await asyncio.sleep(0.01)
        assert not dev._lock.locked()
        assert hass.states.get(CONNECTED).state == "off"

        dev._last_attempt = 0  # backoff over; the token woke up again
        est = await advertise(hass, setup, make_client())
    assert est.await_count == 1
    assert hass.states.get(CONNECTED).state == "on"


async def test_stream_starts_before_slow_reads(hass: HomeAssistant, setup) -> None:
    """The token sleeps seconds after waking: start the stream first, read later."""
    client = make_client()
    gate = asyncio.Event()

    async def slow_read(uuid):
        await gate.wait()  # reads are slow / never come back in time
        return b""

    client.read_gatt_char = AsyncMock(side_effect=slow_read)
    est = AsyncMock(return_value=client)
    with patch(ESTABLISH, est):
        setup.runtime_data._on_advertisement(service_info(), None)
        for _ in range(20):  # let the connect task run; reads stay blocked
            await asyncio.sleep(0)
    names = [c[0] for c in client.method_calls]
    assert names.index("start_notify") < names.index("read_gatt_char")
    assert names.index("write_gatt_char") < names.index("read_gatt_char")
    assert hass.states.get(CONNECTED).state == "on"  # not held up by the reads
    gate.set()
    await hass.async_block_till_done()


async def test_advertisement_backoff(hass: HomeAssistant, setup) -> None:
    """A second advertisement right after a failed attempt is ignored."""
    est = await advertise(hass, setup, side_effect=BleakError("boom"))
    assert est.await_count == 1
    est = await advertise(hass, setup, side_effect=BleakError("boom"))
    assert est.await_count == 0
    # once the backoff is over the next advertisement retries
    setup.runtime_data._last_attempt = 0
    est = await advertise(hass, setup, side_effect=BleakError("boom"))
    assert est.await_count == 1


async def test_advertisement_ignored_while_connected(hass: HomeAssistant, setup) -> None:
    await advertise(hass, setup, make_client())
    assert setup.runtime_data.connected
    setup.runtime_data._last_attempt = 0
    est = await advertise(hass, setup, make_client())
    assert est.await_count == 0


LAST_INFO = "custom_components.triki.device.bluetooth.async_last_service_info"


async def poll(hass: HomeAssistant, entry, info, client=None):
    """Poll as the 1 s timer does, with HA's last advertisement set to ``info``."""
    est = AsyncMock(return_value=client)
    with patch(LAST_INFO, return_value=info), patch(ESTABLISH, est):
        entry.runtime_data._poll_awake(None)
        await hass.async_block_till_done()
    return est


async def test_poll_connects_without_advertisement_callback(hass: HomeAssistant, setup) -> None:
    """HA drops unchanged advertisements, so the callback never fires again.

    The token must still be picked up from the last seen advertisement.
    """
    est = await poll(hass, setup, service_info(), make_client())
    assert est.await_count == 1
    assert hass.states.get(CONNECTED).state == "on"


async def test_poll_ignores_stale_or_missing_advertisement(hass: HomeAssistant, setup) -> None:
    stale = service_info()
    stale.time -= 30  # token went back to sleep long ago
    assert (await poll(hass, setup, stale, make_client())).await_count == 0
    assert (await poll(hass, setup, None, make_client())).await_count == 0
    assert hass.states.get(CONNECTED).state == "off"


async def test_no_instant_reconnect_after_idle_disconnect(hass: HomeAssistant, setup) -> None:
    """After an idle drop the still-awake token must sleep before we reconnect.

    Reconnecting while it is still advertising resets its sleep timer, so it would
    never sleep and we would reconnect forever. We wait for its advertisements to
    go stale (it slept), then reconnect only on a genuinely fresh wake-up.
    """
    dev = setup.runtime_data
    await advertise(hass, setup, make_client())
    dev._last_activity -= 10_000
    dev._idle_check(None)
    await hass.async_block_till_done()
    assert hass.states.get(CONNECTED).state == "off"
    assert dev._await_sleep is True

    # the token is still advertising: a fresh wake-up must be ignored, even once
    # the short cooldown is over, and it keeps pushing the sleep deadline out
    dev._last_attempt = 0
    dev._no_connect_until = 0
    assert (await poll(hass, setup, service_info(), make_client())).await_count == 0
    assert dev._await_sleep is True

    # its advertisements stop for long enough: the token slept. The next poll with
    # no fresh advert clears the wait (but does not connect on the stale advert).
    dev._awake_seen -= 30
    stale = service_info()
    stale.time -= 30
    assert (await poll(hass, setup, stale, make_client())).await_count == 0
    assert dev._await_sleep is False

    # the next genuine wake-up connects again
    dev._last_attempt = 0
    assert (await poll(hass, setup, service_info(), make_client())).await_count == 1


async def test_quick_reconnect_after_drop_is_not_a_new_wake(hass: HomeAssistant, setup) -> None:
    """A weak-signal link loss followed by an immediate reconnect is a resume.

    The token did not sleep, so the reconnect must not emit a second ``wake``.
    """
    dev = setup.runtime_data
    bus = async_capture_events(hass, BUS_EVENT)

    await advertise(hass, setup, make_client())
    assert [e.data["type"] for e in bus] == ["wake"]

    # the token drops the link on its own, then re-advertises right away
    dev._handle_disconnected()
    await hass.async_block_till_done()
    dev._last_attempt = 0
    await advertise(hass, setup, make_client())

    assert dev.connected is True
    assert [e.data["type"] for e in bus] == ["wake"]  # no second wake on resume


async def test_slow_reconnect_after_drop_is_still_a_resume(hass: HomeAssistant, setup) -> None:
    """The resume window is measured from the start of the connect, not its end.

    A link that takes seconds to come up after a weak-signal drop must not turn
    the resume into a second ``wake``.
    """
    dev = setup.runtime_data
    bus = async_capture_events(hass, BUS_EVENT)
    await advertise(hass, setup, make_client())
    dev._handle_disconnected()
    await hass.async_block_till_done()
    dev._last_attempt = 0

    async def slow(*_args, **_kwargs):
        await asyncio.sleep(0.15)  # longer than the (patched) resume window
        return make_client()

    with patch("custom_components.triki.device._WAKE_GAP_S", 0.1):
        await advertise(hass, setup, side_effect=slow)
        for _ in range(100):
            if dev.connected:
                break
            await asyncio.sleep(0.01)
    assert dev.connected
    assert [e.data["type"] for e in bus] == ["wake"]


async def test_revision_reads_are_retried_and_never_wipe_the_registry(
    hass: HomeAssistant, setup
) -> None:
    dev = setup.runtime_data
    registry = dr.async_get(hass)
    # a value stored by an earlier run of the integration
    registry.async_update_device(dev.device_id, sw_version="old")

    def reader(fail: str, answers: dict[str, bytes]):
        async def read(uuid):
            if uuid == fail:
                raise BleakError("busy")
            return answers.get(uuid, b"")

        return AsyncMock(side_effect=read)

    # first link: the firmware read fails, the hardware read answers
    client = make_client()
    client.read_gatt_char = reader(FIRMWARE_REV_UUID, {HARDWARE_REV_UUID: b"A"})
    await advertise(hass, setup, client)
    assert dev.firmware is None and dev.hardware == "A"
    device = registry.async_get(dev.device_id)
    assert device.sw_version == "old"  # not wiped by the failed read
    assert device.hw_version == "A"

    # next link: the firmware read is retried
    dev._handle_disconnected()
    await hass.async_block_till_done()
    dev._last_attempt = 0
    client = make_client()
    client.read_gatt_char = reader(HARDWARE_REV_UUID, {FIRMWARE_REV_UUID: b"1.2.3"})
    await advertise(hass, setup, client)
    assert dev.firmware == "1.2.3" and dev.hardware == "A"
    device = registry.async_get(dev.device_id)
    assert (device.sw_version, device.hw_version) == ("1.2.3", "A")


async def test_repeated_connect_failures_are_logged_once(
    hass: HomeAssistant, setup, caplog
) -> None:
    caplog.set_level(logging.INFO, logger="custom_components.triki")
    dev = setup.runtime_data
    for _ in range(4):
        dev._last_attempt = 0
        await advertise(hass, setup, side_effect=BleakError("boom"))
    assert caplog.text.count("connect attempts in a row failed") == 1
    dev._last_attempt = 0
    await advertise(hass, setup, make_client())
    assert dev.connected
    assert "connected again" in caplog.text


async def test_battery_notification_updates_the_sensor(hass: HomeAssistant, setup) -> None:
    client = make_client()
    await advertise(hass, setup, client)
    dev = setup.runtime_data
    assert hass.states.get(BATTERY).state == "87"
    battery_cb = next(
        c.args[1] for c in client.start_notify.await_args_list if c.args[0] == BATTERY_LEVEL_UUID
    )
    battery_cb(None, bytearray([83]))
    await hass.async_block_till_done()
    assert hass.states.get(BATTERY).state == "83"
    battery_cb(None, bytearray())  # empty payload: ignored
    assert dev.battery == 83


async def test_advertisement_updates_rssi(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    info = service_info()
    info.time -= 60  # stale: must not trigger a connect, but rssi is still tracked
    with patch(ESTABLISH, AsyncMock()) as est:
        dev._on_advertisement(info, None)
        await hass.async_block_till_done()
    est.assert_not_awaited()
    assert dev.rssi == info.rssi


def battery_callback(client):
    return next(
        c.args[1] for c in client.start_notify.await_args_list if c.args[0] == BATTERY_LEVEL_UUID
    )


def answer_stop_with_battery(hass: HomeAssistant, client, level: int) -> None:
    """Make the token behave as measured: a battery notification follows a STOP."""
    from custom_components.triki.protocol import stop_command

    async def write(uuid, data, response=False):
        if data == stop_command():
            hass.loop.call_soon(battery_callback(client), None, bytearray([level]))

    client.write_gatt_char = AsyncMock(side_effect=write)


def written(client) -> list[bytes]:
    return [c.args[1] for c in client.write_gatt_char.await_args_list]


async def test_idle_switch_pauses_the_stream_for_a_battery_measurement(
    hass: HomeAssistant, setup
) -> None:
    """The token measures its battery only while not streaming (exp9/exp10)."""
    from custom_components.triki.const import IDLE_RATE
    from custom_components.triki.protocol import start_command, stop_command

    client = make_client()
    await advertise(hass, setup, client)
    dev = setup.runtime_data
    assert hass.states.get(BATTERY).state == "87"  # the under-load value at connect
    answer_stop_with_battery(hass, client, 82)
    dev._last_activity -= 100  # past idle_timeout, not past sleep_timeout
    dev._idle_check(None)
    await settle(hass, dev)
    assert written(client) == [stop_command(), start_command(IDLE_RATE)]
    assert hass.states.get(BATTERY).state == "82"
    assert dev.stream_rate == IDLE_RATE
    assert not dev._battery_refresh_due()


async def test_battery_pause_ends_on_timeout(hass: HomeAssistant, setup) -> None:
    from custom_components.triki.const import IDLE_RATE
    from custom_components.triki.protocol import start_command, stop_command

    client = make_client()
    await advertise(hass, setup, client)
    dev = setup.runtime_data
    client.write_gatt_char = AsyncMock()  # a token that never answers the STOP
    dev._last_activity -= 100
    with patch("custom_components.triki.device._BATTERY_REFRESH_WAIT_S", 0.01):
        dev._idle_check(None)
        await settle(hass, dev)
    assert written(client) == [stop_command(), start_command(IDLE_RATE)]
    assert hass.states.get(BATTERY).state == "87"  # unchanged, but the stream is back
    assert not dev._battery_refresh_due()  # no hammering: next try after the interval


async def test_no_second_pause_before_the_interval(hass: HomeAssistant, setup) -> None:
    from custom_components.triki.const import IDLE_RATE
    from custom_components.triki.protocol import start_command

    client = make_client()
    await advertise(hass, setup, client)
    dev = setup.runtime_data
    client.write_gatt_char.reset_mock()
    dev._battery_refreshed = dev._last_activity  # refreshed a moment ago
    dev._last_activity -= 100  # past idle_timeout, not past sleep_timeout
    dev._idle_check(None)
    await settle(hass, dev)
    assert written(client) == [start_command(IDLE_RATE)]


async def test_battery_check_refreshes_a_long_idle_link(hass: HomeAssistant, setup) -> None:
    from custom_components.triki.protocol import start_command, stop_command

    client = make_client()
    await advertise(hass, setup, client)
    dev = setup.runtime_data
    answer_stop_with_battery(hass, client, 80)
    # just used: nothing happens, the check is re-armed
    dev._battery_check(None)
    await hass.async_block_till_done()
    assert written(client) == []
    assert dev._unsub_battery is not None
    # idle for long enough: pause at the current rate
    dev._last_activity -= 100
    dev._battery_check(None)
    await settle(hass, dev)
    assert written(client) == [stop_command(), start_command(dev.options.rate)]
    assert hass.states.get(BATTERY).state == "80"


async def test_battery_check_noop_when_disconnected(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    dev._battery_check(None)
    await hass.async_block_till_done()
    assert dev._unsub_battery is None


async def test_connect_read_only_while_battery_unknown(hass: HomeAssistant, setup) -> None:
    """A measured value must not be replaced by the under-load read of the next link."""
    client = make_client()
    await advertise(hass, setup, client)
    dev = setup.runtime_data
    battery_callback(client)(None, bytearray([82]))
    await hass.async_block_till_done()
    assert hass.states.get(BATTERY).state == "82"
    dev._handle_disconnected()
    await hass.async_block_till_done()
    dev._last_attempt = 0
    client = make_client()
    await advertise(hass, setup, client)
    assert BATTERY_LEVEL_UUID not in [c.args[0] for c in client.read_gatt_char.await_args_list]
    assert hass.states.get(BATTERY).state == "82"


async def test_led_write_error(hass: HomeAssistant, setup) -> None:
    client = make_client()
    await advertise(hass, setup, client)
    dev = setup.runtime_data
    client.write_gatt_char = AsyncMock(side_effect=BleakError("write failed"))
    with (
        patch("custom_components.triki.device._LED_WRITE_RETRY_DELAY_S", 0),
        pytest.raises(HomeAssistantError),
    ):
        await dev.async_set_led(True)
    assert dev.led_on is False  # unchanged
    assert client.write_gatt_char.await_count == 3  # all tries used
    assert dev.stats.led_write_retries == 2


async def test_led_write_retried_once_on_gatt_error(hass: HomeAssistant, setup) -> None:
    client = make_client()
    await advertise(hass, setup, client)
    dev = setup.runtime_data
    calls = {"n": 0}

    async def flaky(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BleakError("GATT 0x0e")

    client.write_gatt_char = AsyncMock(side_effect=flaky)
    with patch("custom_components.triki.device._LED_WRITE_RETRY_DELAY_S", 0):
        await dev.async_set_led(True)
    assert dev.led_on is True
    assert client.write_gatt_char.await_count == 2
    assert dev.stats.led_write_retries == 1


async def test_led_write_timeout_is_not_retried(hass: HomeAssistant, setup) -> None:
    client = make_client()
    await advertise(hass, setup, client)
    dev = setup.runtime_data

    async def hang(*_args, **_kwargs):
        await asyncio.sleep(10)

    client.write_gatt_char = AsyncMock(side_effect=hang)
    with (
        patch("custom_components.triki.device._LED_WRITE_TIMEOUT_S", 0.01),
        pytest.raises(HomeAssistantError),
    ):
        await dev.async_set_led(True)
    assert client.write_gatt_char.await_count == 1
    assert dev.stats.led_write_retries == 0
    client.write_gatt_char = AsyncMock()  # the stop write at unload must not hang


async def test_idle_check_keeps_link_while_button_held(hass: HomeAssistant, setup) -> None:
    client = make_client()
    await advertise(hass, setup, client)
    dev = setup.runtime_data
    dev.button = True
    dev._last_activity -= 10_000
    dev._idle_check(None)
    await hass.async_block_till_done()
    client.disconnect.assert_not_awaited()
    assert dev.connected
    assert dev._unsub_idle is not None  # re-armed


async def test_wake_as_press_emits_press(hass: HomeAssistant, setup) -> None:
    from pytest_homeassistant_custom_component.common import async_capture_events

    bus = async_capture_events(hass, "triki_event")
    dev = setup.runtime_data
    dev.options = replace(dev.options, wake_as_press=True)
    await advertise(hass, setup, make_client())
    assert [e.data["type"] for e in bus] == ["wake", "press"]
    assert bus[1].data["source"] == "wake"


async def test_wake_alone_by_default(hass: HomeAssistant, setup) -> None:
    from pytest_homeassistant_custom_component.common import async_capture_events

    bus = async_capture_events(hass, "triki_event")
    await advertise(hass, setup, make_client())
    assert [e.data["type"] for e in bus] == ["wake"]


async def test_no_reconnect_on_advertisement_older_than_drop(hass: HomeAssistant, setup) -> None:
    """After the token drops the link, its last advertisement is stale news.

    Connecting to the sleeping token hangs until the timeout and would hold the
    lock against the next real wake-up.
    """
    dev = setup.runtime_data
    old = service_info()
    old.time -= 1
    await advertise(hass, setup, make_client())
    dev._on_disconnect(None)
    await hass.async_block_till_done()
    dev._last_attempt = 0
    assert (await poll(hass, setup, old, make_client())).await_count == 0
    dev._last_attempt = 0
    assert (await poll(hass, setup, service_info(), make_client())).await_count == 1


async def test_repeated_notifications_are_dropped(hass: HomeAssistant, setup) -> None:
    """BlueZ delivered every notification N times; the parser must see it once."""
    from .helpers import frame
    from .test_init import connect

    client, notify = await connect(hass, setup)
    dev = setup.runtime_data
    chunk = bytearray(frame() * 1 + frame()[:6])
    for _ in range(5):
        notify(None, chunk)
    assert dev._dup_notifs == 4


async def test_notifications_from_old_client_are_ignored(hass: HomeAssistant, setup) -> None:
    from .helpers import frame
    from .test_init import connect

    client, notify = await connect(hass, setup)
    dev = setup.runtime_data
    dev._client = make_client()  # the link was replaced; `notify` is the old client's
    notify(None, bytearray(frame()))
    assert dev._stale_notifs == 1


async def test_late_drop_of_old_client_keeps_current_session(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    client = make_client()
    await advertise(hass, setup, client)
    assert dev.connected
    dev._on_disconnect(make_client())  # drop report from some earlier client
    await hass.async_block_till_done()
    assert dev.connected
    assert dev._client is client
    dev._on_disconnect(client)
    await hass.async_block_till_done()
    assert not dev.connected


async def test_second_advertisement_while_connecting_queues_nothing(
    hass: HomeAssistant, setup
) -> None:
    dev = setup.runtime_data
    gate = asyncio.Event()

    async def slow(*args, **kwargs):
        await gate.wait()
        return make_client()

    est = AsyncMock(side_effect=slow)
    with patch(ESTABLISH, est):
        dev._on_advertisement(service_info(), None)  # task created, lock not taken yet
        dev._last_attempt = 0
        dev._on_advertisement(service_info(), None)
        await asyncio.sleep(0)
        gate.set()
        await hass.async_block_till_done()
    assert est.await_count == 1
    assert dev._connecting is False


async def test_unload_while_connecting_closes_the_link(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    client = make_client()
    gate = asyncio.Event()

    async def slow(*args, **kwargs):
        await gate.wait()
        return client

    with patch(ESTABLISH, AsyncMock(side_effect=slow)):
        dev._on_advertisement(service_info(), None)
        await asyncio.sleep(0)
        dev._stopping = True  # what async_stop does first
        gate.set()
        await hass.async_block_till_done()
    client.disconnect.assert_awaited()
    assert not dev.connected
    client.start_notify.assert_not_awaited()


async def test_token_that_refuses_to_stream_is_dropped_and_left_alone(
    hass: HomeAssistant, setup
) -> None:
    """Start ack 21 01 and no frames: disconnect and back off, do not loop."""
    dev = setup.runtime_data
    client = make_client()
    await advertise(hass, setup, client)
    assert dev.connected and not dev._streaming
    dev._stream_watchdog(None)  # 3 s without a single frame
    await hass.async_block_till_done()
    client.disconnect.assert_awaited()
    assert not dev.connected
    dev._last_attempt = 0
    assert (await poll(hass, setup, service_info(), make_client())).await_count == 0


async def test_streaming_token_cancels_the_watchdog(hass: HomeAssistant, setup) -> None:
    from .helpers import frame
    from .test_init import connect

    client, notify = await connect(hass, setup)
    dev = setup.runtime_data
    assert dev._unsub_watchdog is not None
    notify(None, bytearray(frame()))
    assert dev._streaming and dev._unsub_watchdog is None


async def test_unload_cancels_hung_connect(hass: HomeAssistant, setup) -> None:
    """A connect still in flight is tied to the entry and dies with it."""
    cancelled = asyncio.Event()

    async def hang(*_args, **_kwargs):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with patch(ESTABLISH, hang):
        setup.runtime_data._on_advertisement(service_info(), None)
        await asyncio.sleep(0)
        assert setup.runtime_data._connecting
        assert await hass.config_entries.async_unload(setup.entry_id)
        await hass.async_block_till_done()
    assert cancelled.is_set()
