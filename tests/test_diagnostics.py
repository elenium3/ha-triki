from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.triki.protocol import DEFAULT_RATE

from .conftest import connect
from .helpers import frame


async def test_diagnostics(hass: HomeAssistant, setup, hass_client: ClientSessionGenerator) -> None:
    diag = await get_diagnostics_for_config_entry(hass, hass_client, setup)
    assert diag["entry"]["data"]["address"] == "**REDACTED**"
    assert diag["device"]["connected"] is False
    assert diag["link"]["connects"] == 0

    client, notify = await connect(hass, setup)
    notify(None, bytearray(frame() * 2))
    diag = await get_diagnostics_for_config_entry(hass, hass_client, setup)
    assert diag["device"]["connected"] is True
    assert diag["options"]["rate"] == DEFAULT_RATE
    assert diag["link"]["connects"] == 1
    assert diag["link"]["notifications"] == 1
    assert diag["link"]["frames"] == 2
    assert diag["link"]["last_source"] == "local"

    setup.runtime_data._on_disconnect(client)
    await hass.async_block_till_done()
    diag = await get_diagnostics_for_config_entry(hass, hass_client, setup)
    assert diag["link"]["drops"] == 1
    assert diag["link"]["last_session_s"] is not None
