"""Repair flows: the one fixable issue is a link held forever."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant

from .const import CONF_SLEEP_TIMEOUT, DEFAULT_SLEEP_TIMEOUT

if TYPE_CHECKING:
    # annotation only: the name does not exist in the oldest supported core (2025.8)
    from homeassistant.components.repairs import RepairsFlowResult


class SleepTimeoutRepairFlow(RepairsFlow):
    """Set the sleep timeout back to the default so the token can sleep."""

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> RepairsFlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="confirm",
                description_placeholders={"seconds": str(DEFAULT_SLEEP_TIMEOUT)},
            )
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is not None:
            self.hass.config_entries.async_update_entry(
                entry, options={**entry.options, CONF_SLEEP_TIMEOUT: DEFAULT_SLEEP_TIMEOUT}
            )
            # options are read at setup (the options flow reloads by itself)
            self.hass.config_entries.async_schedule_reload(entry.entry_id)
        return self.async_create_entry(data={})


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    return SleepTimeoutRepairFlow(str((data or {})["entry_id"]))
