"""Config flow: Bluetooth discovery + manual pick, and options."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CAPTURE,
    CONF_KNOB,
    CONF_MOTION_GESTURES,
    CONF_MULTI_PRESS,
    CONF_MULTI_PRESS_WINDOW,
    CONF_WAKE_AS_PRESS,
    CONF_IDLE_TIMEOUT,
    CONF_INVERT_ROTATION,
    CONF_KNOB_STEP,
    CONF_RATE,
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_INVERT_ROTATION,
    DEFAULT_KNOB,
    DEFAULT_MOTION_GESTURES,
    DEFAULT_MULTI_PRESS,
    DEFAULT_MULTI_PRESS_WINDOW,
    DEFAULT_WAKE_AS_PRESS,
    DEFAULT_KNOB_STEP,
    DEFAULT_RATE,
    DOMAIN,
)
from .protocol import SUPPORTED_RATES


def _is_triki(info: BluetoothServiceInfoBleak) -> bool:
    return (info.name or "").lower().startswith("triki")


class TrikiConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._found: dict[str, str] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        if not _is_triki(discovery_info):
            return self.async_abort(reason="not_supported")
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovery is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovery.name,
                data={CONF_ADDRESS: self._discovery.address},
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._discovery.name},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=self._found.get(address, address),
                data={CONF_ADDRESS: address},
            )

        current = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in current or not _is_triki(info):
                continue
            self._found[info.address] = info.name
        if not self._found:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {a: f"{n} ({a})" for a, n in self._found.items()}
                    )
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TrikiOptionsFlow()


class TrikiOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            user_input[CONF_RATE] = int(user_input[CONF_RATE])
            return self.async_create_entry(data=user_input)

        o = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_RATE, default=str(o.get(CONF_RATE, DEFAULT_RATE))
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[str(r) for r in SUPPORTED_RATES],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_IDLE_TIMEOUT,
                    default=o.get(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=600, step=5, unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_KNOB_STEP, default=o.get(CONF_KNOB_STEP, DEFAULT_KNOB_STEP)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5, max=180, step=5, unit_of_measurement="°",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_INVERT_ROTATION,
                    default=o.get(CONF_INVERT_ROTATION, DEFAULT_INVERT_ROTATION),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_WAKE_AS_PRESS,
                    default=o.get(CONF_WAKE_AS_PRESS, DEFAULT_WAKE_AS_PRESS),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_KNOB, default=o.get(CONF_KNOB, DEFAULT_KNOB)
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_MOTION_GESTURES,
                    default=o.get(CONF_MOTION_GESTURES, DEFAULT_MOTION_GESTURES),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_MULTI_PRESS, default=o.get(CONF_MULTI_PRESS, DEFAULT_MULTI_PRESS)
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_MULTI_PRESS_WINDOW,
                    default=o.get(CONF_MULTI_PRESS_WINDOW, DEFAULT_MULTI_PRESS_WINDOW),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.2, max=1.5, step=0.05, unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_CAPTURE, default=o.get(CONF_CAPTURE, False)
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
