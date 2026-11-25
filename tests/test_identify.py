"""Identify: blink the LED so a person can tell which cap this is."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from bleak.exc import BleakError
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.triki import device as device_mod
from custom_components.triki.protocol import CTRL_UUID

from .conftest import connect

BUTTON = "button.triki_0000_identify"


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(device_mod, "_IDENTIFY_ON_S", 0)
    monkeypatch.setattr(device_mod, "_IDENTIFY_OFF_S", 0)


def _led_writes(client) -> list[bytes]:
    return [c.args[1] for c in client.write_gatt_char.await_args_list if c.args[0] == CTRL_UUID]


async def test_identify_blinks_three_times_and_ends_off(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    client, _ = await connect(hass, setup)
    await hass.services.async_call("button", "press", {"entity_id": BUTTON}, blocking=True)
    assert _led_writes(client) == [b"\x01", b"\x00"] * 3
    assert dev.led_on is False  # known now: the blink ended with the LED off


async def test_identify_leaves_a_lit_led_lit(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    client, _ = await connect(hass, setup)
    await dev.async_set_led(True)
    client.write_gatt_char.reset_mock()
    await dev.async_identify()
    assert _led_writes(client) == [b"\x00", b"\x01"] * 3
    assert dev.led_on is True


async def test_identify_does_not_flicker_the_led_switch(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    await connect(hass, setup)
    await dev.async_set_led(True)
    seen: list[bool | None] = []
    dev.async_add_listener(lambda: seen.append(dev.led_on))
    await dev.async_identify()
    assert set(seen) <= {True}


async def test_identify_on_a_sleeping_cap_says_so(hass: HomeAssistant, setup) -> None:
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call("button", "press", {"entity_id": BUTTON}, blocking=True)
    assert err.value.translation_key == "asleep"


async def test_identify_reports_a_failed_write(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    client, _ = await connect(hass, setup)
    client.write_gatt_char = AsyncMock(side_effect=BleakError("gone"))
    with pytest.raises(HomeAssistantError) as err:
        await dev.async_identify()
    assert err.value.translation_key == "led_write_failed"


async def test_a_second_press_during_a_blink_is_ignored(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    client, _ = await connect(hass, setup)
    async with dev._identify_lock:  # a blink is running
        await dev.async_identify()
    assert _led_writes(client) == []


async def test_the_button_is_a_config_identify_button(hass: HomeAssistant, setup) -> None:
    entry = er.async_get(hass).async_get(BUTTON)
    assert entry is not None
    assert entry.original_device_class == "identify"
    assert entry.entity_category == "config"
    assert hass.states.get(BUTTON).state != "unavailable"  # there while the cap sleeps
