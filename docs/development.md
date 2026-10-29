# Development

## Setup

```bash
git clone https://github.com/elenium3/ha-triki
cd ha-triki
python3.13 -m venv .venv && . .venv/bin/activate
pip install pytest-homeassistant-custom-component pytest-cov mypy ruff bleak
```

`pytest-homeassistant-custom-component` pins a Home Assistant version; the
tests run against that. The Bluetooth component imports `usb`, whose pinned
requirements are not installed by the test package. CI installs them from the
installed Home Assistant's manifests; locally:

```bash
pip install $(python - <<'EOF'
import json, pathlib, homeassistant
base = pathlib.Path(homeassistant.__file__).parent / "components"
print(" ".join(r for c in ("bluetooth", "usb") for r in json.load(open(base / c / "manifest.json"))["requirements"]))
EOF
)
```

## Checks

```bash
ruff check custom_components tests tools
ruff format custom_components tests
mypy
pytest --cov --cov-fail-under=95
```

The ruff rule set is the subset of Home Assistant core's that applies to a custom
integration; mypy runs strict. Both are configured in `pyproject.toml`.

## Layout

```
custom_components/triki/
  __init__.py      entry setup, migration, platform forwarding
  config_flow.py   discovery, manual pick, options
  device.py        TrikiDevice: advertisements, link, stream, idle/sleep timers
  gestures.py      GestureDetector: pure-Python state machine, no HA imports
  protocol.py      GATT UUIDs, commands, frame parser, Sample (no HA imports)
  models.py        TrikiOptions parsed once from the entry
  capture.py       optional raw session recorder
  entity.py        base entity, device info
  event.py, binary_sensor.py, light.py, sensor.py
  diagnostics.py
tests/             pytest-homeassistant-custom-component, mocked bleak client
tools/
  triki_probe.py   standalone probe: scan, info, LED, record, guided capture
  replay.py        run a capture through the parser and gesture detector
```

`protocol.py` and `gestures.py` deliberately have no Home Assistant imports so
that the tools and the tests can use them directly. See
[Architecture](architecture.md) for how the pieces interact.

## Working with a real token

`tools/triki_probe.py` needs only `bleak` and a local adapter:

```bash
python tools/triki_probe.py scan                      # find the token (press its button)
python tools/triki_probe.py info                      # firmware, battery, services
python tools/triki_probe.py led                       # blink the LED
python tools/triki_probe.py record --rate 52 --seconds 20 --label shake
python tools/triki_probe.py guided                    # prompts for a series of gestures
```

`record` and `guided` write `captures/*.jsonl` and print what the parser and the
detector make of the stream, live. The same format is produced by the
integration's *Record raw sessions* option.

Replay a capture after changing a threshold in `gestures.py`:

```bash
python tools/replay.py captures/20261029-shake.jsonl
python tools/replay.py captures/20261029-shake.jsonl --frames   # dump every decoded frame
```

The output lists, per labelled segment, the events the detector produces now
next to the events that were recorded live.

## Tests

- `test_protocol.py`: frame parsing, re-sync on garbage, commands.
- `test_gestures.py`: the detector on synthetic streams (presses, turns, shake,
  start-up discard, button/knob interaction).
- `test_init.py`, `test_device_errors.py`: end-to-end through Home Assistant
  with a mocked bleak client: discovery, connect, stream, entities, bus events,
  every failure path, migration.
- `test_idle.py`: idle rate switch, activity during a rate write, sleep
  disconnect.
- `test_config_flow.py`, `test_diagnostics.py`.

`tests/conftest.py` provides `setup` (a loaded entry for a sleeping token) and
`connect()` (one fresh advertisement, a mocked client, the notify callback).
`tests/helpers.py::frame()` builds a 14-byte frame from physical units.

## Releasing

1. Update `CHANGELOG.md`: move *Unreleased* into a new version section.
2. Tag `vX.Y.Z` and publish a GitHub release. The release workflow stamps the
   version into `manifest.json` and attaches `triki.zip` for HACS.

## Conventions

- Commit messages: imperative, one topic, body explains *why*.
- Hardware observations go into the docs with numbers and conditions (adapter or
  proxy, distance, RSSI), not into code comments alone.
- Do not add gestures without a capture that shows them.
