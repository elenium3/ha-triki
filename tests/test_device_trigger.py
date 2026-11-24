"""Device triggers: the automation editor's "Triki → Press"."""

from __future__ import annotations

from homeassistant.components import automation
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    async_get_device_automations,
    async_mock_service,
)

from custom_components.triki.const import BUS_EVENT, DOMAIN


def _types(triggers) -> set[str]:
    # the device also has the entity triggers of its sensors and switch
    return {t["type"] for t in triggers if t["domain"] == DOMAIN}


async def test_the_list_follows_the_options(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    triggers = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, dev.device_id)
    assert _types(triggers) == {"wake", "press", "long_press"}
    assert all(t["device_id"] == dev.device_id for t in triggers)

    hass.config_entries.async_update_entry(
        setup, options={**setup.options, "knob": True, "tilt": True}
    )
    await hass.async_block_till_done()
    triggers = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, dev.device_id)
    assert _types(triggers) == {
        "wake",
        "press",
        "long_press",
        "rotate_cw",
        "rotate_ccw",
        "tilt_left",
        "tilt_right",
    }


async def test_a_trigger_fires_on_its_gesture_only(hass: HomeAssistant, setup) -> None:
    calls = async_mock_service(hass, "test", "pressed")
    dev = setup.runtime_data
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: {
                "triggers": {
                    "platform": "device",
                    "domain": DOMAIN,
                    "device_id": dev.device_id,
                    "type": "press",
                },
                "actions": {
                    "action": "test.pressed",
                    "data": {"count": "{{ trigger.event.data.count }}"},
                },
            }
        },
    )
    hass.bus.async_fire(BUS_EVENT, {"device_id": dev.device_id, "type": "long_press"})
    hass.bus.async_fire(BUS_EVENT, {"device_id": "another cap", "type": "press", "count": 1})
    hass.bus.async_fire(BUS_EVENT, {"device_id": dev.device_id, "type": "press", "count": 1})
    await hass.async_block_till_done()
    assert [c.data["count"] for c in calls] == [1]


async def test_a_gesture_from_the_device_reaches_the_trigger(hass: HomeAssistant, setup) -> None:
    """End to end: the device's own event, as a press makes it."""
    calls = async_mock_service(hass, "test", "pressed")
    dev = setup.runtime_data
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: {
                "triggers": {
                    "platform": "device",
                    "domain": DOMAIN,
                    "device_id": dev.device_id,
                    "type": "press",
                },
                "actions": {"action": "test.pressed"},
            }
        },
    )
    dev._emit("press", {"count": 1})
    await hass.async_block_till_done()
    assert len(calls) == 1
