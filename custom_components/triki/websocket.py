"""WebSocket API for the live card.

``triki/devices`` lists the tokens. ``triki/subscribe`` streams one token: a
``status`` message whenever its state changes, ``motion`` messages (pose and
the last frame) at up to 30 per second while frames arrive, and ``event``
messages for gestures. Motion goes over this socket only, never into entity
states, so the recorder is not touched. ``triki/reset_heading`` zeroes yaw.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

# mypy sees voluptuous markers as a different type than the decorator's hint in
# this environment; the schemas are the ones Home Assistant core uses.

if TYPE_CHECKING:
    from .device import TrikiDevice


@callback
def async_register(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_devices)
    websocket_api.async_register_command(hass, ws_subscribe)
    websocket_api.async_register_command(hass, ws_reset_heading)


def _devices(hass: HomeAssistant) -> list[TrikiDevice]:
    return [
        entry.runtime_data
        for entry in hass.config_entries.async_loaded_entries(DOMAIN)
        if entry.runtime_data is not None
    ]


def _find(hass: HomeAssistant, device_id: str | None) -> TrikiDevice | None:
    devices = _devices(hass)
    if device_id is None:
        return devices[0] if len(devices) == 1 else None
    return next((d for d in devices if d.device_id == device_id), None)


def status(dev: TrikiDevice) -> dict[str, Any]:
    return {
        "name": dev.name,
        "device_id": dev.device_id,
        "connected": dev.connected,
        "streaming": dev.connected and dev.streaming,
        "unresponsive": dev.unresponsive,
        "waiting_for_sleep": dev.waiting_for_sleep,
        "battery": dev.battery,
        "rssi": dev.rssi,
        "rate": dev.stream_rate if dev.connected else None,
        "measured_rate": dev.measured_rate,
        "button": dev.button,
        "led": dev.led_on,
        "firmware": dev.firmware,
    }


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/devices"})  # type: ignore[dict-item]
@callback
def ws_devices(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    connection.send_result(
        msg["id"],
        [{"device_id": d.device_id, "name": d.name} for d in _devices(hass)],
    )


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/subscribe", vol.Optional("device_id"): str}  # type: ignore[dict-item]
)
@callback
def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    dev = _find(hass, msg.get("device_id"))
    if dev is None:
        connection.send_error(msg["id"], "not_found", "No such Triki token")
        return
    msg_id = msg["id"]

    @callback
    def send(payload: dict[str, Any]) -> None:
        connection.send_message(websocket_api.event_message(msg_id, payload))

    @callback
    def on_state() -> None:
        send({"type": "status", **status(dev)})

    @callback
    def on_motion(snap: dict[str, Any]) -> None:
        send({"type": "motion", **snap})

    @callback
    def on_event(kind: str, data: dict[str, Any]) -> None:
        send({"type": "event", "event": kind, "data": data})

    unsubs = [
        dev.async_add_listener(on_state),
        dev.async_add_motion_listener(on_motion),
        dev.async_add_event_listener(on_event),
    ]

    @callback
    def unsubscribe() -> None:
        for unsub in unsubs:
            unsub()

    connection.subscriptions[msg_id] = unsubscribe
    connection.send_result(msg_id)
    on_state()
    snap = dev.motion_snapshot()
    if snap is not None:
        on_motion(snap)


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/reset_heading", vol.Optional("device_id"): str}  # type: ignore[dict-item]
)
@callback
def ws_reset_heading(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    dev = _find(hass, msg.get("device_id"))
    if dev is None:
        connection.send_error(msg["id"], "not_found", "No such Triki token")
        return
    dev.reset_heading()
    connection.send_result(msg["id"])
