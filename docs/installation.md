# Installation

## Requirements

- Home Assistant 2025.8 or newer with the
  [Bluetooth integration](https://www.home-assistant.io/integrations/bluetooth/)
  set up.
- A Bluetooth path to the token: an
  [ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy.html)
  with `active: true` (recommended, see [Radio and placement](radio-and-placement.md))
  or a local adapter.
- A Żabka Triki token with a working battery.

## HACS (recommended)

1. HACS → Integrations → ⋮ → *Custom repositories*.
2. Repository `https://github.com/elenium3/ha-triki`, category *Integration*.
3. Install *Żabka Triki*, restart Home Assistant.

## Manual

Copy `custom_components/triki` into `<config>/custom_components/` and restart.
Releases on GitHub ship a `triki.zip` with the same content.

## Adding the token

1. Press the green button on the token. It advertises for a few seconds after a
   press, so do this right before the next step.
2. Home Assistant discovers it as *Żabka Triki* (Settings → Devices & services →
   *Discovered*). Confirm.
3. If nothing is discovered: *Add integration → Żabka Triki*, press the button
   again and pick the token from the list.

The device is created immediately. Entities that only make sense while the token
is linked (button, action, tilt) show as unavailable until the first connection.

## First check

Press the button once. The *Action* event entity should show `wake`, the
*Connected* binary sensor should turn on, and the battery sensor should get a
value within a few seconds. If the connection takes more than a second or the
link drops within a minute, the receiver is too far from the token. See
[Radio and placement](radio-and-placement.md).

## Updating

Through HACS, or replace the folder and restart. Config entries are migrated
automatically; see `async_migrate_entry` in `__init__.py` and the
[changelog](../CHANGELOG.md).

## Removing

Settings → Devices & services → Żabka Triki → ⋮ → Delete. The token is released
and can be discovered again right away.
