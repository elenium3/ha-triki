"""A link held forever drains the cell: the battery saver and the repair issues."""

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.triki.const import (
    CONF_SLEEP_TIMEOUT,
    DEFAULT_SLEEP_TIMEOUT,
    DOMAIN,
    ISSUE_BATTERY_LOW,
    ISSUE_NOT_RESPONDING,
    ISSUE_SLEEP_NEVER,
)

from .conftest import ADDRESS, ESTABLISH, NAME, connect, make_client, service_info, settle
from .test_device_errors import answer_stop_with_battery


async def _setup(hass: HomeAssistant, **options) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ADDRESS,
        title=NAME,
        data={"address": ADDRESS},
        options=options,
        version=2,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _measure(hass: HomeAssistant, dev, client, level: int) -> None:
    """One idle battery pause that reports ``level`` at rest."""
    answer_stop_with_battery(hass, client, level)
    dev._battery_refreshed = float("-inf")
    dev._last_activity -= 60  # idle long enough for a refresh, short of any sleep timeout
    dev._battery_check(None)
    await settle(hass, dev)


async def test_never_sleep_raises_a_fixable_issue(hass: HomeAssistant, mock_bluetooth) -> None:
    entry = await _setup(hass, **{CONF_SLEEP_TIMEOUT: 0})
    issue_id = f"{ISSUE_SLEEP_NEVER}_{entry.entry_id}"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issue_id)
    assert issue is not None and issue.is_fixable

    from custom_components.triki.repairs import async_create_fix_flow

    flow = await async_create_fix_flow(hass, issue_id, issue.data)
    flow.hass = hass
    result = await flow.async_step_init()
    assert result["step_id"] == "confirm"
    result = await flow.async_step_confirm({})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options[CONF_SLEEP_TIMEOUT] == DEFAULT_SLEEP_TIMEOUT
    # the reload re-reads the options and clears the issue
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None
    assert entry.runtime_data.options.sleep_timeout == DEFAULT_SLEEP_TIMEOUT


async def test_default_sleep_has_no_issue(hass: HomeAssistant, setup) -> None:
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, f"{ISSUE_SLEEP_NEVER}_{setup.entry_id}") is None
    )


async def test_low_battery_lets_a_never_sleeping_token_sleep(
    hass: HomeAssistant, mock_bluetooth
) -> None:
    entry = await _setup(hass, **{CONF_SLEEP_TIMEOUT: 0, "idle_timeout": 0})
    dev = entry.runtime_data
    client, _ = await connect(hass, entry)
    assert dev.sleep_timeout == 0 and dev._unsub_idle is None

    await _measure(hass, dev, client, 31)
    assert dev.battery_rest == 31 and not dev.battery_saver
    client.disconnect.assert_not_awaited()

    await _measure(hass, dev, client, 25)
    assert dev.battery_saver and dev.sleep_timeout == DEFAULT_SLEEP_TIMEOUT
    assert dev._unsub_idle is not None  # idle checks run again although both options are 0

    dev._last_activity -= DEFAULT_SLEEP_TIMEOUT
    dev._idle_check(None)
    await hass.async_block_till_done()
    client.disconnect.assert_awaited()
    assert dev.connected is False


async def test_loaded_reads_do_not_trigger_the_saver(hass: HomeAssistant, mock_bluetooth) -> None:
    """The connect-time read (17-27 % under load) is not a level at rest."""
    entry = await _setup(hass, **{CONF_SLEEP_TIMEOUT: 0})
    dev = entry.runtime_data
    dev.restore_battery(18)
    await connect(hass, entry)
    assert dev.battery == 18 and dev.battery_rest is None
    assert not dev.battery_saver


async def test_low_battery_issue_comes_and_goes(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    issue_id = f"{ISSUE_BATTERY_LOW}_{setup.entry_id}"
    registry = ir.async_get(hass)
    client, _ = await connect(hass, setup)

    await _measure(hass, dev, client, 19)
    issue = registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None and not issue.is_fixable
    assert issue.translation_placeholders == {"name": NAME, "level": "19"}

    await _measure(hass, dev, client, 25)  # inside the margin: still a weak cell
    assert registry.async_get_issue(DOMAIN, issue_id) is not None

    await _measure(hass, dev, client, 85)  # a fresh cell
    assert registry.async_get_issue(DOMAIN, issue_id) is None


async def test_removing_the_entry_clears_its_issues(hass: HomeAssistant, mock_bluetooth) -> None:
    entry = await _setup(hass, **{CONF_SLEEP_TIMEOUT: 0})
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert not [i for i in ir.async_get(hass).issues if i[0] == DOMAIN]


async def test_low_battery_issue_threshold(hass: HomeAssistant, setup) -> None:
    """Tokens locked up at 18-21 % at rest: the notice comes at 30 %, goes at 40 %."""
    dev = setup.runtime_data
    issue_id = f"{ISSUE_BATTERY_LOW}_{setup.entry_id}"
    registry = ir.async_get(hass)
    client, _ = await connect(hass, setup)

    await _measure(hass, dev, client, 31)
    assert registry.async_get_issue(DOMAIN, issue_id) is None
    await _measure(hass, dev, client, 30)
    assert registry.async_get_issue(DOMAIN, issue_id) is not None
    await _measure(hass, dev, client, 39)
    assert registry.async_get_issue(DOMAIN, issue_id) is not None
    await _measure(hass, dev, client, 40)
    assert registry.async_get_issue(DOMAIN, issue_id) is None


async def test_silent_token_after_a_drop_raises_an_issue(hass: HomeAssistant, setup) -> None:
    """A link that drops on its own and a token that never advertises again."""
    dev = setup.runtime_data
    issue_id = f"{ISSUE_NOT_RESPONDING}_{setup.entry_id}"
    registry = ir.async_get(hass)
    await connect(hass, setup)

    dev._handle_disconnected()
    await hass.async_block_till_done()
    assert dev._unsub_silence is not None and not dev.unresponsive

    dev._check_silent_after_drop(None)
    issue = registry.async_get_issue(DOMAIN, issue_id)
    assert dev.unresponsive and dev._unsub_silence is None
    assert issue is not None and not issue.is_fixable
    assert issue.translation_placeholders == {"name": NAME, "level": f"{dev.battery} %"}

    # the cell was pulled and put back: the token advertises again
    dev._last_attempt = 0
    with patch(ESTABLISH, AsyncMock(return_value=make_client())):
        dev._on_advertisement(service_info(), None)
        await hass.async_block_till_done()
    assert not dev.unresponsive
    assert registry.async_get_issue(DOMAIN, issue_id) is None


async def test_token_heard_after_a_drop_is_not_flagged(hass: HomeAssistant, setup) -> None:
    """A healthy token advertises for minutes after a drop: no notice."""
    dev = setup.runtime_data
    await connect(hass, setup)
    dev._handle_disconnected()
    await hass.async_block_till_done()

    with patch(
        "custom_components.triki.device.bluetooth.async_last_service_info",
        return_value=service_info(),
    ):
        dev._check_silent_after_drop(None)
    assert not dev.unresponsive
    assert not [i for i in ir.async_get(hass).issues if i[1].startswith(ISSUE_NOT_RESPONDING)]


async def test_idle_disconnect_does_not_arm_the_silence_check(hass: HomeAssistant, setup) -> None:
    """Dropping the link ourselves is not a token that went silent."""
    dev = setup.runtime_data
    await connect(hass, setup)
    dev._last_activity -= DEFAULT_SLEEP_TIMEOUT
    dev._idle_check(None)
    await hass.async_block_till_done()
    assert dev.connected is False and dev._unsub_silence is None


async def test_a_pause_reports_its_highest_level_once(hass: HomeAssistant, setup) -> None:
    """History 2026-11-18/19: inside the pause the token sent two interleaved series,
    one climbing 21 -> 27 and one 82 -> 94. Each value went to the sensor (84, 27, 83)
    and the last one became the level at rest: had it been a 27, the saver and the
    low-battery issue (both at 30 %) would have fired on a cell at ~90 %."""
    from custom_components.triki.protocol import stop_command

    from .conftest import BATTERY
    from .test_device_errors import battery_callback

    dev = setup.runtime_data
    client, _ = await connect(hass, setup)
    seen: list[str] = []
    hass.bus.async_listen(
        "state_changed",
        lambda ev: (
            seen.append(ev.data["new_state"].state) if ev.data["entity_id"] == BATTERY else None
        ),
    )

    async def write(uuid, data, response=False):
        if data == stop_command():
            cb = battery_callback(client)
            for level in (84, 23, 89, 25, 27):  # the low one comes last
                hass.loop.call_soon(cb, None, bytearray([level]))

    client.write_gatt_char = AsyncMock(side_effect=write)
    dev._battery_refreshed = float("-inf")
    dev._last_activity -= 60
    dev._battery_check(None)
    await settle(hass, dev)

    assert dev.battery == 89 and dev.battery_rest == 89
    assert not dev.battery_saver
    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, f"{ISSUE_BATTERY_LOW}_{setup.entry_id}") is None
    )
    assert seen == ["89"]  # one update per pause, no 23/25/27 flashes
