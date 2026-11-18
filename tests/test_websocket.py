"""The live card's websocket API and the frontend files it is served from."""

from __future__ import annotations

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
