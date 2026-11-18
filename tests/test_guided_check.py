"""The card's guided check: gestures stay out of automations while it runs."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    async_capture_events,
    async_fire_time_changed,
)

from custom_components.triki import device as device_mod
from custom_components.triki.const import BUS_EVENT, IDLE_RATE

from .conftest import EVENT, connect
from .helpers import frame

SESSION = "card-session-1"


def _press(notify) -> None:
    stream = frame() * 80 + frame(button=True) * 10 + frame() * 60
    for i in range(0, len(stream), 20):
        notify(None, bytearray(stream[i : i + 20]))


async def test_check_keeps_gestures_out_of_automations(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    bus = async_capture_events(hass, BUS_EVENT)
    card: list[str] = []
    dev.async_add_event_listener(lambda kind, _data: card.append(kind), during_check=True)
    _client, notify = await connect(hass, setup)
    bus.clear()
    card.clear()
    before = hass.states.get(EVENT).attributes.get("event_type")

    assert dev.start_check(SESSION)
    _press(notify)
    await hass.async_block_till_done()
    assert card == ["press"]  # the card sees it
    assert bus == []  # automations do not
    assert hass.states.get(EVENT).attributes.get("event_type") == before

    dev.stop_check(SESSION)
    _press(notify)
    await hass.async_block_till_done()
    assert [e.data["type"] for e in bus] == ["press"]
    assert hass.states.get(EVENT).attributes["event_type"] == "press"


async def test_one_check_per_token(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    assert dev.start_check(SESSION)
    assert not dev.start_check("other-card-session")  # a second card is refused
    assert dev.start_check(SESSION)  # the owner renews
    dev.stop_check("other-card-session")  # not the owner: no effect
    assert dev.checking
    dev.stop_check(SESSION)
    assert not dev.checking
    assert dev.start_check("other-card-session")


async def test_check_lapses_without_renewal(hass: HomeAssistant, setup) -> None:
    """A closed tab must not leave the token silent for automations."""
    dev = setup.runtime_data
    states: list[bool] = []
    dev.async_add_listener(lambda: states.append(dev.checking))
    t0 = device_mod.time.monotonic()
    assert dev.start_check(SESSION)
    with patch.object(device_mod.time, "monotonic", return_value=t0 + device_mod._CHECK_TTL_S + 1):
        async_fire_time_changed(
            hass, dt_util.utcnow() + timedelta(seconds=device_mod._CHECK_TTL_S + 1)
        )
        await hass.async_block_till_done()
        assert not dev.checking
    assert states[0] is True and states[-1] is False
    assert dev.start_check("other-card-session")


async def test_check_holds_the_full_rate(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    await connect(hass, setup)
    dev._last_activity = device_mod.time.monotonic() - 10_000  # long idle
    assert dev.start_check(SESSION)
    dev._last_activity = device_mod.time.monotonic() - 10_000
    with patch.object(dev, "_async_set_rate") as set_rate:
        dev._idle_check(None)
        await hass.async_block_till_done()
    assert dev.connected  # not dropped as idle
    assert not any(c.args and c.args[0] == IDLE_RATE for c in set_rate.call_args_list)


async def test_check_command(hass: HomeAssistant, setup, hass_ws_client) -> None:
    dev = setup.runtime_data
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "triki/check", "action": "start", "session": SESSION})
    assert (await ws.receive_json())["success"]
    assert dev.check_owner == SESSION
    await ws.send_json({"id": 2, "type": "triki/check", "action": "start", "session": "x" * 12})
    msg = await ws.receive_json()
    assert not msg["success"] and msg["error"]["code"] == "busy"
    await ws.send_json({"id": 3, "type": "triki/check", "action": "stop", "session": SESSION})
    assert (await ws.receive_json())["success"]
    assert not dev.checking


async def test_check_and_calibration_need_an_admin(
    hass: HomeAssistant, setup, hass_ws_client, hass_read_only_access_token
) -> None:
    ws = await hass_ws_client(hass, hass_read_only_access_token)
    await ws.send_json({"id": 1, "type": "triki/check", "action": "start", "session": SESSION})
    msg = await ws.receive_json()
    assert not msg["success"] and msg["error"]["code"] == "unauthorized"
    await ws.send_json({"id": 2, "type": "triki/calibrate", "step": "clear"})
    msg = await ws.receive_json()
    assert not msg["success"] and msg["error"]["code"] == "unauthorized"
    assert not setup.runtime_data.checking


async def test_status_tells_the_card_what_to_expect(
    hass: HomeAssistant, setup, hass_ws_client
) -> None:
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "triki/subscribe"})
    assert (await ws.receive_json())["success"]
    status = (await ws.receive_json())["event"]
    assert status["checking"] is False
    assert status["via"] is None  # not linked
    assert status["options"] == {  # the defaults: the knob is opt-in
        "knob": False,
        "knob_step": 30,
        "invert_rotation": False,
        "motion_gestures": False,
        "multi_press": False,
        "shake": False,
    }
    assert "face" in status
