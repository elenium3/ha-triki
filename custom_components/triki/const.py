"""Constants for the Żabka Triki integration."""

from __future__ import annotations

DOMAIN = "triki"
MANUFACTURER = "Żabka / Caps Apps"
MODEL = "Triki"

CONF_RATE = "sample_rate"
CONF_IDLE_TIMEOUT = "idle_timeout"
CONF_KNOB_STEP = "knob_step"
CONF_INVERT_ROTATION = "invert_rotation"
CONF_CAPTURE = "capture"

DEFAULT_RATE = 104
DEFAULT_IDLE_TIMEOUT = 30  # s without motion/button -> disconnect (0 = never)
DEFAULT_KNOB_STEP = 30
DEFAULT_INVERT_ROTATION = False

BUS_EVENT = "triki_event"

EVENT_TYPES = [
    "wake",
    "press",
    "double_press",
    "triple_press",
    "long_press",
    "rotate_cw",
    "rotate_ccw",
    "shake",
    "tap",
    "throw",
    "flip",
]

SIGNAL_UPDATE = f"{DOMAIN}_update_{{}}"
SIGNAL_EVENT = f"{DOMAIN}_event_{{}}"

# Tilt sensors are throttled to keep the recorder sane.
TILT_PUBLISH_INTERVAL = 1.0
BATTERY_POLL_INTERVAL = 600.0
