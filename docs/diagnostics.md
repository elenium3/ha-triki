# Diagnostics

Settings → Devices & services → Żabka Triki → ⋮ → *Download diagnostics*
produces a JSON like this (addresses redacted):

```json
{
  "entry": {"title": "Triki 4190656753", "data": {"address": "**REDACTED**"}, "options": {"sample_rate": 52, "knob_step": 30}},
  "options": {"rate": 52, "idle_timeout": 30, "sleep_timeout": 0, "knob_step": 30.0, "invert_rotation": false, "wake_as_press": false, "knob": true, "shake": false, "motion_gestures": false, "multi_press": true, "multi_press_window": 0.3, "capture": false},
  "device": {"connected": true, "stream_rate": 26, "firmware": "3.2.1-A", "hardware": null, "battery": 82, "rssi": -71, "led_on": false, "button": false, "pitch": 1.6, "roll": -1.6},
  "link": {"connects": 1, "connect_failures": 0, "drops": 0, "stream_refusals": 0, "notifications": 30111, "frames": 30106, "rate_switches": 3, "parser_dropped_bytes": 25, "last_source": "**REDACTED**", "last_link_s": 0.11, "last_session_s": 1064.6},
  "last_advertisement": {"source": "**REDACTED**", "rssi": -79, "age_s": 5.1, "connectable": true}
}
```

## Fields

**device**

| Field | Meaning |
|---|---|
| `connected` | Link up right now. |
| `stream_rate` | Rate the token was last told to stream at: the configured rate, or 26 while idle. `null` when not connected. |
| `firmware`, `hardware` | Device Information service, read once per entry lifetime. |
| `rssi` | Signal of the last advertisement. |

**link** (counters since the entry was loaded)

| Field | Meaning |
|---|---|
| `connects`, `connect_failures` | Attempts that succeeded or failed. |
| `drops` | The token or the radio closed the link (not an idle disconnect). |
| `stream_refusals` | Connected, start acknowledged, no frames within 3 s. |
| `notifications`, `frames` | BLE notifications received and 14-byte frames parsed from them. Notifications far above frames means BlueZ duplicates, see [Troubleshooting](troubleshooting.md). |
| `rate_switches` | Idle ↔ active stream re-starts over the live link. |
| `led_write_retries` | LED writes that failed with a GATT error and were retried (up to three tries, 0.3 s apart). |
| `parser_dropped_bytes` | Bytes skipped while re-synchronising on a frame header. A handful per session is normal. |
| `last_source` | Scanner the last link went through (redacted: it is the adapter's or proxy's MAC). |
| `last_link_s` | Time from the connect request to the stream running. 0.1–0.3 s through a proxy, 1.5–10 s on a distant local adapter. |
| `last_session_s` | How long the last link lasted. |

**last_advertisement**: what Home Assistant's Bluetooth stack last saw from the
token, from any scanner.

## Debug logging

*Enable debug logging* on the device page, or in `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.triki: debug
```

Debug lines include every event, every rate switch, every skipped connection
attempt with its reason, and the timing of each connect. They are chatty
(several lines per second during a turn); turn debug off when done.

## Captures

The *Record raw sessions* option writes `<config>/triki_captures/<stamp>-<name>.jsonl`,
one JSON object per line:

```json
{"t": 0, "meta": {"name": "Triki 4190656753", "rate": 52, "platform": "homeassistant", "firmware": "3.2.1-A", "battery": 82}}
{"t": 1.234, "hex": "2200f1ff0300fcff0a00f6ff0a08"}
{"t": 1.240, "event": "press", "data": {"count": 1}}
{"t": 40.1, "rate": 26}
{"t": 99.9, "disconnected": true}
```

`tools/replay.py` re-runs a capture through the current parser and gesture
detector; see [Development](development.md).
