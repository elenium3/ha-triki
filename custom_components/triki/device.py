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
from homeassistant.helpers.event import async_call_later

from .const import (
    BATTERY_POLL_INTERVAL,
    BUS_EVENT,
    DOMAIN,
    TILT_PUBLISH_INTERVAL,
)
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
    ) -> None:
        self.hass = hass
        self.address = address
        self.name = name
        self.rate = rate
        self.idle_timeout = idle_timeout

        self._parser = FrameParser()
        self._detector = GestureDetector(rate, knob_step, invert_rotation)

        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._stopping = False
        self._expected_disconnect = False
        self._last_attempt = 0.0
        self._unsub_adv: CALLBACK_TYPE | None = None
        self._unsub_idle: CALLBACK_TYPE | None = None
        self._unsub_battery: CALLBACK_TYPE | None = None

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

    async def async_stop(self) -> None:
        self._stopping = True
        if self._unsub_adv:
            self._unsub_adv()
            self._unsub_adv = None
        await self.async_disconnect()

    @callback
    def _on_advertisement(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        if service_info.rssi != self.rssi:
            self.rssi = service_info.rssi
            self._notify()
        if self._stopping or self.connected or self._lock.locked():
            return
        if bluetooth.MONOTONIC_TIME() - service_info.time > _FRESH_ADV_S:
            return
        now = time.monotonic()
        if now - self._last_attempt < _RECONNECT_BACKOFF_S:
            return
        self._last_attempt = now
        self.hass.async_create_background_task(
            self._async_connect(service_info.device),
            f"{DOMAIN}_connect_{self.address}",
        )

    def _ble_device(self, fallback: BLEDevice) -> BLEDevice:
        return (
            bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            or fallback
        )

    async def _async_connect(self, ble_device: BLEDevice) -> None:
        async with self._lock:
            if self.connected or self._stopping:
                return
            try:
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

            self._client = client
            self._expected_disconnect = False
            try:
                await self._async_session_setup(client)
            except (BleakError, TimeoutError) as err:
                _LOGGER.debug("%s: session setup failed: %s", self.name, err)
                self._expected_disconnect = True
                await client.disconnect()
                return

            self.connected = True
            self._last_activity = time.monotonic()
            self._schedule_idle_check()
            self._schedule_battery_poll()
            _LOGGER.debug("%s: connected, streaming at %s Hz", self.name, self.rate)
            self._emit("wake")
            self._notify()

    async def _async_session_setup(self, client: BleakClient) -> None:
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

        self._parser.reset()
        self._detector.reset()
        self._last_motion_t = 0.0
        await client.start_notify(NUS_TX_UUID, self._on_notify)
        await client.write_gatt_char(NUS_RX_UUID, start_command(self.rate), response=True)

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

    def _on_disconnect(self, _client: BleakClient) -> None:
        # bleak may call this from another thread on some backends
        self.hass.loop.call_soon_threadsafe(self._handle_disconnected)

    @callback
    def _handle_disconnected(self) -> None:
        if self._client is None and not self.connected:
            return
        if not self._expected_disconnect:
            _LOGGER.debug("%s: link dropped (token asleep?)", self.name)
        self._client = None
        was_connected = self.connected
        self.connected = False
        for unsub in (self._unsub_idle, self._unsub_battery):
            if unsub:
                unsub()
        self._unsub_idle = self._unsub_battery = None
        for ev in self._detector.flush():
            self._emit(ev.type, ev.data)
        self.button = False
        if was_connected:
            self._notify()

    # ------------------------------------------------------------ streaming
    @callback
    def _on_notify(self, _char: Any, data: bytearray) -> None:
        changed = False
        for frame in self._parser.push(data):
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
