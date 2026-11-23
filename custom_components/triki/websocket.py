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

from .const import (
    CONF_INVERT_ROTATION,
    CONF_MULTI_PRESS_WINDOW,
    CONF_RATE,
    CONF_SHAKE,
    CONF_TILT,
    DOMAIN,
)
from .orientation import CalibrationError
from .protocol import SUPPORTED_RATES

# mypy sees voluptuous markers as a different type than the decorator's hint in
# this environment; the schemas are the ones Home Assistant core uses.

if TYPE_CHECKING:
    from .device import TrikiDevice


@callback
def async_register(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, ws_devices)
    websocket_api.async_register_command(hass, ws_subscribe)
    websocket_api.async_register_command(hass, ws_reset_heading)
    websocket_api.async_register_command(hass, ws_calibrate)
    websocket_api.async_register_command(hass, ws_check)
    websocket_api.async_register_command(hass, ws_apply)


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
        "readiness": dev.readiness,
        "doze_left_s": dev.doze_left_s,
        "calibrated": dev.calibrated,
        "logo_angle": dev.logo_angle,
        "battery": dev.battery,
        "rssi": dev.rssi,
        "rate": dev.stream_rate if dev.connected else None,
        "measured_rate": dev.measured_rate,
        "button": dev.button,
        "led": dev.led_on,
        "firmware": dev.firmware,
        "face": dev.face,
        "via": dev.link_source_name,
        "checking": dev.checking,
        "options": {
            "knob": dev.options.knob,
            "knob_step": dev.options.knob_step,
            "invert_rotation": dev.options.invert_rotation,
            "motion_gestures": dev.options.motion_gestures,
            "multi_press": dev.options.multi_press,
            "shake": dev.options.shake,
            "tilt": dev.options.tilt,
            "multi_press_window": dev.options.multi_press_window,
        },
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

    @callback
    def on_gone() -> None:
        # the entry reloads (options changed): this device object is done; the
        # card subscribes again and gets the new one
        send({"type": "reload"})

    unsubs = [
        dev.async_add_listener(on_state),
        dev.async_add_motion_listener(on_motion),
        dev.async_add_event_listener(on_event, during_check=True),
        dev.async_add_gone_listener(on_gone),
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


_CALIBRATE_SCHEMA: dict[Any, Any] = {
    vol.Required("type"): f"{DOMAIN}/calibrate",
    vol.Optional("device_id"): str,
    vol.Required("step"): vol.In(["flat", "logo", "clear"]),
    vol.Optional("angle"): vol.Coerce(float),
}


@websocket_api.require_admin
@websocket_api.websocket_command(_CALIBRATE_SCHEMA)
@callback
def ws_calibrate(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """flat: lying still on the table (levels it, zeroes the heading); logo: the
    metal logo's angle in degrees (per token, drawn by the card); clear: forget both."""
    dev = _find(hass, msg.get("device_id"))
    if dev is None:
        connection.send_error(msg["id"], "not_found", "No such Triki token")
        return
    try:
        dev.calibrate(msg["step"], msg.get("angle"))
    except CalibrationError as err:
        connection.send_error(msg["id"], str(err), f"Calibration step not possible: {err}")
        return
    connection.send_result(msg["id"])


_CHECK_SCHEMA: dict[Any, Any] = {
    vol.Required("type"): f"{DOMAIN}/check",
    vol.Optional("device_id"): str,
    vol.Required("action"): vol.In(["start", "stop", "sleep"]),
    vol.Required("session"): vol.All(str, vol.Length(min=8, max=64)),
}


@websocket_api.require_admin
@websocket_api.websocket_command(_CHECK_SCHEMA)
@callback
def ws_check(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """The card's guided check. ``start`` begins or renews it (the card renews
    every few seconds; it lapses on its own otherwise), ``stop`` ends it, ``sleep``
    drops the link as after idling for the sleep step. While it runs, gestures
    reach the card only, not automations."""
    dev = _find(hass, msg.get("device_id"))
    if dev is None:
        connection.send_error(msg["id"], "not_found", "No such Triki token")
        return
    if msg["action"] == "stop":
        dev.stop_check(msg["session"])
    elif msg["action"] == "sleep":
        if not dev.check_sleep(msg["session"]):
            connection.send_error(msg["id"], "not_ready", "Not connected, or not this check")
            return
    elif not dev.start_check(msg["session"]):
        connection.send_error(msg["id"], "busy", "Another check of this token is running")
        return
    connection.send_result(msg["id"])


# What the guided check may change, with the options form's own limits. Anything
# else stays in the options form, where the owner sees every setting at once.
_APPLY_OPTIONS = vol.Schema(
    {
        vol.Optional(CONF_INVERT_ROTATION): bool,
        vol.Optional(CONF_RATE): vol.All(vol.Coerce(int), vol.In(SUPPORTED_RATES)),
        vol.Optional(CONF_MULTI_PRESS_WINDOW): vol.All(
            vol.Coerce(float), vol.Range(min=0.2, max=1.5)
        ),
        vol.Optional(CONF_SHAKE): bool,
        vol.Optional(CONF_TILT): bool,
    }
)
_APPLY_SCHEMA: dict[Any, Any] = {
    vol.Required("type"): f"{DOMAIN}/apply",
    vol.Optional("device_id"): str,
    vol.Required("options"): vol.All(_APPLY_OPTIONS, vol.Length(min=1)),
}


@websocket_api.require_admin
@websocket_api.websocket_command(_APPLY_SCHEMA)
@callback
def ws_apply(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Settings the guided check suggests, applied when the owner presses Apply.

    The entry reloads with them, as after the options form: the link drops and
    the token reconnects on its next wake-up.
    """
    dev = _find(hass, msg.get("device_id"))
    if dev is None:
        connection.send_error(msg["id"], "not_found", "No such Triki token")
        return
    entry = dev.entry
    hass.config_entries.async_update_entry(entry, options={**entry.options, **msg["options"]})
    hass.config_entries.async_schedule_reload(entry.entry_id)
    connection.send_result(msg["id"], {"applied": msg["options"]})
