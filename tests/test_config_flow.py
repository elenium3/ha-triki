from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.triki.const import CONF_IDLE_TIMEOUT, CONF_RATE, DOMAIN
from custom_components.triki.protocol import DEFAULT_RATE

from .conftest import ADDRESS, NAME, service_info

SETUP = "custom_components.triki.async_setup_entry"
SCANNERS = "custom_components.triki.config_flow.async_scanner_count"


@pytest.fixture(autouse=True)
def a_receiver_that_can_connect():
    """The test environment has no Bluetooth adapter; most flows assume one."""
    with patch(SCANNERS, return_value=1):
        yield


async def test_bluetooth_discovery(hass: HomeAssistant, mock_bluetooth) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=service_info(),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "gestures"
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"gestures": ["knob", "tilt"]}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {CONF_ADDRESS: ADDRESS}
    # the gestures picked are on, the others off; nothing else is set
    assert result["options"] == {
        "knob": True,
        "multi_press": False,
        "tilt": True,
        "shake": False,
        "motion_gestures": False,
    }

    # second discovery of the same token aborts
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=service_info(),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_no_devices(hass: HomeAssistant, mock_bluetooth) -> None:
    with patch(
        "custom_components.triki.config_flow.async_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_no_receiver_that_can_connect(hass: HomeAssistant, mock_bluetooth) -> None:
    """Pressing the cap again would not help: say what is missing."""
    with (
        patch(SCANNERS, return_value=0),
        patch(
            "custom_components.triki.config_flow.async_discovered_service_info",
            return_value=[],
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_connectable_receiver"


async def test_user_heard_only_by_a_listening_receiver(hass: HomeAssistant, mock_bluetooth) -> None:
    """A passive proxy or a Shelly hears the cap but cannot link to it."""

    def heard(_hass, connectable=True):
        return [] if connectable else [service_info()]

    with (
        patch("custom_components.triki.config_flow.async_discovered_service_info", heard),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "heard_not_connectable"


async def test_user_pick(hass: HomeAssistant, mock_bluetooth) -> None:
    with patch(
        "custom_components.triki.config_flow.async_discovered_service_info",
        return_value=[service_info(), service_info("Some Lamp", "11:22:33:44:55:66")],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ADDRESS: ADDRESS}
    )
    assert result["step_id"] == "gestures"
    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert not any(result["options"].values())  # nothing picked: all off


async def test_options(hass: HomeAssistant, mock_bluetooth) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    # the gestures come first, the rest folds away
    keys = [str(k) for k in result["data_schema"].schema]
    assert keys == ["knob", "multi_press", "tilt", "shake", "motion_gestures", "advanced"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "knob": True,
            "advanced": {
                CONF_RATE: "52",
                CONF_IDLE_TIMEOUT: 60,
                "knob_step": 45,
                "invert_rotation": True,
            },
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # stored flat: the section is only the form's layout
    assert entry.options[CONF_RATE] == 52
    assert entry.options["knob"] is True
    assert entry.options["knob_step"] == 45
    assert "advanced" not in entry.options
    # the flow schedules a reload (here: a first setup); let it finish before
    # teardown, or a slow runner finds the setup still in flight
    await hass.async_block_till_done()


async def test_bluetooth_discovery_rejects_other_devices(
    hass: HomeAssistant, mock_bluetooth
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=service_info("Some Lamp", "11:22:33:44:55:66"),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_bluetooth_discovery_rejects_dfu_bootloader(
    hass: HomeAssistant, mock_bluetooth
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=service_info("TrikiDfu", "11:22:33:44:55:67"),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_user_pick_already_configured(hass: HomeAssistant, mock_bluetooth) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}).add_to_hass(
        hass
    )
    with patch(
        "custom_components.triki.config_flow.async_discovered_service_info",
        return_value=[service_info()],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
    # the only awake token is already set up, so there is nothing to pick
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_options_change_reloads_entry(hass: HomeAssistant, mock_bluetooth) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=ADDRESS, title=NAME, data={CONF_ADDRESS: ADDRESS}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.options.rate == DEFAULT_RATE
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "advanced": {
                CONF_RATE: "26",
                CONF_IDLE_TIMEOUT: 60,
                "knob_step": 45,
                "invert_rotation": True,
            }
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.options.rate == 26  # new TrikiDevice from the reload
