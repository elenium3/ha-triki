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
CONF_WAKE_AS_PRESS = "wake_as_press"
CONF_MULTI_PRESS_WINDOW = "multi_press_window"
CONF_MOTION_GESTURES = "motion_gestures"
CONF_MULTI_PRESS = "multi_press"
CONF_KNOB = "knob"
CONF_SHAKE = "shake"
CONF_TILT = "tilt"

CONF_SLEEP_TIMEOUT = "sleep_timeout"

DEFAULT_IDLE_TIMEOUT = 30  # s without motion/button -> stream drops to IDLE_RATE (0 = never)
DEFAULT_SLEEP_TIMEOUT = 300  # s without motion/button -> drop the link (0 = never)
# Lowest rate the firmware accepts. Enough for the button and to notice motion,
# a quarter of the radio traffic of 104 Hz. The link itself stays up: a reconnect
# starts with a slow, lossy link for 10-20 s and the token then advertises at
# full tilt for ~3 min, so dropping and re-taking the link is the expensive path.
IDLE_RATE = 26
DEFAULT_KNOB_STEP = 30
DEFAULT_INVERT_ROTATION = False
DEFAULT_WAKE_AS_PRESS = True
# set in the entry data once the 0.3.0 default of wake_as_press has been applied
WAKE_PRESS_MARK = "wake_press_on"
DEFAULT_MOTION_GESTURES = False
DEFAULT_MULTI_PRESS = False
DEFAULT_KNOB = False
DEFAULT_SHAKE = False
DEFAULT_TILT = False
DEFAULT_MULTI_PRESS_WINDOW = 0.5  # s between releasing and pressing again

BUS_EVENT = "triki_event"

# The button uses Home Assistant's standard button event types
# (homeassistant.components.event.ButtonEventType), written as plain strings
# because the supported cores are older than the enum.
EVENT_SINGLE_PRESS = "single_press"
EVENT_MULTI_PRESS = "multi_press"  # data: press_count, 2 or 3
EVENT_LONG_PRESS_START = "long_press_start"  # held past the threshold, still down
EVENT_LONG_PRESS_END = "long_press_end"  # released after a long press
ATTR_PRESS_COUNT = "press_count"
MULTI_PRESS_MAX = 3  # more presses than this count as three, as they always did

EVENT_TYPES = [
    "wake",
    EVENT_SINGLE_PRESS,
    EVENT_MULTI_PRESS,
    EVENT_LONG_PRESS_START,
    EVENT_LONG_PRESS_END,
    "rotate_cw",
    "rotate_ccw",
    "tilt_left",
    "tilt_right",
    "shake",
    "tap",
    "throw",
    "flip",
]

# What the automation editor offers under "Device": one line per gesture, so a
# double and a triple press are separate although both arrive as multi_press.
TRIGGER_TYPES = [
    trigger
    for kind in EVENT_TYPES
    for trigger in (("double_press", "triple_press") if kind == EVENT_MULTI_PRESS else (kind,))
]


# Tilt sensors are throttled to keep the recorder sane.
TILT_PUBLISH_INTERVAL = 1.0
# The token measures its battery only while it is not streaming, so a refresh
# means a short stream pause (see TrikiDevice._async_pause_for_battery). Do it
# at most this often, and only while the token has been idle for a while.
BATTERY_REFRESH_INTERVAL = 1800.0
# A link that is never dropped keeps the token awake around the clock: the
# 7.5 ms connection plus the IMU draw about 1 mA, so a CR2032 lasts about a
# week. A sagging cell then locks the token up (no advertising, the button does
# nothing) until the cell is pulled. Seen twice on the development unit, each
# time at the end of a 7-21 h link, with the level at rest at 16-19 %.
# At or below this level at rest, a "never" sleep timeout falls back to the
# default one so the token gets to sleep between uses.
BATTERY_SAVER_LEVEL = 30
# At or below this level at rest, a repair issue asks for a new cell. It is
# cleared once a level this many points higher is measured (a replaced cell).
# On 14 Nov 2026 a cell that measured 18-21 % at rest locked up two different
# tokens four times, each time 20-27 s into a session with the default 300 s
# sleep timeout; the same tokens never did it on a fresh cell. So the warning
# has to come well before 20 %.
BATTERY_LOW_LEVEL = 30
BATTERY_LOW_CLEAR_MARGIN = 10

ISSUE_SLEEP_NEVER = "sleep_timeout_never"
ISSUE_BATTERY_LOW = "battery_low"
ISSUE_NOT_RESPONDING = "not_responding"
ISSUE_LINK_LOSSY = "link_lossy"
