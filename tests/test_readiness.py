"""Readiness: connected, dozing off after an idle drop, asleep, not responding."""

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant

from custom_components.triki import device as device_mod

from .conftest import ESTABLISH, make_client, service_info

READINESS = "sensor.triki_0000_readiness"


async def connect(hass: HomeAssistant, entry) -> None:
    with patch(ESTABLISH, AsyncMock(return_value=make_client())):
        entry.runtime_data._on_advertisement(service_info(), None)
        await hass.async_block_till_done()


async def idle_drop(hass: HomeAssistant, entry) -> None:
    dev = entry.runtime_data
    dev._last_activity -= 10_000
    dev._idle_check(None)
    await hass.async_block_till_done()


async def test_states_through_an_idle_drop(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    assert hass.states.get(READINESS).state == "asleep"
    await connect(hass, setup)
    assert hass.states.get(READINESS).state == "connected"
    assert dev.doze_left_s is None

    await idle_drop(hass, setup)
    assert hass.states.get(READINESS).state == "dozing"
    assert 175 <= dev.doze_left_s <= 180

    # still advertising: dozing, and the adverts keep it so
    dev._last_attempt = dev._no_connect_until = 0
    dev._awake_seen -= device_mod._SLEEP_GAP_S - 1
    with patch(ESTABLISH, AsyncMock()) as est:
        dev._on_advertisement(service_info(), None)
        await hass.async_block_till_done()
    assert est.await_count == 0
    assert dev.readiness == "dozing"

    # the adverts stop: the timer the last one armed says it is asleep now
    dev._awake_seen -= device_mod._SLEEP_GAP_S
    dev._doze_started -= device_mod._DOZE_S
    dev._doze_check(None)
    await hass.async_block_till_done()
    assert hass.states.get(READINESS).state == "asleep"
    assert dev.doze_left_s is None


async def test_missed_adverts_early_in_the_doze_are_not_sleep(hass: HomeAssistant, setup) -> None:
    """A weak link misses the adverts for a while: the token cannot have slept a
    minute after the drop, so it is still dozing and no advert connects to it."""
    dev = setup.runtime_data
    await connect(hass, setup)
    await idle_drop(hass, setup)
    dev._doze_started -= 60
    dev._awake_seen -= 30  # nothing heard for 30 s
    dev._doze_check(None)
    assert dev.readiness == "dozing"
    dev._last_attempt = dev._no_connect_until = 0
    with patch(ESTABLISH, AsyncMock()) as est:
        dev._on_advertisement(service_info(), None)
        await hass.async_block_till_done()
    assert est.await_count == 0
    assert dev.readiness == "dozing"


async def test_an_open_check_wakes_a_dozing_token_unless_it_is_its_sleep_step(
    hass: HomeAssistant, setup
) -> None:
    """While a check is open a press reconnects a dozing token, so readiness says
    a press wakes it; in the check's own sleep step it waits for sleep."""
    dev = setup.runtime_data
    await connect(hass, setup)
    await idle_drop(hass, setup)
    assert dev.readiness == "dozing"
    assert dev.start_check("card")
    assert dev.readiness == "asleep"
    dev._check_sleeping = True  # the sleep step dropped the link
    assert dev.readiness == "dozing"
    dev.stop_check("card")


async def test_an_overdue_doze_counts_down_to_zero(hass: HomeAssistant, setup) -> None:
    """A press while dozing starts the 3 minutes over: unseen, so 0, not negative."""
    dev = setup.runtime_data
    await connect(hass, setup)
    await idle_drop(hass, setup)
    dev._doze_started -= device_mod._DOZE_S + 60
    assert dev.readiness == "dozing"
    assert dev.doze_left_s == 0


async def test_a_reload_while_dozing_does_not_connect(hass: HomeAssistant, setup) -> None:
    """Saving options right after an idle drop reloads the entry: the new instance
    must still wait for the token to sleep, or it links up for another session."""
    await connect(hass, setup)
    await idle_drop(hass, setup)
    assert await hass.config_entries.async_reload(setup.entry_id)
    await hass.async_block_till_done()
    dev = setup.runtime_data
    assert dev.readiness == "dozing"
    dev._last_attempt = dev._no_connect_until = 0
    with patch(ESTABLISH, AsyncMock(return_value=make_client())) as est:
        dev._on_advertisement(service_info(), None)
        await hass.async_block_till_done()
    assert est.await_count == 0
    assert not dev.connected


async def test_a_reload_while_connected_reconnects(hass: HomeAssistant, setup) -> None:
    """A reload mid-session is not an idle drop: the session goes on."""
    await connect(hass, setup)
    assert await hass.config_entries.async_reload(setup.entry_id)
    await hass.async_block_till_done()
    dev = setup.runtime_data
    assert dev.readiness == "asleep"
    await connect(hass, setup)
    assert dev.connected


async def test_not_responding(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    dev._set_unresponsive(True)
    await hass.async_block_till_done()
    assert hass.states.get(READINESS).state == "not_responding"
