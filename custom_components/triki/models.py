"""Options of one Triki config entry, parsed once at setup."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

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
    DEFAULT_WAKE_AS_PRESS,
)
from .protocol import DEFAULT_RATE, SUPPORTED_RATES


@dataclass(frozen=True, slots=True, kw_only=True)
class TrikiOptions:
    rate: int = DEFAULT_RATE
    idle_timeout: int = DEFAULT_IDLE_TIMEOUT
    sleep_timeout: int = DEFAULT_SLEEP_TIMEOUT
    knob_step: float = DEFAULT_KNOB_STEP
    invert_rotation: bool = DEFAULT_INVERT_ROTATION
    wake_as_press: bool = DEFAULT_WAKE_AS_PRESS
    knob: bool = DEFAULT_KNOB
    shake: bool = DEFAULT_SHAKE
    motion_gestures: bool = DEFAULT_MOTION_GESTURES
    multi_press: bool = DEFAULT_MULTI_PRESS
    multi_press_window: float = DEFAULT_MULTI_PRESS_WINDOW
    capture: bool = False

    @classmethod
    def from_entry(cls, entry: ConfigEntry) -> TrikiOptions:
        o = entry.options
        # the options flow only offers valid values; a hand-edited store must
        # not crash the stream (unknown rate) or the gesture math (zero step)
        rate = int(o.get(CONF_RATE, DEFAULT_RATE))
        if rate not in SUPPORTED_RATES:
            rate = DEFAULT_RATE
        return cls(
            rate=rate,
            idle_timeout=max(0, int(o.get(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT))),
            sleep_timeout=max(0, int(o.get(CONF_SLEEP_TIMEOUT, DEFAULT_SLEEP_TIMEOUT))),
            knob_step=max(1.0, float(o.get(CONF_KNOB_STEP, DEFAULT_KNOB_STEP))),
            invert_rotation=bool(o.get(CONF_INVERT_ROTATION, DEFAULT_INVERT_ROTATION)),
            wake_as_press=bool(o.get(CONF_WAKE_AS_PRESS, DEFAULT_WAKE_AS_PRESS)),
            knob=bool(o.get(CONF_KNOB, DEFAULT_KNOB)),
            shake=bool(o.get(CONF_SHAKE, DEFAULT_SHAKE)),
            motion_gestures=bool(o.get(CONF_MOTION_GESTURES, DEFAULT_MOTION_GESTURES)),
            multi_press=bool(o.get(CONF_MULTI_PRESS, DEFAULT_MULTI_PRESS)),
            multi_press_window=max(
                0.1, float(o.get(CONF_MULTI_PRESS_WINDOW, DEFAULT_MULTI_PRESS_WINDOW))
            ),
            capture=bool(o.get(CONF_CAPTURE, False)),
        )
