"""Which receiver the link goes through, the wait for proxies after a start, the shake recorder."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.bluetooth import BaseHaRemoteScanner
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant

from custom_components.triki import device as device_mod
from custom_components.triki.diagnostics import async_get_config_entry_diagnostics
from custom_components.triki.gestures import SHAKE_RECORD_S, GestureDetector
from custom_components.triki.protocol import Sample

from .conftest import ESTABLISH, make_client, service_info
from .helpers import frame


async def _advertise(hass: HomeAssistant, entry, client):
    est = AsyncMock(return_value=client)
    with patch(ESTABLISH, est):
        entry.runtime_data._on_advertisement(service_info(), None)
        await hass.async_block_till_done()
    return est


def _scanner(remote: bool, source: str = "local", name: str = "hci0 (00:11:22:33:44:55)"):
    scanner = MagicMock(spec=BaseHaRemoteScanner) if remote else MagicMock()
    scanner.source = source
    scanner.name = name
    return scanner


async def test_the_link_path_is_habluetooths_not_the_adverts(hass: HomeAssistant, setup) -> None:
    """habluetooth may link through another scanner than the one that heard the advert."""
    client = make_client()
    client._connected_scanner = _scanner(
        True, "D0:EF:76:33:5A:0E", "hm-ble-esp32 (D0:EF:76:33:5A:0E)"
    )
    with patch.object(
        device_mod.bluetooth, "async_scanner_by_source", return_value=client._connected_scanner
    ):
        assert (await _advertise(hass, setup, client)).await_count == 1
        dev = setup.runtime_data
        assert dev.stats.last_source == "D0:EF:76:33:5A:0E"  # the advert came via "local"
        assert dev.link_source_name == "hm-ble-esp32"


async def test_without_a_path_record_the_advert_source_stays(hass: HomeAssistant, setup) -> None:
    client = make_client()
    client._connected_scanner = None
    assert (await _advertise(hass, setup, client)).await_count == 1
    assert setup.runtime_data.stats.last_source == "local"


async def test_after_a_start_a_local_adapter_waits_for_a_proxy(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    dev._on_ha_started(None)  # as if Home Assistant had just started
    with patch.object(
        device_mod.bluetooth, "async_scanner_by_source", return_value=_scanner(False)
    ):
        assert (await _advertise(hass, setup, make_client())).await_count == 0
    dev._last_attempt = 0
    with patch.object(device_mod.bluetooth, "async_scanner_by_source", return_value=_scanner(True)):
        assert (await _advertise(hass, setup, make_client())).await_count == 1


async def test_the_wait_for_a_proxy_ends(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    dev._on_ha_started(None)
    dev._proxy_grace_until -= device_mod._PROXY_GRACE_S + 1  # the grace is over
    with patch.object(
        device_mod.bluetooth, "async_scanner_by_source", return_value=_scanner(False)
    ):
        assert (await _advertise(hass, setup, make_client())).await_count == 1


async def test_a_running_home_assistant_does_not_wait(hass: HomeAssistant, setup) -> None:
    """Reloading the entry (an options change) is not a start: no grace."""
    assert setup.runtime_data._proxy_grace_until == 0.0
    with patch.object(
        device_mod.bluetooth, "async_scanner_by_source", return_value=_scanner(False)
    ):
        assert (await _advertise(hass, setup, make_client())).await_count == 1


async def test_set_up_during_the_start_waits_for_the_started_event(hass: HomeAssistant) -> None:
    """The grace starts when Home Assistant has started, not when the entry was set up."""
    dev = device_mod.TrikiDevice.__new__(device_mod.TrikiDevice)
    dev.hass = hass
    dev._unsub_started = None
    dev._proxy_grace_until = 0.0
    with patch.object(type(hass), "is_running", new=False):
        dev._stopping = False
        dev._unsub_adv = dev._unsub_poll = None
        dev.address = "AA:BB:CC:DD:EE:FF"
        with patch.object(
            device_mod.bluetooth, "async_register_advertisement_callback", create=True
        ):
            dev.async_start()
    assert dev._proxy_grace_until == float("inf")
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert dev._proxy_grace_until < float("inf")
    assert dev._unsub_started is None


def _shake(d: GestureDetector) -> list:
    out = []
    t = 0.0
    for _ in range(50):  # still, then swings
        t += 1 / 52
        out += d.update(Sample.from_frame(frame()), t)
    for i in range(30):
        t += 1 / 52
        s = 1500.0 if i % 4 < 2 else -1500.0
        out += d.update(Sample.from_frame(frame(gx=s, ax=5.0 if s > 0 else -5.0)), t)
    return out


def test_a_shake_keeps_the_stream_before_it() -> None:
    d = GestureDetector(52, startup_discard=0)
    events = _shake(d)
    assert "shake" in [e.type for e in events]
    win = d.shake_window
    assert win and win[-1][0] == 0.0  # the frame the shake fired on
    assert -SHAKE_RECORD_S - 0.05 <= win[0][0] < -1.0  # 1.5 s of history
    assert win[-1][1] == 19  # ms since the previous arrival: 52 Hz
    assert win[0][2] == 1.0 and win[-1][3] >= 1000  # |a| at rest, |gyro| swinging


async def test_diagnostics_show_the_recorded_shakes(hass: HomeAssistant, setup) -> None:
    dev = setup.runtime_data
    dev.shake_log.append(
        {"at": "2026-11-19T04:00:00+00:00", "rate": 52, "frames": [[0.0, 19, 3.1, 1500, 0]]}
    )
    data = await async_get_config_entry_diagnostics(hass, setup)
    assert data["shakes"][0]["frames"] == [[0.0, 19, 3.1, 1500, 0]]
    assert "link_via" in data
