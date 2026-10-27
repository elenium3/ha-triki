"""Hardware probe for the Żabka Triki. Runs standalone (no Home Assistant).

    pip install bleak
    python tools/triki_probe.py scan
    python tools/triki_probe.py info   [--address XX:..]
    python tools/triki_probe.py led    [--address XX:..]
    python tools/triki_probe.py record [--address XX:..] [--rate 104] [--seconds 20] [--label shake]
    python tools/triki_probe.py guided [--address XX:..] [--rate 104]

`record`/`guided` write raw notifications to captures/*.jsonl and print what the
integration's parser + gesture detector make of them, live. Captures are the
ground truth for tests/test_replay.py.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import time
import types
from datetime import datetime
from pathlib import Path

from bleak import BleakClient, BleakScanner

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "custom_components" / "triki"
CAPTURES = ROOT / "captures"


def _load_core():
    """Import protocol.py + gestures.py without running the HA package __init__."""
    pkg = types.ModuleType("triki_core")
    pkg.__path__ = [str(CORE)]
    sys.modules["triki_core"] = pkg
    mods = {}
    for name in ("protocol", "gestures"):
        spec = importlib.util.spec_from_file_location(f"triki_core.{name}", CORE / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        mods[name] = mod
    return mods["protocol"], mods["gestures"]


P, G = _load_core()

DIS = {
    "manufacturer": "00002a29-0000-1000-8000-00805f9b34fb",
    "model": P.MODEL_UUID,
    "firmware": P.FIRMWARE_REV_UUID,
    "hardware": P.HARDWARE_REV_UUID,
    "software": "00002a28-0000-1000-8000-00805f9b34fb",
}


async def find(address: str | None, timeout: float = 15.0):
    if address:
        dev = await BleakScanner.find_device_by_address(address, timeout=timeout)
    else:
        print(f"Scanning {timeout:.0f}s — press the green button to wake the token...")
        dev = await BleakScanner.find_device_by_filter(
            lambda d, ad: (d.name or ad.local_name or "").lower().startswith("triki"),
            timeout=timeout,
        )
    if dev is None:
        sys.exit("Triki not found (asleep? press the button and retry)")
    print(f"Found {dev.name} {dev.address}")
    return dev


async def cmd_scan(args):
    print("Scanning 10s...")
    found = await BleakScanner.discover(timeout=10.0, return_adv=True)
    for d, ad in found.values():
        name = d.name or ad.local_name or ""
        if name.lower().startswith("triki"):
            print(f"{d.address}  {name!r}  rssi={ad.rssi}  uuids={ad.service_uuids}  "
                  f"mfr={ {k: v.hex() for k, v in ad.manufacturer_data.items()} }")


async def cmd_info(args):
    dev = await find(args.address)
    async with BleakClient(dev) as c:
        for svc in c.services:
            print(f"service {svc.uuid}")
            for ch in svc.characteristics:
                print(f"  char {ch.uuid}  {','.join(ch.properties)}")
        for k, u in DIS.items():
            try:
                print(f"{k:12} {bytes(await c.read_gatt_char(u)).decode(errors='replace')!r}")
            except Exception as e:  # noqa: BLE001
                print(f"{k:12} <{e}>")
        print("battery     ", (await c.read_gatt_char(P.BATTERY_LEVEL_UUID))[0], "%")
        print("ctrl (LED)  ", bytes(await c.read_gatt_char(P.CTRL_UUID)).hex())


async def cmd_led(args):
    dev = await find(args.address)
    async with BleakClient(dev) as c:
        for i in range(6):
            on = i % 2 == 0
            await c.write_gatt_char(P.CTRL_UUID, P.led_command(on), response=True)
            back = bytes(await c.read_gatt_char(P.CTRL_UUID)).hex()
            print(f"LED {'on ' if on else 'off'} -> ctrl reads {back}")
            await asyncio.sleep(0.7)
        await c.write_gatt_char(P.CTRL_UUID, P.led_command(False), response=True)


class Session:
    def __init__(self, rate: int, path: Path):
        self.rate = rate
        self.parser = P.FrameParser()
        self.det = G.GestureDetector(rate)
        self.path = path
        self.fh = path.open("w", encoding="utf-8")
        self.t0 = time.perf_counter()
        self.frames = 0
        self.notifs = 0
        self.label = ""
        self.last_print = 0.0
        self.disconnected = asyncio.Event()

    def mark(self, label: str):
        self.label = label
        self.fh.write(json.dumps({"t": self.now(), "mark": label}) + "\n")
        self.fh.flush()

    def now(self) -> float:
        return round(time.perf_counter() - self.t0, 4)

    def on_notify(self, _ch, data: bytearray):
        self.notifs += 1
        self.fh.write(json.dumps({"t": self.now(), "hex": bytes(data).hex()}) + "\n")
        for fr in self.parser.push(data):
            self.frames += 1
            s = P.Sample.from_frame(fr)
            for ev in self.det.update(s):
                print(f"  [{self.now():7.2f}] EVENT {ev.type} {ev.data or ''}")
                self.fh.write(json.dumps({"t": self.now(), "event": ev.type, "data": ev.data}) + "\n")
            if self.now() - self.last_print > 0.5:
                self.last_print = self.now()
                pr = self.det.pitch_roll
                tilt = f"pitch={pr[0]:6.1f} roll={pr[1]:6.1f}" if pr else ""
                print(f"  g=({s.gx:7.1f},{s.gy:7.1f},{s.gz:7.1f})dps "
                      f"a=({s.ax:5.2f},{s.ay:5.2f},{s.az:5.2f})g |a|={s.accel_mag:4.2f} "
                      f"btn={int(s.button)} {tilt}")

    def close(self):
        el = max(self.now(), 1e-6)
        print(f"\n{self.notifs} notifications, {self.frames} frames in {el:.1f}s "
              f"= {self.frames / el:.1f} Hz (requested {self.rate}), dropped bytes {self.parser.dropped}")
        self.fh.write(json.dumps({"t": self.now(), "summary": {
            "notifications": self.notifs, "frames": self.frames, "dropped": self.parser.dropped}}) + "\n")
        self.fh.close()
        print(f"capture: {self.path}")


async def _stream(args, steps):
    dev = await find(args.address)
    CAPTURES.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = CAPTURES / f"{stamp}-{args.label or args.cmd}-{args.rate}hz.jsonl"
    sess = Session(args.rate, path)

    def on_disc(_c):
        print(f"  [{sess.now():7.2f}] !!! DISCONNECTED by token/stack")
        sess.fh.write(json.dumps({"t": sess.now(), "disconnected": True}) + "\n")
        sess.disconnected.set()

    async with BleakClient(dev, disconnected_callback=on_disc) as c:
        hdr = {"t": 0, "meta": {
            "name": dev.name, "rate": args.rate, "platform": sys.platform,
            "firmware": bytes(await c.read_gatt_char(P.FIRMWARE_REV_UUID)).decode(errors="replace"),
            "battery": (await c.read_gatt_char(P.BATTERY_LEVEL_UUID))[0]}}
        sess.fh.write(json.dumps(hdr) + "\n")
        print("meta:", hdr["meta"])
        await c.start_notify(P.NUS_TX_UUID, sess.on_notify)
        await c.write_gatt_char(P.NUS_RX_UUID, P.start_command(args.rate), response=True)
        try:
            await steps(sess)
        finally:
            if c.is_connected:
                try:
                    await c.stop_notify(P.NUS_TX_UUID)
                except Exception:  # noqa: BLE001
                    pass
            sess.close()


async def cmd_record(args):
    async def steps(sess):
        sess.mark(args.label or "free")
        print(f"Recording {args.seconds}s (label={args.label or 'free'}) — Ctrl+C to stop early")
        try:
            await asyncio.wait_for(sess.disconnected.wait(), args.seconds)
        except TimeoutError:
            pass
    await _stream(args, steps)


GUIDE = [
    ("still", 4, "Положи токен ровно, логотипом вверх, не трогай"),
    ("press", 5, "Одно короткое нажатие кнопки"),
    ("double_press", 5, "Двойное нажатие"),
    ("long_press", 5, "Зажми кнопку ~1.5 с"),
    ("rotate_cw", 6, "На столе поверни по часовой на ~90° (вид сверху), медленно"),
    ("rotate_ccw", 6, "Теперь против часовой на ~90°"),
    ("shake", 5, "Потряси в руке"),
    ("tap", 5, "Стукни им по столу (несильно)"),
    ("flip", 6, "Переверни логотипом вниз и оставь лежать"),
    ("throw", 6, "Подбрось на ~20 см и поймай"),
    ("idle", 30, "Положи и не трогай 30 с — смотрим, отвалится ли сам"),
]


async def cmd_guided(args):
    async def steps(sess):
        for label, secs, text in GUIDE:
            if sess.disconnected.is_set():
                print("token disconnected — stopping")
                return
            print(f"\n=== {label}: {text} ({secs}s)")
            await asyncio.sleep(1.0)
            print("GO")
            sess.mark(label)
            try:
                await asyncio.wait_for(sess.disconnected.wait(), secs)
            except TimeoutError:
                pass
    await _stream(args, steps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["scan", "info", "led", "record", "guided"])
    ap.add_argument("--address")
    ap.add_argument("--rate", type=int, default=104, choices=P.SUPPORTED_RATES)
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--label", default="")
    args = ap.parse_args()
    fn = globals()[f"cmd_{args.cmd}"]
    try:
        asyncio.run(fn(args))
    except KeyboardInterrupt:
        print("interrupted")


if __name__ == "__main__":
    main()
