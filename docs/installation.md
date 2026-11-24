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
- A Żabka Triki token with a working battery. Close the Żappka app or turn
  Bluetooth off on the phone: the token takes one connection at a time and
  cannot be found while the app holds it.

## HACS (recommended)

1. [Install HACS](https://www.hacs.xyz/docs/use/download/download/) if you do
   not have it.
2. Open HACS and search for *Żabka Triki*. The integration is in the default
   HACS catalog; typing `zabka` or `triki` finds it, no Polish keyboard needed.
   Or use this button:

   [![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=elenium3&repository=ha-triki&category=integration)
3. Download it and
   [restart Home Assistant](https://www.home-assistant.io/docs/configuration/#reloading-changes).

If it does not show up in the search (a HACS install that has not refreshed its
catalog yet), add `https://github.com/elenium3/ha-triki` as a
[custom repository](https://www.hacs.xyz/docs/faq/custom_repositories/) of type
*Integration*.

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

1. Press the cap (the whole cap is the button). It advertises for a few seconds after a
   press, so do this right before the next step.
2. Home Assistant discovers it as *Żabka Triki* under *Discovered* in
   [Settings → Devices & services](https://my.home-assistant.io/redirect/integrations/).
   Confirm, then tick the gestures you want besides press and long press
   (knob, double and triple press, tilt, shake, flip/tap/toss). Everything can
   be changed later in *Configure*.
3. If nothing is discovered:
   [Add integration → Żabka Triki](https://my.home-assistant.io/redirect/config_flow_start/?domain=triki),
   press the button again and pick the token from the list.

The device is created immediately. Until the first connection *Connected* is
off, *Readiness* says asleep and the battery and the other sensors show
*Unknown*.

## First check

Press the button once. The *Action* event entity should show `wake` and then
`single_press`, the *Connected* binary sensor should turn on, and the battery sensor should get a
value within a few seconds (a low first value is normal: it is measured under
load and corrected at the first idle pause, see [Configuration](configuration.md#entities)). If the connection takes more than a second or the
link drops within a minute, the receiver is too far from the token. See
[Radio and placement](radio-and-placement.md).

If a later press does nothing, look at *Readiness* or the card: *Dozing off*
means the token went idle and misses presses for about 3 minutes. Wait rather
than press again; see
[Troubleshooting](troubleshooting.md#presses-ignored-after-a-sleep-disconnect).

Only press and long press are reported out of the box. Rotation (the knob),
double and triple press, tilt, shake and flip/tap/toss are off unless you
ticked them when adding the token; turn them on under *Configure* on the
integration, see [Configuration](configuration.md).

The **Triki live 3D** card is available once a token is added: add it to a
dashboard (reload the page if it is not in the list) and press **Check**. See
[Live 3D card](live-card.md).

## Updating

Through HACS, or replace the folder and restart. Config entries are migrated
automatically; see `async_migrate_entry` in `__init__.py` and the
[changelog](../CHANGELOG.md).

## Removing

Settings → Devices & services → Żabka Triki → ⋮ → Delete. The token is released
and can be discovered again right away.
