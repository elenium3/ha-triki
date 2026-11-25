"""The knob position: an absolute 0-100 % next to the relative knob events."""

from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    mock_restore_cache_with_extra_data,
)

from custom_components.triki.const import BUS_EVENT, DOMAIN

from .conftest import ADDRESS, NAME

POSITION = "number.triki_0000_knob_position"


async def _setup(hass: HomeAssistant, **options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=ADDRESS, title=NAME, data={CONF_ADDRESS: ADDRESS}, options=options
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_a_turn_moves_it_and_the_event_carries_it(hass: HomeAssistant, mock_bluetooth):
    entry = await _setup(hass, knob=True)
    dev = entry.runtime_data
    bus = async_capture_events(hass, BUS_EVENT)
    assert hass.states.get(POSITION).state == "50"  # the middle until told otherwise

    dev._emit("rotate_cw", {"steps": 3, "degrees": 90.0})  # a quarter turn up
    await hass.async_block_till_done()
    assert hass.states.get(POSITION).state == "75"
    assert bus[-1].data["position"] == 75

    dev._emit("rotate_ccw", {"steps": 1, "degrees": 30.0})
    await hass.async_block_till_done()
    assert bus[-1].data["position"] == 67
    assert hass.states.get(POSITION).state == "67"


async def test_it_stops_at_the_ends(hass: HomeAssistant, mock_bluetooth):
    entry = await _setup(hass, knob=True)
    dev = entry.runtime_data
    bus = async_capture_events(hass, BUS_EVENT)
    dev._emit("rotate_cw", {"steps": 24, "degrees": 720.0})
    assert bus[-1].data["position"] == 100
    dev._emit("rotate_ccw", {"steps": 48, "degrees": 1440.0})
    assert bus[-1].data["position"] == 0


async def test_set_from_home_assistant_then_turned_from_there(hass: HomeAssistant, mock_bluetooth):
    """An automation puts the lamp's brightness in; the next turn goes on from it."""
    entry = await _setup(hass, knob=True)
    dev = entry.runtime_data
    await hass.services.async_call(
        "number", "set_value", {"entity_id": POSITION, "value": 20}, blocking=True
    )
    assert hass.states.get(POSITION).state == "20"
    bus = async_capture_events(hass, BUS_EVENT)
    dev._emit("rotate_cw", {"steps": 1, "degrees": 36.0})
    assert bus[-1].data["position"] == 30


async def test_it_survives_a_restart(hass: HomeAssistant, mock_bluetooth):
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(POSITION, "83"),
                {
                    "native_max_value": 100,
                    "native_min_value": 0,
                    "native_step": 1,
                    "native_unit_of_measurement": "%",
                    "native_value": 83,
                },
            )
        ],
    )
    entry = await _setup(hass, knob=True)
    assert hass.states.get(POSITION).state == "83"
    assert entry.runtime_data.knob_position == 83.0


async def test_the_guided_check_does_not_move_it(hass: HomeAssistant, mock_bluetooth):
    entry = await _setup(hass, knob=True)
    dev = entry.runtime_data
    dev.start_check("card")
    dev._emit("rotate_cw", {"steps": 3, "degrees": 90.0})
    await hass.async_block_till_done()
    assert dev.knob_position == 50.0
    assert hass.states.get(POSITION).state == "50"


async def test_no_entity_without_the_knob(hass: HomeAssistant, mock_bluetooth):
    entry = await _setup(hass, knob=True)
    registry = er.async_get(hass)
    assert registry.async_get(POSITION) is not None

    # saving the options reloads the entry
    hass.config_entries.async_update_entry(entry, options={**entry.options, "knob": False})
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(POSITION) is None
    assert hass.states.get(POSITION) is None
