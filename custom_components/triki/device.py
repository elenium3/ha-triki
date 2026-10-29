"""Connection manager for one Triki token.

Lifecycle: the token sleeps a few seconds after it stops moving and only
advertises while awake (button press / motion). We listen for its
advertisements through Home Assistant's Bluetooth stack (local adapter or
ESPHome proxy), connect as soon as it shows up, start the IMU stream and turn
samples into events. After ``idle_timeout`` seconds without activity the link
stays up but the stream is re-started at ``IDLE_RATE`` (a fresh link is slow
and lossy for 10-20 s, so dropping it is the expensive path); the first motion
or press brings the configured rate back. Only after ``sleep_timeout`` seconds
is the link dropped so the token can sleep.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import timedelta
from itertools import pairwise
from typing import Any

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    BleakNotFoundError,
    BleakOutOfConnectionSlotsError,
    establish_connection,
)
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.typing import UNDEFINED

from .capture import Capture
from .const import (
    BATTERY_REFRESH_INTERVAL,
    BUS_EVENT,
    DOMAIN,
    IDLE_RATE,
    TILT_PUBLISH_INTERVAL,
)
from .gestures import GestureDetector
from .models import TrikiOptions
from .protocol import (
    BATTERY_LEVEL_UUID,
    CTRL_UUID,
    FIRMWARE_REV_UUID,
    HARDWARE_REV_UUID,
    NUS_RX_UUID,
    NUS_TX_UUID,
    FrameParser,
    Sample,
    led_command,
    start_command,
    stop_command,
)

_LOGGER = logging.getLogger(__name__)

# An advertisement older than this is a replay from the cache, not a wake-up.
_FRESH_ADV_S = 10.0
_IDLE_CHECK_S = 2.0
_RECONNECT_BACKOFF_S = 3.0
# Home Assistant only calls advertisement callbacks when the advertised data
# changes. Triki always advertises the same payload, so after the first wake-up
# the callback goes silent for minutes. We therefore also poll the last seen
# advertisement: if it is this fresh, the token is awake right now.
_CONNECT_TIMEOUT_S = 12.0
_POLL_S = 1.0
_POLL_FRESH_S = 10.0
_ADVERT_HISTORY = 32  # advertisement timestamps kept for the cadence figures
_ADVERT_NOTIFY_S = 1.0  # rssi state writes and advert log lines at most this often
# The token can accept the connection but refuse to stream (start ack 21 01, no
# frames). Do not keep waking it in a loop.
_STREAM_WATCHDOG_S = 3.0
_STOP_TIMEOUT_S = 2.0  # the stop write must not hold up an idle/unload disconnect
_NO_STREAM_COOLDOWN_S = 60.0
_DUP_WINDOW_S = 0.003  # identical chunks closer than this are one notification
# After we drop the link on idle, the token keeps advertising for several more
# seconds. Reconnecting in that window resets its sleep timer, so it never sleeps
# and we reconnect forever. Instead wait until its advertisements go stale (it
# slept), then only reconnect on a genuinely fresh wake-up. This is how long with
# no advertisement counts as "asleep".
_IDLE_COOLDOWN_S = 10.0
# A reconnect sooner than this after a drop is a resume of the same awake session
# (a weak-signal link loss), not a fresh wake-up, so it must not re-emit "wake".
_WAKE_GAP_S = 5.0
# How long the token must stop advertising before we treat it as asleep and arm
# for the next wake-up. Must outlast the few seconds it keeps advertising after we
# drop the link, or we would reconnect to the same still-awake token.
_SLEEP_GAP_S = 15.0
# The LED write fails now and then with a GATT error on a fresh link (seen by
# other clients too); a short retry is enough.
_LED_WRITE_TIMEOUT_S = 5.0
_LED_WRITE_RETRIES = 3
_LED_WRITE_RETRY_DELAY_S = 0.3
# This many connect failures in a row for an awake token is worth one line at
# info level (the entities only show "asleep", which looks normal).
_UNREACHABLE_AFTER = 3
# Battery: the token re-measures only while the stream is stopped and then pushes
# the value by notification (6 s after STOP on the test unit). The value read
# right after a connect is taken under load (27 % against 82 % at rest on the
# same cell) and never changes while the stream runs.
_BATTERY_REFRESH_WAIT_S = 10.0  # how long the stream may stay stopped for a measurement
_BATTERY_CHECK_S = 60.0  # how often to look for an idle moment once a refresh is due
_BATTERY_IDLE_FOR_REFRESH_S = 30.0  # no presses or motion for this long before pausing


@dataclass(slots=True)
class LinkStats:
    """Counters since setup, exposed through diagnostics."""

    adverts: int = 0  # advertisements seen (every one on HA 2026.10+, changed ones before)
    connects: int = 0
    connect_failures: int = 0
    drops: int = 0  # the token (or the radio) closed the link, not us
    stream_refusals: int = 0  # connected, but no frames after the start command
    notifications: int = 0
    frames: int = 0
    rate_switches: int = 0  # idle <-> active stream rate changes over the live link
    led_write_retries: int = 0  # LED writes that needed a second (or third) try
    parser_dropped_bytes: int = 0
    last_source: str | None = None  # scanner the last connect went through
    last_link_s: float | None = None  # time to establish the last link
    last_session_s: float | None = None  # how long the last link lasted


class TrikiDevice:
    """State + BLE session for a single token."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        name: str,
        options: TrikiOptions,
        *,
        entry: ConfigEntry,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.address = address
        self.name = name
        self.options = options
        self.stream_rate = options.rate  # what the token was last told to stream at
        self._rate_write_pending = False
        # BlueZ/bleak may deliver one notification several times (the count grew by
        # one per connection in captures): ignore other clients and repeats.
        self._stale_notifs = 0
        self._dup_notifs = 0
        self._last_chunk: bytes | None = None
        self._last_chunk_t = 0.0
        self.stats = LinkStats()
        self._session_t0 = 0.0

        self._parser = FrameParser()
        self._detector = GestureDetector(
            options.rate,
            knob_step_deg=options.knob_step,
            invert_rotation=options.invert_rotation,
            multi_press_window_s=options.multi_press_window,
            motion_gestures=options.motion_gestures,
            multi_press=options.multi_press,
            knob=options.knob,
            shake=options.shake,
        )
        self._capture = Capture(hass, name) if options.capture else None

        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._stopping = False
        self._connecting = False
        self._expected_disconnect = False
        self._last_attempt = 0.0
        self._no_connect_until = 0.0
        self._await_sleep = False
        self._awake_seen = 0.0
        self._last_drop = 0.0
        self._last_skip: str | None = None
        self.every_advertisement = False  # the HA 2026.10 per-advertisement callback is in use
        self._advert_times: deque[float] = deque(maxlen=_ADVERT_HISTORY)
        self._last_advert_notify = 0.0
        self._fail_streak = 0
        self._unreachable_logged = False
        # monotonic time of the last stream pause for it; -inf so the first idle
        # switch refreshes even on a host whose monotonic clock is young
        self._battery_refreshed = float("-inf")
        self._battery_event = asyncio.Event()  # set by a battery notification
        self._battery_pause = False  # the stream is stopped for a measurement right now
        self._unsub_adv: CALLBACK_TYPE | None = None
        self._unsub_poll: CALLBACK_TYPE | None = None
        self._unsub_idle: CALLBACK_TYPE | None = None
        self._unsub_battery: CALLBACK_TYPE | None = None
        self._unsub_watchdog: CALLBACK_TYPE | None = None
        self._streaming = False

        self._state_listeners: list[Callable[[], None]] = []
        self._event_listeners: list[Callable[[str, dict[str, Any]], None]] = []

        # public state
        self.connected = False
        self.button = False
        self.led_on: bool | None = None
        self.battery: int | None = None
        self.rssi: int | None = None
        self.firmware: str | None = None
        self.hardware: str | None = None
        self.pitch: float | None = None
        self.roll: float | None = None
        self.device_id: str | None = None

        self._last_activity = 0.0
        self._last_motion_t = 0.0
        self._last_tilt_pub = 0.0

    # ------------------------------------------------------------ listeners
    @callback
    def async_add_listener(self, cb: Callable[[], None]) -> CALLBACK_TYPE:
        self._state_listeners.append(cb)
        return lambda: self._state_listeners.remove(cb)

    @callback
    def async_add_event_listener(self, cb: Callable[[str, dict[str, Any]], None]) -> CALLBACK_TYPE:
        self._event_listeners.append(cb)
        return lambda: self._event_listeners.remove(cb)

    @callback
    def _notify(self) -> None:
        for cb in list(self._state_listeners):
            cb()

    @callback
    def _create_task(self, coro: Coroutine[Any, Any, Any], name: str) -> None:
        """Run a background task that dies with the config entry (unload cancels it)."""
        self.entry.async_create_background_task(self.hass, coro, f"{DOMAIN}_{name}_{self.address}")

    @callback
    def _emit(self, kind: str, data: dict[str, Any] | None = None) -> None:
        data = data or {}
        _LOGGER.debug("%s: event %s %s", self.name, kind, data)
        if self._capture:
            self._capture.write({"event": kind, "data": data})
        for cb in list(self._event_listeners):
            cb(kind, data)
        self.hass.bus.async_fire(
            BUS_EVENT,
            {
                "device_id": self.device_id,
                "address": self.address,
                "type": kind,
                **data,
            },
        )

    # ------------------------------------------------------------ lifecycle
    @callback
    def async_start(self) -> None:
        self._stopping = False
        # Home Assistant 2026.10 delivers every advertisement of an address;
        # older versions only changed ones (the token's payload never changes),
        # which is why they also need the 1 s poll of the last advertisement.
        register_every = getattr(bluetooth, "async_register_advertisement_callback", None)
        if register_every is not None:
            self.every_advertisement = True
            self._unsub_adv = register_every(self.hass, self._on_every_advertisement, self.address)
            return
        self._unsub_adv = bluetooth.async_register_callback(
            self.hass,
            self._on_advertisement,
            bluetooth.BluetoothCallbackMatcher(address=self.address, connectable=True),
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
        self._unsub_poll = async_track_time_interval(
            self.hass, self._poll_awake, timedelta(seconds=_POLL_S)
        )

    async def async_stop(self) -> None:
        self._stopping = True
        for attr in ("_unsub_adv", "_unsub_poll"):
            unsub = getattr(self, attr)
            if unsub:
                unsub()
                setattr(self, attr, None)
        await self.async_disconnect()

    @callback
    def _poll_awake(self, _now: Any) -> None:
        """Catch wake-ups whose advertisement HA did not dispatch (unchanged data)."""
        if self._stopping or self.connected or self._lock.locked():
            return
        info = bluetooth.async_last_service_info(self.hass, self.address, connectable=True)
        if info is not None:
            self._maybe_connect(info, _POLL_FRESH_S)

    @callback
    def _on_every_advertisement(self, service_info: bluetooth.BluetoothServiceInfoBleak) -> None:
        if not service_info.connectable:
            return
        self._on_advertisement(service_info, None)

    @callback
    def _on_advertisement(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange | None,
    ) -> None:
        now = time.monotonic()
        self.stats.adverts += 1
        self._advert_times.append(service_info.time)
        rssi_changed = service_info.rssi != self.rssi
        self.rssi = service_info.rssi
        # an awake token advertises several times a second: one state write and
        # one log line per second is plenty
        if now - self._last_advert_notify >= _ADVERT_NOTIFY_S:
            self._last_advert_notify = now
            if rssi_changed:
                self._notify()
            _LOGGER.debug(
                "%s: advert via %s rssi %s age %.1fs",
                self.name,
                service_info.source,
                service_info.rssi,
                bluetooth.MONOTONIC_TIME() - service_info.time,
            )
        self._maybe_connect(service_info, _FRESH_ADV_S)

    @property
    def advertisement_cadence(self) -> dict[str, Any]:
        """Recent advertisement timing for diagnostics (seconds)."""
        times = list(self._advert_times)
        gaps = sorted(b - a for a, b in pairwise(times))
        return {
            "every": self.every_advertisement,
            "recent": len(times),
            "last_age_s": round(bluetooth.MONOTONIC_TIME() - times[-1], 1) if times else None,
            "median_interval_s": round(gaps[len(gaps) // 2], 3) if gaps else None,
            "min_interval_s": round(gaps[0], 3) if gaps else None,
        }

    @callback
    def _maybe_connect(
        self, service_info: bluetooth.BluetoothServiceInfoBleak, max_age: float
    ) -> None:
        if self._stopping or self.connected or self._connecting or self._lock.locked():
            return
        now = time.monotonic()
        age = bluetooth.MONOTONIC_TIME() - service_info.time
        reason = None
        if self._await_sleep:
            # The token keeps advertising for a few seconds after we drop the link;
            # reconnecting then just resets its sleep timer. Only once its
            # advertisements have stopped for a stretch (it actually slept) do we arm
            # for the next genuine wake-up. A fresh advert keeps pushing that out.
            # The gap is judged before this advert refreshes the mark: with the
            # per-advertisement callback this call only ever sees fresh adverts,
            # and the first one after the gap *is* the wake-up to connect on.
            slept = now - self._awake_seen >= _SLEEP_GAP_S
            if age < max_age:
                self._awake_seen = now
            if slept:
                self._await_sleep = False
            else:
                reason = "waiting for the token to sleep after an idle disconnect"
        if reason is None:
            if age > max_age:
                reason = f"advert too old ({age:.1f}s > {max_age:.0f}s)"
            elif service_info.time < self._last_drop:
                # advertisement from before the token fell asleep: it is gone now
                reason = "advert older than the last link drop"
            elif now < self._no_connect_until:
                reason = "idle cooldown"
            elif now - self._last_attempt < _RECONNECT_BACKOFF_S:
                reason = "reconnect backoff"
        if reason:
            if reason.split(" (")[0] != self._last_skip:
                self._last_skip = reason.split(" (")[0]
                _LOGGER.debug(
                    "%s: not connecting: %s (source %s)", self.name, reason, service_info.source
                )
            return
        self._last_skip = None
        self._last_attempt = now
        self.stats.last_source = service_info.source
        # taken here, not inside the task: the lock is only acquired once the task
        # runs, and a second advertisement in between would queue a second attempt
        self._connecting = True
        self._create_task(self._async_connect(service_info.device, service_info.time), "connect")

    def _ble_device(self, fallback: BLEDevice) -> BLEDevice:
        return (
            bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
            or fallback
        )

    async def _async_connect(self, ble_device: BLEDevice, seen: float | None = None) -> None:
        try:
            await self._async_connect_locked(ble_device, seen)
        finally:
            self._connecting = False

    async def _async_connect_locked(self, ble_device: BLEDevice, seen: float | None) -> None:
        async with self._lock:
            if self.connected or self._stopping:
                return
            t0 = time.monotonic()
            adv_age = bluetooth.MONOTONIC_TIME() - seen if seen else -1.0
            try:
                # bleak_retry_connector may retry for a minute (20 s per attempt,
                # 4 s backoff on "no slot"). The token is awake for seconds only,
                # and the lock would swallow every wake-up meanwhile.
                async with asyncio.timeout(_CONNECT_TIMEOUT_S):
                    client = await establish_connection(
                        BleakClientWithServiceCache,
                        ble_device,
                        self.name,
                        disconnected_callback=self._on_disconnect,
                        max_attempts=2,
                        ble_device_callback=lambda: self._ble_device(ble_device),
                    )
            except (BleakNotFoundError, BleakOutOfConnectionSlotsError) as err:
                self._connect_failed("cannot connect", err)
                return
            except (BleakError, TimeoutError) as err:
                self._connect_failed("connect failed", err)
                return

            if self._stopping:  # unloaded while connecting: do not leave a live link
                await client.disconnect()
                return
            t_link = time.monotonic()
            old = self._client
            if old is not None and old is not client:
                # should not happen; never abandon a client that may still be linked
                self._create_task(old.disconnect(), "stale")
            self._client = client
            self._expected_disconnect = False
            try:
                d_notify, d_write = await self._async_session_setup(client)
            except (BleakError, TimeoutError) as err:
                _LOGGER.debug("%s: session setup failed: %s", self.name, err)
                self._expected_disconnect = True
                await client.disconnect()
                return

            if self._stopping:
                self._expected_disconnect = True
                await client.disconnect()
                return
            self.connected = True
            self._last_activity = self._session_t0 = time.monotonic()
            self.stats.connects += 1
            self.stats.last_link_s = round(t_link - t0, 2)
            self._fail_streak = 0
            if self._unreachable_logged:
                self._unreachable_logged = False
                _LOGGER.info("%s: connected again (via %s)", self.name, self.stats.last_source)
            self._unsub_watchdog = async_call_later(
                self.hass, _STREAM_WATCHDOG_S, self._stream_watchdog
            )
            self._schedule_idle_check()
            self._schedule_battery_check()
            _LOGGER.debug(
                "%s: connected, streaming at %s Hz (advert age %.1fs, link %.1fs, setup %.1fs: notify %.1fs, write %.1fs)",
                self.name,
                self.options.rate,
                adv_age,
                t_link - t0,
                time.monotonic() - t_link,
                d_notify,
                d_write,
            )
            # The token drops the link on its own on a weak signal; reconnecting
            # right away is a resume, not a new wake-up. Only report "wake" if it was
            # gone long enough to have actually slept (or this is the first link).
            # Measured from the start of this attempt: a slow link must not turn a
            # resume into a wake.
            resumed = self._last_drop and t0 - self._last_drop < _WAKE_GAP_S
            if not resumed:
                self._emit("wake")
                if self.options.wake_as_press:
                    # the press that woke the token is over before the link is up
                    self._emit("press", {"count": 1, "source": "wake"})
            self._notify()
            self._create_task(self._async_read_info(client), "info")

    def _connect_failed(self, what: str, err: BaseException) -> None:
        self.stats.connect_failures += 1
        self._fail_streak += 1
        _LOGGER.debug("%s: %s: %s", self.name, what, err)
        if self._fail_streak == _UNREACHABLE_AFTER and not self._unreachable_logged:
            self._unreachable_logged = True
            _LOGGER.info(
                "%s: %d connect attempts in a row failed (last: %s); "
                "it is seen but cannot be linked, check the receiver placement",
                self.name,
                self._fail_streak,
                err,
            )

    async def _async_read_info(self, client: BleakClient) -> None:
        """Read the slow, non-essential characteristics once the stream runs.

        The token goes back to sleep a few seconds after waking up, so nothing
        that is not needed to start the IMU stream may delay it.
        """
        try:
            if self.firmware is None or self.hardware is None:
                # each read is retried on later links until it succeeds once
                if self.firmware is None:
                    self.firmware = await self._read_str(client, FIRMWARE_REV_UUID)
                if self.hardware is None:
                    self.hardware = await self._read_str(client, HARDWARE_REV_UUID)
                self._update_device_registry()
            if self.battery is None:
                # taken under load right after the connect, so a low number; the
                # first stream pause replaces it. Better than nothing until then.
                await self._read_battery(client)
            try:
                ctrl = await client.read_gatt_char(CTRL_UUID)
                self.led_on = bool(ctrl and ctrl[0] & 0x01)
            except BleakError:
                self.led_on = None
            # the measured value arrives by notification after a stream pause
            try:
                await client.start_notify(
                    BATTERY_LEVEL_UUID,
                    lambda _char, data: self._on_battery_notify(client, data),
                )
            except BleakError as err:
                _LOGGER.debug("%s: battery notify unavailable: %s", self.name, err)
        except (BleakError, TimeoutError) as err:
            _LOGGER.debug("%s: info read failed: %s", self.name, err)
        if self._client is client:
            self._notify()

    @callback
    def _on_battery_notify(self, client: BleakClient, data: bytearray) -> None:
        if client is not self._client or not data:
            return
        level = max(0, min(100, int(data[0])))
        _LOGGER.debug(
            "%s: battery notify %d%% (link age %.1fs, stream %s Hz, %s)",
            self.name,
            level,
            time.monotonic() - self._session_t0,
            self.stream_rate,
            "at rest" if self._battery_pause else "under load, ignored",
        )
        if not self._battery_pause:
            # the token also measures while streaming and reports the change;
            # that value is taken under load (27 % against 82 % at rest on the
            # same cell) and would make the sensor flap
            return
        self._battery_event.set()
        if level != self.battery:
            self.battery = level
            self._notify()

    async def _async_session_setup(self, client: BleakClient) -> tuple[float, float]:
        if self._capture:
            self._capture.start(
                {
                    "name": self.name,
                    "rate": self.options.rate,
                    "platform": "homeassistant",
                    "firmware": self.firmware,
                    "battery": self.battery,
                }
            )
        self._parser.reset()
        self._detector.reset()
        self._last_motion_t = 0.0
        t = time.monotonic()
        self._stale_notifs = self._dup_notifs = 0
        self._last_chunk = None
        self._streaming = False
        self.stream_rate = self.options.rate
        await client.start_notify(
            NUS_TX_UUID, lambda char, data: self._on_notify_from(client, char, data)
        )
        t_notify = time.monotonic()
        await client.write_gatt_char(NUS_RX_UUID, start_command(self.options.rate), response=True)
        return t_notify - t, time.monotonic() - t_notify

    @staticmethod
    async def _read_str(client: BleakClient, uuid: str) -> str | None:
        try:
            raw = await client.read_gatt_char(uuid)
        except BleakError:
            return None
        return bytes(raw).decode("utf-8", "replace").strip("\x00 ") or None

    async def _read_battery(self, client: BleakClient) -> None:
        try:
            raw = await client.read_gatt_char(BATTERY_LEVEL_UUID)
        except BleakError as err:
            _LOGGER.debug("%s: battery read failed: %s", self.name, err)
            return
        if raw:
            self.battery = max(0, min(100, int(raw[0])))
            _LOGGER.debug(
                "%s: battery read %d%% (link age %.1fs, stream %s Hz)",
                self.name,
                self.battery,
                time.monotonic() - self._session_t0,
                self.stream_rate,
            )

    @callback
    def _update_device_registry(self) -> None:
        if self.device_id is None:
            return
        dev_reg = dr.async_get(self.hass)
        # a failed read must not wipe a value stored by an earlier session
        dev_reg.async_update_device(
            self.device_id,
            sw_version=self.firmware if self.firmware is not None else UNDEFINED,
            hw_version=self.hardware if self.hardware is not None else UNDEFINED,
        )

    async def async_disconnect(self) -> None:
        client = self._client
        if client is None:
            return
        self._expected_disconnect = True
        if self.connected:
            # end the stream the way the app does; a token that is told to stop may
            # go to sleep sooner than one whose link just vanished
            try:
                async with asyncio.timeout(_STOP_TIMEOUT_S):
                    await client.write_gatt_char(NUS_RX_UUID, stop_command(), response=True)
            except (BleakError, TimeoutError) as err:
                _LOGGER.debug("%s: stop command failed: %s", self.name, err)
        try:
            await client.disconnect()
        except BleakError as err:
            _LOGGER.debug("%s: disconnect error: %s", self.name, err)
        self._handle_disconnected()

    def _on_disconnect(self, client: BleakClient | None) -> None:
        # bleak may call this from another thread on some backends
        self.hass.loop.call_soon_threadsafe(self._handle_disconnected, client)

    @callback
    def _handle_disconnected(self, client: BleakClient | None = None) -> None:
        if client is not None and client is not self._client:
            if self._client is not None:
                # a late drop report from an earlier client must not tear down the
                # current session (the next poll would then open a second link)
                _LOGGER.debug("%s: ignoring drop of an old client", self.name)
            # else: bleak echoing a disconnect we already handled ourselves
            return
        if self._client is None and not self.connected:
            return
        if not self._expected_disconnect:
            self.stats.drops += 1
            _LOGGER.debug("%s: link dropped (token asleep?)", self.name)
        if self.connected:
            self.stats.last_session_s = round(time.monotonic() - self._session_t0, 1)
        if self._stale_notifs or self._dup_notifs:
            _LOGGER.debug(
                "%s: dropped %d notifications from other clients, %d repeats",
                self.name,
                self._stale_notifs,
                self._dup_notifs,
            )
        self._client = None
        self._last_drop = bluetooth.MONOTONIC_TIME()
        self._battery_event.set()  # do not keep a stream pause waiting on a dead link
        was_connected = self.connected
        self.connected = False
        for unsub in (self._unsub_idle, self._unsub_battery, self._unsub_watchdog):
            if unsub:
                unsub()
        self._unsub_idle = self._unsub_battery = self._unsub_watchdog = None
        for ev in self._detector.flush():
            self._emit(ev.type, ev.data)
        if self._capture:
            self._capture.write({"disconnected": True, "expected": self._expected_disconnect})
            self._capture.stop()
        self.button = False
        if was_connected:
            self._notify()

    # ------------------------------------------------------------ streaming
    @callback
    def _on_notify_from(self, client: BleakClient, char: Any, data: bytearray) -> None:
        if client is not self._client:
            self._stale_notifs += 1
            return
        now = time.monotonic()
        chunk = bytes(data)
        if chunk == self._last_chunk and now - self._last_chunk_t < _DUP_WINDOW_S:
            self._dup_notifs += 1
            return
        self._last_chunk, self._last_chunk_t = chunk, now
        self._on_notify(char, data)

    @callback
    def _on_notify(self, _char: Any, data: bytearray) -> None:
        if self._capture:
            self._capture.write({"hex": bytes(data).hex()})
        changed = False
        active = False
        self.stats.notifications += 1
        frames = list(self._parser.push(data))
        now = time.monotonic()
        dt = self._detector.dt
        for i, frame in enumerate(frames):
            self.stats.frames += 1
            if not self._streaming:
                self._streaming = True
                if self._unsub_watchdog:
                    self._unsub_watchdog()
                    self._unsub_watchdog = None
            sample = Sample.from_frame(frame)
            # frames of one notification arrived together: spread them one
            # sample period apart, ending at the arrival time
            for ev in self._detector.update(sample, now - (len(frames) - 1 - i) * dt):
                active = True
                self._emit(ev.type, ev.data)
            if sample.button != self.button:
                self.button = sample.button
                active = changed = True
        self.stats.parser_dropped_bytes = self._parser.dropped
        if self._detector.last_motion_t != self._last_motion_t:
            self._last_motion_t = self._detector.last_motion_t
            active = True

        now = time.monotonic()
        if active:
            self._last_activity = now
            if self.stream_rate != self.options.rate and not self._rate_write_pending:
                # the token is being used again: back to the configured rate (a
                # write in flight re-checks activity itself when it completes)
                self._create_task(self._async_set_rate(self.options.rate), "fullrate")
        if now - self._last_tilt_pub >= TILT_PUBLISH_INTERVAL:
            pr = self._detector.pitch_roll
            if pr is not None:
                pitch, roll = round(pr[0], 1), round(pr[1], 1)
                if (pitch, roll) != (self.pitch, self.roll):
                    self.pitch, self.roll = pitch, roll
                    changed = True
            self._last_tilt_pub = now
        if changed:
            self._notify()

    # ------------------------------------------------------------ timers
    @callback
    def _stream_watchdog(self, _now: Any) -> None:
        self._unsub_watchdog = None
        if not self.connected or self._streaming:
            return
        self.stats.stream_refusals += 1
        # not debug: this is the one failure the user cannot see from the entities
        _LOGGER.info(
            "%s: no frames %.0fs after start: the token refused to stream, backing off %.0fs",
            self.name,
            _STREAM_WATCHDOG_S,
            _NO_STREAM_COOLDOWN_S,
        )
        self._no_connect_until = time.monotonic() + _NO_STREAM_COOLDOWN_S
        self._create_task(self.async_disconnect(), "nostream")

    @callback
    def _schedule_idle_check(self) -> None:
        if self.options.idle_timeout <= 0 and self.options.sleep_timeout <= 0:
            return
        self._unsub_idle = async_call_later(self.hass, _IDLE_CHECK_S, self._idle_check)

    @callback
    def _idle_check(self, _now: Any) -> None:
        self._unsub_idle = None
        if not self.connected:
            return
        idle = 0.0 if self.button else time.monotonic() - self._last_activity
        sleep_timeout, idle_timeout = self.options.sleep_timeout, self.options.idle_timeout
        if 0 < sleep_timeout <= idle:
            _LOGGER.debug("%s: idle for %ss, disconnecting", self.name, sleep_timeout)
            self._await_sleep = True
            self._awake_seen = time.monotonic()
            self._no_connect_until = time.monotonic() + _IDLE_COOLDOWN_S
            self._create_task(self.async_disconnect(), "idle")
            return
        if (
            0 < idle_timeout <= idle
            and self.stream_rate != IDLE_RATE
            and not self._rate_write_pending
        ):
            # keep the link (a fresh one is slow for 10-20 s and the token would
            # advertise for minutes), just stop asking for a fast stream. The
            # token is idle anyway, so this is the moment for a battery refresh.
            self._create_task(
                self._async_set_rate(IDLE_RATE, refresh=self._battery_refresh_due()), "lowrate"
            )
        self._schedule_idle_check()

    def _battery_refresh_due(self) -> bool:
        return time.monotonic() - self._battery_refreshed >= BATTERY_REFRESH_INTERVAL

    async def _async_pause_for_battery(self, client: BleakClient) -> None:
        """Stop the stream until the token reports a fresh battery level.

        Presses and motion during the pause are not seen, which is why this only
        runs while the token has been idle for a while and rarely.
        """
        self._battery_event.clear()
        self._battery_pause = True
        try:
            async with asyncio.timeout(_STOP_TIMEOUT_S):
                await client.write_gatt_char(NUS_RX_UUID, stop_command(), response=True)
            t = time.monotonic()
            try:
                async with asyncio.timeout(_BATTERY_REFRESH_WAIT_S):
                    await self._battery_event.wait()
            except TimeoutError:
                _LOGGER.debug(
                    "%s: no battery update within %.0fs of the stream pause",
                    self.name,
                    _BATTERY_REFRESH_WAIT_S,
                )
            else:
                _LOGGER.debug(
                    "%s: battery %s%% after a %.1fs stream pause",
                    self.name,
                    self.battery,
                    time.monotonic() - t,
                )
        finally:
            self._battery_pause = False
        self._battery_refreshed = time.monotonic()

    async def _async_set_rate(self, rate: int, *, refresh: bool = False) -> None:
        """Re-send START at another rate over the live link (no reconnect needed).

        Activity that arrives while the write is in flight cannot queue a second
        write (``_rate_write_pending`` gates the callers), so after a switch to
        the idle rate we re-check: if the token was used meanwhile, go straight
        back to the configured rate instead of waiting for the next frame.

        With ``refresh`` the stream is first stopped for a battery measurement.
        """
        if self._rate_write_pending:
            return
        self._rate_write_pending = True
        try:
            while True:
                client = self._client
                if client is None or not self.connected:
                    return
                activity_before = self._last_activity
                try:
                    if refresh:
                        refresh = False
                        await self._async_pause_for_battery(client)
                        if self._client is not client:
                            return
                    async with asyncio.timeout(_STOP_TIMEOUT_S):
                        await client.write_gatt_char(
                            NUS_RX_UUID, start_command(rate), response=True
                        )
                except (BleakError, TimeoutError) as err:
                    _LOGGER.debug("%s: rate change to %s Hz failed: %s", self.name, rate, err)
                    return
                if self._client is not client:
                    return  # the link went away meanwhile
                self.stream_rate = rate
                self.stats.rate_switches += 1
                self._detector.set_rate(rate)
                if self._capture:
                    self._capture.write({"rate": rate})
                _LOGGER.debug(
                    "%s: stream now %s Hz (%s)",
                    self.name,
                    rate,
                    "idle" if rate != self.options.rate else "active",
                )
                if rate == self.options.rate or self._last_activity == activity_before:
                    return
                rate = self.options.rate  # used during the write: back to full rate
        finally:
            self._rate_write_pending = False

    @callback
    def _schedule_battery_check(self) -> None:
        self._unsub_battery = async_call_later(self.hass, _BATTERY_CHECK_S, self._battery_check)

    @callback
    def _battery_check(self, _now: Any) -> None:
        """On a long link, refresh the battery at the next idle moment once due.

        The idle-rate switch already refreshes when it happens; this covers links
        that stay idle for hours and setups with the idle timeout off.
        """
        self._unsub_battery = None
        if not self.connected or self._client is None:
            return
        idle = time.monotonic() - self._last_activity
        if (
            self._battery_refresh_due()
            and not self.button
            and idle >= _BATTERY_IDLE_FOR_REFRESH_S
            and not self._rate_write_pending
        ):
            self._create_task(self._async_set_rate(self.stream_rate, refresh=True), "battery")
        self._schedule_battery_check()

    # ------------------------------------------------------------ commands
    async def async_set_led(self, on: bool) -> None:
        client = self._client
        if not self.connected or client is None:
            # a sleeping token is a device state, not bad input from the caller
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="asleep",
                translation_placeholders={"name": self.name},
            )
        for attempt in range(1, _LED_WRITE_RETRIES + 1):
            try:
                async with asyncio.timeout(_LED_WRITE_TIMEOUT_S):
                    await client.write_gatt_char(CTRL_UUID, led_command(on), response=True)
                break
            except (BleakError, TimeoutError) as err:
                # only a live link is worth another try; a timeout or a lost link
                # is reported right away
                if (
                    isinstance(err, TimeoutError)
                    or attempt == _LED_WRITE_RETRIES
                    or self._client is not client
                ):
                    raise HomeAssistantError(
                        translation_domain=DOMAIN,
                        translation_key="led_write_failed",
                        translation_placeholders={"error": str(err)},
                    ) from err
                self.stats.led_write_retries += 1
                _LOGGER.debug("%s: LED write %d failed (%s), retrying", self.name, attempt, err)
                await asyncio.sleep(_LED_WRITE_RETRY_DELAY_S)
        self.led_on = on
        self._last_activity = time.monotonic()
        self._notify()
