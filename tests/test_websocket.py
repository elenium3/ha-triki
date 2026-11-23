"""The live card's websocket API and the frontend files it is served from."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components import triki
from custom_components.triki import device as device_mod

from .conftest import connect
from .helpers import frame


async def test_frontend_files_are_shipped() -> None:
    for name in triki.FRONTEND_FILES:
        assert (triki.FRONTEND_DIR / name).is_file()


async def test_devices_lists_the_token(hass: HomeAssistant, setup, hass_ws_client) -> None:
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "triki/devices"})
    msg = await ws.receive_json()
    assert msg["success"]
    assert msg["result"] == [{"device_id": setup.runtime_data.device_id, "name": "Triki 0000"}]


async def test_subscribe_unknown_device(hass: HomeAssistant, setup, hass_ws_client) -> None:
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "triki/subscribe", "device_id": "nope"})
    msg = await ws.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "not_found"


async def test_subscribe_streams_status_and_motion(
    hass: HomeAssistant, setup, hass_ws_client, monkeypatch
) -> None:
    monkeypatch.setattr(device_mod, "LIVE_INTERVAL_S", 0.0)
    dev = setup.runtime_data
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "triki/subscribe"})  # the only token: no id needed
    assert (await ws.receive_json())["success"]
    first = await ws.receive_json()
    assert first["event"]["type"] == "status"
    assert first["event"]["connected"] is False

    _client, notify = await connect(hass, setup)
    for i in range(30):
        notify(None, bytearray(frame(gz=0.1 * i, ay=1.0, az=0.0)))  # lying on its side
    await hass.async_block_till_done()

    motion = None
    while True:
        try:
            msg = await ws.receive_json(timeout=0.5)
        except TimeoutError:
            break
        if msg["event"]["type"] == "motion":
            motion = msg["event"]
    assert motion is not None
    assert len(motion["quaternion"]) == 4
    roll, pitch, _yaw = motion["euler"]
    assert abs(roll - 90) < 3
    assert abs(pitch) < 3
    assert motion["accel"] == [0.0, 1.0, 0.0]
    assert motion["button"] is False
    assert dev._motion_listeners  # still subscribed

    await ws.send_json({"id": 2, "type": "unsubscribe_events", "subscription": 1})
    while (msg := await ws.receive_json())["id"] != 2:
        pass
    assert msg["success"]
    assert not dev._motion_listeners


async def test_no_motion_without_subscribers(hass: HomeAssistant, setup) -> None:
    """Nobody watching: the snapshot is not even built."""
    dev = setup.runtime_data
    _client, notify = await connect(hass, setup)
    notify(None, bytearray(frame()))
    assert not dev._motion_listeners
    assert dev.motion_snapshot() is not None


async def test_reset_heading(hass: HomeAssistant, setup, hass_ws_client) -> None:
    dev = setup.runtime_data
    _client, notify = await connect(hass, setup)
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "triki/reset_heading", "device_id": dev.device_id})
    assert (await ws.receive_json())["success"]


async def test_pose_is_forgotten_on_disconnect(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    client, notify = await connect(hass, setup)
    notify(None, bytearray(frame()))
    assert dev.motion_snapshot() is not None
    dev._on_disconnect(client)
    await hass.async_block_till_done()
    assert dev.motion_snapshot() is None


async def test_status_reports_the_wait_for_sleep(hass: HomeAssistant, setup) -> None:
    """After an idle drop the card can tell the owner why the token does not reconnect."""
    from custom_components.triki.websocket import status

    dev = setup.runtime_data
    assert status(dev)["waiting_for_sleep"] is False
    dev._await_sleep = True
    assert status(dev)["waiting_for_sleep"] is True


async def test_calibrate_flat_is_stored(hass: HomeAssistant, setup, hass_ws_client) -> None:
    dev = setup.runtime_data
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "triki/calibrate", "step": "flat"})
    msg = await ws.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "asleep"

    _client, notify = await connect(hass, setup)
    for i in range(60):
        notify(None, bytearray(frame(ax=-0.087 + i * 1e-5, az=0.996)))  # 5 degrees off
    await ws.send_json({"id": 2, "type": "triki/calibrate", "step": "flat"})
    msg = await ws.receive_json()
    assert msg["success"], msg
    assert dev.calibrated
    stored = setup.data["calibration"]
    assert abs(stored["mount"][2]) > 0.03  # a rotation about y

    await ws.send_json({"id": 3, "type": "triki/calibrate", "step": "clear"})
    assert (await ws.receive_json())["success"]
    assert not dev.calibrated


async def test_calibrate_logo_angle_is_stored(hass: HomeAssistant, setup, hass_ws_client) -> None:
    """The logo angle needs no motion: the token may be asleep."""
    dev = setup.runtime_data
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "triki/calibrate", "step": "logo", "angle": 390})
    msg = await ws.receive_json()
    assert msg["success"], msg
    assert dev.logo_angle == 30.0
    assert setup.data["calibration"]["logo"] == 30.0

    from custom_components.triki.websocket import status

    assert status(dev)["logo_angle"] == 30.0
    await ws.send_json({"id": 2, "type": "triki/calibrate", "step": "logo"})
    msg = await ws.receive_json()
    assert msg["error"]["code"] == "no_angle"
    await ws.send_json({"id": 3, "type": "triki/calibrate", "step": "clear"})
    assert (await ws.receive_json())["success"]
    assert dev.logo_angle is None


async def test_a_delayed_burst_keeps_the_turn(hass: HomeAssistant, setup, monkeypatch) -> None:
    """A proxy holds notifications back for 2 s, then delivers them at once.

    The pose runs on the sample clock, so the turn made meanwhile is not lost.
    """
    dev = setup.runtime_data
    clock = [1000.0]
    monkeypatch.setattr(device_mod.time, "monotonic", lambda: clock[0])
    _client, notify = await connect(hass, setup)
    rate = dev.stream_rate

    def send(n: int, gz: float, step: float) -> None:
        for i in range(n):
            clock[0] += step
            # real frames carry sensor noise; identical ones are dropped as duplicates
            notify(None, bytearray(frame(gz=gz, ax=0.001 * (i % 7))))

    send(3 * rate, 0.0, 1 / rate)  # settle, still
    yaw0 = dev.motion_snapshot()["euler"][2]
    send(rate, 50.0, 1 / rate)  # 1 s of turning at 50 deg/s, on time
    clock[0] += 2.0  # then the proxy goes quiet for 2 s ...
    send(2 * rate, 50.0, 0.001)  # ... and delivers the next 2 s of turning at once
    send(rate, 0.0, 1 / rate)
    turned = dev.motion_snapshot()["euler"][2] - yaw0
    turned -= 360 * round(turned / 360)
    assert abs(turned) == pytest.approx(150, abs=8)  # on arrival times it was about 55


async def test_apply_changes_only_what_the_check_may(
    hass: HomeAssistant, setup, hass_ws_client
) -> None:
    """The check's Apply: the given settings land in the options and the entry reloads."""
    ws = await hass_ws_client(hass)
    dev_id = setup.runtime_data.device_id
    await ws.send_json_auto_id(
        {
            "type": "triki/apply",
            "device_id": dev_id,
            "options": {"invert_rotation": True, "sample_rate": 26, "multi_press_window": 0.55},
        }
    )
    msg = await ws.receive_json()
    assert msg["success"], msg
    await hass.async_block_till_done()
    assert setup.options["invert_rotation"] is True
    assert setup.options["sample_rate"] == 26
    assert setup.options["multi_press_window"] == 0.55
    assert setup.runtime_data.options.invert_rotation is True  # reloaded with them


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"sleep_timeout": 0},  # not the check's to change
        {"sample_rate": 30},
        {"multi_press_window": 5},
    ],
)
async def test_apply_refuses_other_settings(
    hass: HomeAssistant, setup, hass_ws_client, options
) -> None:
    ws = await hass_ws_client(hass)
    before = dict(setup.options)
    await ws.send_json_auto_id(
        {"type": "triki/apply", "device_id": setup.runtime_data.device_id, "options": options}
    )
    msg = await ws.receive_json()
    assert not msg["success"]
    assert dict(setup.options) == before


async def test_apply_needs_an_admin(
    hass: HomeAssistant, setup, hass_ws_client, hass_admin_user
) -> None:
    hass_admin_user.groups = []
    ws = await hass_ws_client(hass)
    await ws.send_json_auto_id(
        {
            "type": "triki/apply",
            "device_id": setup.runtime_data.device_id,
            "options": {"shake": False},
        }
    )
    msg = await ws.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "unauthorized"
