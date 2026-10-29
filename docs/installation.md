# Installation

## Requirements

- Home Assistant 2025.8 or newer with the
  [Bluetooth integration](https://www.home-assistant.io/integrations/bluetooth/)
  set up.
- A Bluetooth path to the token. Recommended: an ESP32 board flashed as an
  ESPHome Bluetooth proxy, placed where the token is used. If you have never
  made one, [Bluetooth proxy for beginners](bluetooth-proxy.md) walks through
  it. A local adapter in the Home Assistant machine also works if the token is
  used right next to it; see [Radio and placement](radio-and-placement.md).
- A Żabka Triki token with a working battery.

## HACS (recommended)

1. [Install HACS](https://www.hacs.xyz/docs/use/download/download/) if you do
   not have it.
2. HACS → ⋮ → *Custom repositories*
   ([how](https://www.hacs.xyz/docs/faq/custom_repositories/)): repository
   `https://github.com/elenium3/ha-triki`, type *Integration*.
3. Download *Żabka Triki* and
   [restart Home Assistant](https://www.home-assistant.io/docs/configuration/#reloading-changes).

## Manual

Copy `custom_components/triki` into the `custom_components` folder of your
[configuration directory](https://www.home-assistant.io/docs/configuration/)
(create the folder if it is missing) and restart. Each
[release](https://github.com/elenium3/ha-triki/releases) ships a `triki.zip`
with the files of that folder, without the folder itself (that is the layout
HACS expects); unpack it into `custom_components/triki/`:

```bash
mkdir -p custom_components/triki
unzip triki.zip -d custom_components/triki
```

## Adding the token

1. Press the green button on the token. It advertises for a few seconds after a
   press, so do this right before the next step.
2. Home Assistant discovers it as *Żabka Triki* under *Discovered* in
   [Settings → Devices & services](https://my.home-assistant.io/redirect/integrations/).
   Confirm.
3. If nothing is discovered:
   [Add integration → Żabka Triki](https://my.home-assistant.io/redirect/config_flow_start/?domain=triki),
   press the button again and pick the token from the list.

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
