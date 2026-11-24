"""The blueprints under blueprints/automation/triki run in Home Assistant and do
what they say."""

from __future__ import annotations

import pathlib
import shutil

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

SRC = pathlib.Path(__file__).parent.parent / "blueprints" / "automation" / "triki"
EVENT = "event.triki_action"
LIGHT = "light.desk"


@pytest.fixture
def blueprints(hass: HomeAssistant, tmp_path):
    hass.config.config_dir = str(tmp_path)
    dest = tmp_path / "blueprints" / "automation" / "triki"
    dest.mkdir(parents=True)
    for f in SRC.glob("*.yaml"):
        shutil.copy(f, dest / f.name)


async def _setup(hass: HomeAssistant, path: str, inputs: dict) -> None:
    hass.states.async_set(EVENT, "2026-11-24T00:00:00.000+00:00", {"event_type": "wake"})
    assert await async_setup_component(
        hass,
        "automation",
        {"automation": {"use_blueprint": {"path": path, "input": {"triki": EVENT, **inputs}}}},
    )
    await hass.async_block_till_done()


async def _gesture(hass: HomeAssistant, n: int, kind: str, **attrs) -> None:
    hass.states.async_set(
        EVENT, f"2026-11-24T00:00:{n:02d}.000+00:00", {"event_type": kind, **attrs}
    )
    await hass.async_block_till_done()


async def test_light_remote(hass: HomeAssistant, blueprints) -> None:
    toggle = async_mock_service(hass, "light", "toggle")
    turn_on = async_mock_service(hass, "light", "turn_on")
    hass.states.async_set(LIGHT, "on", {"brightness": 128})  # 50 %
    await _setup(hass, "triki/triki_light.yaml", {"light": LIGHT})

    await _gesture(hass, 1, "single_press")
    assert len(toggle) == 1 and toggle[0].data["entity_id"] == [LIGHT]

    await _gesture(hass, 2, "rotate_cw", steps=2, degrees=60)
    assert turn_on[-1].data["brightness_pct"] == 66  # 50 + 2 x 8

    hass.states.async_set(LIGHT, "on", {"brightness": 3})  # ~1 %
    await _gesture(hass, 3, "rotate_ccw", steps=3, degrees=90)
    assert turn_on[-1].data["brightness_pct"] == 1  # not off

    await _gesture(hass, 4, "long_press_start")
    assert turn_on[-1].data["brightness_pct"] == 100

    n = len(turn_on)
    hass.states.async_set(LIGHT, "off")
    await _gesture(hass, 5, "rotate_cw", steps=1)
    assert len(turn_on) == n  # the knob does not switch a light on
    await _gesture(hass, 6, "shake")
    assert len(toggle) == 1 and len(turn_on) == n


async def test_an_action_per_gesture(hass: HomeAssistant, blueprints) -> None:
    calls = async_mock_service(hass, "test", "gesture")
    act = lambda name: [{"action": "test.gesture", "data": {"name": name, "steps": "{{ steps }}"}}]  # noqa: E731
    await _setup(
        hass,
        "triki/triki_actions.yaml",
        {"press": act("press"), "rotate_ccw": act("ccw"), "tilt_left": act("left")},
    )
    await _gesture(hass, 1, "single_press")
    await _gesture(hass, 2, "rotate_ccw", steps=3)
    await _gesture(hass, 3, "multi_press", press_count=2)  # left empty: nothing
    await _gesture(hass, 4, "tilt_left", repeat=False)
    assert [(c.data["name"], c.data["steps"]) for c in calls] == [
        ("press", 1),
        ("ccw", 3),
        ("left", 1),
    ]


async def test_presses_by_count_and_the_release(hass: HomeAssistant, blueprints) -> None:
    calls = async_mock_service(hass, "test", "gesture")
    act = lambda name: [{"action": "test.gesture", "data": {"name": name}}]  # noqa: E731
    await _setup(
        hass,
        "triki/triki_actions.yaml",
        {
            "double_press": act("double"),
            "triple_press": act("triple"),
            "long_press": act("held"),
            "long_press_end": act("released"),
        },
    )
    await _gesture(hass, 1, "multi_press", press_count=3)
    await _gesture(hass, 2, "multi_press", press_count=2)
    await _gesture(hass, 3, "long_press_start")
    await _gesture(hass, 4, "long_press_end")
    await _gesture(hass, 5, "single_press")  # left empty: nothing
    assert [c.data["name"] for c in calls] == ["triple", "double", "held", "released"]


async def test_a_restored_state_is_not_a_gesture(hass: HomeAssistant, blueprints) -> None:
    """A restart or a reload takes the entity through unavailable and back to
    the last event: that must not toggle the light. The first event of a new
    cap (from unknown) is a real one."""
    toggle = async_mock_service(hass, "light", "toggle")
    await _setup(hass, "triki/triki_light.yaml", {"light": LIGHT})
    await _gesture(hass, 1, "single_press")
    assert len(toggle) == 1
    hass.states.async_set(EVENT, "unavailable", {})
    await hass.async_block_till_done()
    await _gesture(hass, 1, "single_press")  # restored: the same press again
    assert len(toggle) == 1
    hass.states.async_set(EVENT, "unknown", {})
    await hass.async_block_till_done()
    await _gesture(hass, 2, "single_press")
    assert len(toggle) == 2


async def test_the_readme_example_ignores_a_restart(hass: HomeAssistant) -> None:
    """The README's automation, as written there: a press toggles, the state
    restored after a restart does not."""
    import yaml

    readme = (pathlib.Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    block = readme.split("```yaml\n", 1)[1].split("```", 1)[0]
    config = yaml.safe_load(block)
    toggle = async_mock_service(hass, "light", "toggle")
    hass.states.async_set(EVENT, "2026-11-24T00:00:00.000+00:00", {"event_type": "single_press"})
    assert await async_setup_component(hass, "automation", config)
    await hass.async_block_till_done()
    await _gesture(hass, 1, "single_press")
    assert len(toggle) == 1
    hass.states.async_set(EVENT, "unavailable", {})
    await hass.async_block_till_done()
    await _gesture(hass, 1, "single_press")  # restored
    assert len(toggle) == 1
    await _gesture(hass, 2, "single_press")
    assert len(toggle) == 2


async def test_odd_states_do_not_break_them(hass: HomeAssistant, blueprints, caplog) -> None:
    """The entity removed, and a light that is on but has no brightness: no
    template error, and the knob leaves such a light alone."""
    turn_on = async_mock_service(hass, "light", "turn_on")
    await _setup(hass, "triki/triki_light.yaml", {"light": LIGHT})
    hass.states.async_set(LIGHT, "on", {})
    await _gesture(hass, 1, "rotate_cw", steps=1)
    assert turn_on == []
    hass.states.async_remove(EVENT)
    await hass.async_block_till_done()
    assert "Error" not in caplog.text, caplog.text
