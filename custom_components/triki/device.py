"""Connection manager for one Triki token.

Lifecycle: the token sleeps a few seconds after it stops moving and only
advertises while awake (button press / motion). We listen for its
advertisements through Home Assistant's Bluetooth stack (local adapter or
ESPHome proxy), connect as soon as it shows up, start the IMU stream, turn
samples into events, and drop the link after ``idle_timeout`` seconds without
activity so the coin cell is not drained by a 104 Hz stream.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import timedelta
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
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from .const import (
    BATTERY_POLL_INTERVAL,
    BUS_EVENT,
    DOMAIN,
    TILT_PUBLISH_INTERVAL,
)
from .capture import Capture
from .gestures import GestureDetector
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
# The token can accept the connection but refuse to stream (start ack 21 01, no
# frames). Do not keep waking it in a loop.
_STREAM_WATCHDOG_S = 3.0
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


class TrikiDevice:
    """State + BLE session for a single token."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        name: str,
        rate: int,
        idle_timeout: int,
        knob_step: float,
        invert_rotation: bool,
        capture: bool = False,
        wake_as_press: bool = False,
        multi_press_window: float = 0.5,
        motion_gestures: bool = False,
        multi_press: bool = False,
        knob: bool = False,
        shake: bool = False,
    ) -> None:
        self.hass = hass
        self.address = address
        self.name = name
        self.rate = rate
        self.idle_timeout = idle_timeout
        self.wake_as_press = wake_as_press
        # BlueZ/bleak may deliver one notification several times (the count grew by
        # one per connection in captures): ignore other clients and repeats.
        self._stale_notifs = 0
        self._dup_notifs = 0
        self._last_chunk: bytes | None = None
        self._last_chunk_t = 0.0

        self._parser = FrameParser()
        self._detector = GestureDetector(
            rate,
            knob_step,
            invert_rotation,
            multi_press_window_s=multi_press_window,
            motion_gestures=motion_gestures,
            multi_press=multi_press,
            knob=knob,
            shake=shake,
        )
        self._capture = Capture(hass, name) if capture else None

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
    def async_add_event_listener(
        self, cb: Callable[[str, dict[str, Any]], None]
    ) -> CALLBACK_TYPE:
        self._event_listeners.append(cb)
        return lambda: self._event_listeners.remove(cb)

    @callback
    def _notify(self) -> None:
        for cb in list(self._state_listeners):
            cb()

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
        info = bluetooth.async_last_service_info(
            self.hass, self.address, connectable=True
        )
        if info is not None:
            self._maybe_connect(info, _POLL_FRESH_S)

    @callback
    def _on_advertisement(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        if service_info.rssi != self.rssi:
            self.rssi = service_info.rssi
            self._notify()
        _LOGGER.debug(
            "%s: advert via %s rssi %s age %.1fs",
            self.name,
            service_info.source,
            service_info.rssi,
            bluetooth.MONOTONIC_TIME() - service_info.time,
        )
        self._maybe_connect(service_info, _FRESH_ADV_S)

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
            if age < max_age:
                self._awake_seen = now
            if now - self._awake_seen >= _SLEEP_GAP_S:
                self._await_sleep = False
                reason = "token slept, waiting for a fresh wake-up"
            else:
                reason = "waiting for the token to sleep after an idle disconnect"
        elif age > max_age:
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
        # taken here, not inside the task: the lock is only acquired once the task
        # runs, and a second advertisement in between would queue a second attempt
        self._connecting = True
        self.hass.async_create_background_task(
            self._async_connect(service_info.device, service_info.time),
            f"{DOMAIN}_connect_{self.address}",
        )

    def _ble_device(self, fallback: BLEDevice) -> BLEDevice:
        return (
            bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            or fallback
        )

    async def _async_connect(self, ble_device: BLEDevice, seen: float | None = None) -> None:
        try:
            await self._async_connect_locked(ble_device, seen)
        finally:
            self._connecting = False

    async def _async_connect_locked(
        self, ble_device: BLEDevice, seen: float | None
    ) -> None:
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
                _LOGGER.debug("%s: cannot connect: %s", self.name, err)
                return
            except (BleakError, TimeoutError) as err:
                _LOGGER.debug("%s: connect failed: %s", self.name, err)
                return

            if self._stopping:  # unloaded while connecting: do not leave a live link
                await client.disconnect()
                return
            t_link = time.monotonic()
            old = self._client
            if old is not None and old is not client:
                # should not happen; never abandon a client that may still be linked
                self.hass.async_create_background_task(
                    old.disconnect(), f"{DOMAIN}_stale_{self.address}"
                )
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
            self._last_activity = time.monotonic()
            self._unsub_watchdog = async_call_later(
                self.hass, _STREAM_WATCHDOG_S, self._stream_watchdog
            )
            self._schedule_idle_check()
            self._schedule_battery_poll()
            _LOGGER.debug(
                "%s: connected, streaming at %s Hz (advert age %.1fs, link %.1fs, setup %.1fs: notify %.1fs, write %.1fs)",
                self.name, self.rate, adv_age, t_link - t0, time.monotonic() - t_link,
                d_notify, d_write,
            )
            # The token drops the link on its own on a weak signal; reconnecting
            # right away is a resume, not a new wake-up. Only report "wake" if it was
            # gone long enough to have actually slept (or this is the first link).
            resumed = self._last_drop and time.monotonic() - self._last_drop < _WAKE_GAP_S
            if not resumed:
                self._emit("wake")
                if self.wake_as_press:
                    # the press that woke the token is over before the link is up
                    self._emit("press", {"count": 1, "source": "wake"})
            self._notify()
            self.hass.async_create_background_task(
                self._async_read_info(client), f"{DOMAIN}_info_{self.address}"
            )

    async def _async_read_info(self, client: BleakClient) -> None:
        """Read the slow, non-essential characteristics once the stream runs.

        The token goes back to sleep a few seconds after waking up, so nothing
        that is not needed to start the IMU stream may delay it.
        """
        try:
            if self.firmware is None:
                self.firmware = await self._read_str(client, FIRMWARE_REV_UUID)
                self.hardware = await self._read_str(client, HARDWARE_REV_UUID)
                self._update_device_registry()
            await self._read_battery(client)
            try:
                ctrl = await client.read_gatt_char(CTRL_UUID)
                self.led_on = bool(ctrl and ctrl[0] & 0x01)
            except BleakError:
                self.led_on = None
        except (BleakError, TimeoutError) as err:
            _LOGGER.debug("%s: info read failed: %s", self.name, err)
        if self._client is client:
            self._notify()

    async def _async_session_setup(self, client: BleakClient) -> tuple[float, float]:
        if self._capture:
            self._capture.start(
                {
                    "name": self.name,
                    "rate": self.rate,
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
        await client.start_notify(
            NUS_TX_UUID, lambda char, data: self._on_notify_from(client, char, data)
        )
        t_notify = time.monotonic()
        await client.write_gatt_char(NUS_RX_UUID, start_command(self.rate), response=True)
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

    @callback
    def _update_device_registry(self) -> None:
        if self.device_id is None:
            return
        dev_reg = dr.async_get(self.hass)
        dev_reg.async_update_device(
            self.device_id, sw_version=self.firmware, hw_version=self.hardware
        )

    async def async_disconnect(self) -> None:
        client = self._client
        if client is None:
            return
        self._expected_disconnect = True
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
            # a late drop report from an earlier client must not tear down the
            # current session (the next poll would then open a second link)
            _LOGGER.debug("%s: ignoring drop of an old client", self.name)
            return
        if self._client is None and not self.connected:
            return
        if not self._expected_disconnect:
            _LOGGER.debug("%s: link dropped (token asleep?)", self.name)
        if self._stale_notifs or self._dup_notifs:
            _LOGGER.debug(
                "%s: dropped %d notifications from other clients, %d repeats",
                self.name, self._stale_notifs, self._dup_notifs,
            )
        self._client = None
        self._last_drop = bluetooth.MONOTONIC_TIME()
        was_connected = self.connected
        self.connected = False
        for unsub in (self._unsub_idle, self._unsub_battery, self._unsub_watchdog):
            if unsub:
                unsub()
        self._unsub_idle = self._unsub_battery = self._unsub_watchdog = None
        for ev in self._detector.flush():
            self._emit(ev.type, ev.data)
        if self._capture:
            self._capture.write(
                {"disconnected": True, "expected": self._expected_disconnect}
            )
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
        for frame in self._parser.push(data):
            if not self._streaming:
                self._streaming = True
                if self._unsub_watchdog:
                    self._unsub_watchdog()
                    self._unsub_watchdog = None
            sample = Sample.from_frame(frame)
            for ev in self._detector.update(sample):
                self._last_activity = time.monotonic()
                self._emit(ev.type, ev.data)
            if sample.button != self.button:
                self.button = sample.button
                self._last_activity = time.monotonic()
                changed = True
        if self._detector.last_motion_t != self._last_motion_t:
            self._last_motion_t = self._detector.last_motion_t
            self._last_activity = time.monotonic()

        now = time.monotonic()
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
        _LOGGER.debug(
            "%s: no frames %.0fs after start: the token refused to stream, backing off %.0fs",
            self.name, _STREAM_WATCHDOG_S, _NO_STREAM_COOLDOWN_S,
        )
        self._no_connect_until = time.monotonic() + _NO_STREAM_COOLDOWN_S
        self.hass.async_create_background_task(
            self.async_disconnect(), f"{DOMAIN}_nostream_{self.address}"
        )

    @callback
    def _schedule_idle_check(self) -> None:
        if self.idle_timeout <= 0:
            return
        self._unsub_idle = async_call_later(self.hass, _IDLE_CHECK_S, self._idle_check)

    @callback
    def _idle_check(self, _now: Any) -> None:
        self._unsub_idle = None
        if not self.connected:
            return
        if self.button or time.monotonic() - self._last_activity < self.idle_timeout:
            self._schedule_idle_check()
            return
        _LOGGER.debug("%s: idle for %ss, disconnecting", self.name, self.idle_timeout)
        self._await_sleep = True
        self._awake_seen = time.monotonic()
        self._no_connect_until = time.monotonic() + _IDLE_COOLDOWN_S
        self.hass.async_create_background_task(
            self.async_disconnect(), f"{DOMAIN}_idle_{self.address}"
        )

    @callback
    def _schedule_battery_poll(self) -> None:
        self._unsub_battery = async_call_later(
            self.hass, BATTERY_POLL_INTERVAL, self._battery_poll
        )

    @callback
    def _battery_poll(self, _now: Any) -> None:
        self._unsub_battery = None
        if not self.connected or self._client is None:
            return
        client = self._client

        async def _run() -> None:
            await self._read_battery(client)
            self._notify()
            if self.connected:
                self._schedule_battery_poll()

        self.hass.async_create_background_task(_run(), f"{DOMAIN}_battery_{self.address}")

    # ------------------------------------------------------------ commands
    async def async_set_led(self, on: bool) -> None:
        if not self.connected or self._client is None:
            raise HomeAssistantError(
                f"{self.name} is asleep; press its button to wake it up first"
            )
        try:
            await self._client.write_gatt_char(CTRL_UUID, led_command(on), response=True)
        except BleakError as err:
            raise HomeAssistantError(f"LED write failed: {err}") from err
        self.led_on = on
        self._last_activity = time.monotonic()
        self._notify()
