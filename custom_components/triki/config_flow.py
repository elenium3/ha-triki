"""Config flow: Bluetooth discovery + manual pick, and options."""

from __future__ import annotations

from typing import Any

try:
    # the schema library of the 2026 cores; those cores alias voluptuous to it,
    # the 2025 cores do not ship it
    import probatio as vol
except ImportError:  # pragma: no cover
    import voluptuous as vol  # type: ignore[no-redef]
from homeassistant import data_entry_flow
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
    async_scanner_count,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CAPTURE,
    CONF_IDLE_TIMEOUT,
    CONF_INVERT_ROTATION,
    CONF_KNOB,
    CONF_KNOB_STEP,
    CONF_MOTION_GESTURES,
    CONF_MULTI_PRESS,
    CONF_MULTI_PRESS_WINDOW,
    CONF_RATE,
    CONF_SHAKE,
    CONF_SLEEP_TIMEOUT,
    CONF_TILT,
    CONF_WAKE_AS_PRESS,
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_INVERT_ROTATION,
    DEFAULT_KNOB,
    DEFAULT_KNOB_STEP,
    DEFAULT_MOTION_GESTURES,
    DEFAULT_MULTI_PRESS,
    DEFAULT_MULTI_PRESS_WINDOW,
    DEFAULT_SHAKE,
    DEFAULT_SLEEP_TIMEOUT,
    DEFAULT_TILT,
    DEFAULT_WAKE_AS_PRESS,
    DOMAIN,
)
from .protocol import DEFAULT_RATE, SUPPORTED_RATES

ADVANCED = "advanced"  # the folded section of the options form

# the gestures offered when a cap is added: each turns one option on (press and
# long press need none); the rest of the options stay at their defaults
SETUP_GESTURES = (CONF_KNOB, CONF_MULTI_PRESS, CONF_TILT, CONF_SHAKE, CONF_MOTION_GESTURES)


def _is_triki(info: BluetoothServiceInfoBleak) -> bool:
    name = (info.name or "").lower()
    # "TrikiDfu..." is a token in its Nordic DFU bootloader (opcode 0x42, also
    # used by the Żappka app for firmware updates): it only offers the DFU
    # service, not the Triki one.
    return name.startswith("triki") and not name.startswith("trikidfu")


class TrikiConfigFlow(ConfigFlow, domain=DOMAIN):
    # 2: idle_timeout no longer drops the link (sleep_timeout does), see async_migrate_entry
    VERSION = 2

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._found: dict[str, str] = {}
        self._title = ""
        self._address = ""

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
        assert self._discovery is not None  # noqa: S101  # set by async_step_bluetooth
        if user_input is not None:
            self._title, self._address = self._discovery.name, self._discovery.address
            return await self.async_step_gestures()
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._discovery.name},
        )

    def _why_nothing_found(self, current: set[str | None]) -> str:
        """Pressing the cap again helps only when a receiver could link to it."""
        if async_scanner_count(self.hass, connectable=True) == 0:
            return "no_connectable_receiver"
        for info in async_discovered_service_info(self.hass, connectable=False):
            if info.address not in current and _is_triki(info):
                # no connectable receiver heard it, or it would be in the list
                return "heard_not_connectable"
        return "no_devices_found"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            self._title, self._address = self._found.get(address, address), address
            return await self.async_step_gestures()

        current = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in current or not _is_triki(info):
                continue
            self._found[info.address] = info.name
        if not self._found:
            return self.async_abort(reason=self._why_nothing_found(current))
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

    async def async_step_gestures(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Which gestures to turn on: they are off until asked for, and the
        options page is easy to miss."""
        if user_input is not None:
            chosen = set(user_input.get("gestures", []))
            return self.async_create_entry(
                title=self._title,
                data={CONF_ADDRESS: self._address},
                options={g: g in chosen for g in SETUP_GESTURES},
            )
        return self.async_show_form(
            step_id="gestures",
            data_schema=vol.Schema(
                {
                    vol.Optional("gestures", default=[]): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(SETUP_GESTURES),
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                            translation_key="gestures",
                        )
                    )
                }
            ),
            description_placeholders={"name": self._title},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TrikiOptionsFlow()


class TrikiOptionsFlow(OptionsFlowWithReload):
    """Every option feeds the BLE session, so a change reloads the entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            # the options are stored flat; the section is only how the form looks
            advanced = user_input.pop(ADVANCED, {})
            data = {**user_input, **advanced}
            data[CONF_RATE] = int(data[CONF_RATE])
            return self.async_create_entry(data=data)

        o = self.config_entry.options
        advanced = vol.Schema(
            {
                vol.Required(
                    CONF_MULTI_PRESS_WINDOW,
                    default=o.get(CONF_MULTI_PRESS_WINDOW, DEFAULT_MULTI_PRESS_WINDOW),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.2,
                        max=1.5,
                        step=0.05,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_KNOB_STEP, default=o.get(CONF_KNOB_STEP, DEFAULT_KNOB_STEP)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=180,
                        step=5,
                        unit_of_measurement="°",
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
                        min=0,
                        max=600,
                        step=5,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_SLEEP_TIMEOUT,
                    default=o.get(CONF_SLEEP_TIMEOUT, DEFAULT_SLEEP_TIMEOUT),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=3600,
                        step=30,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_CAPTURE, default=o.get(CONF_CAPTURE, False)
                ): selector.BooleanSelector(),
            }
        )
        # the gestures up front; the link, timing and debug settings fold away
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_KNOB, default=o.get(CONF_KNOB, DEFAULT_KNOB)
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_MULTI_PRESS, default=o.get(CONF_MULTI_PRESS, DEFAULT_MULTI_PRESS)
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_TILT, default=o.get(CONF_TILT, DEFAULT_TILT)
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_SHAKE, default=o.get(CONF_SHAKE, DEFAULT_SHAKE)
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_MOTION_GESTURES,
                    default=o.get(CONF_MOTION_GESTURES, DEFAULT_MOTION_GESTURES),
                ): selector.BooleanSelector(),
                vol.Required(ADVANCED): data_entry_flow.section(advanced, {"collapsed": True}),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
