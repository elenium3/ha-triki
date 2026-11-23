// node --test tests/js
import { test } from "node:test";
import assert from "node:assert/strict";

import { CheckRun, stripAddress } from "../../custom_components/triki/frontend/triki-check.js";

const LIVE = { connected: true, streaming: true, rate: 52, face: "cap_up", via: "hm-ble-esp32", rssi: -60 };
const OPTS = { knob: true, knob_step: 30, invert_rotation: false, motion_gestures: true, multi_press: true, shake: true };
const FLAT_Q = [1, 0, 0, 0];

function rig(options = OPTS) {
  let t = 0;
  const run = new CheckRun({ options, now: () => t });
  run.feedStatus({ ...LIVE, options });
  const clock = {
    get t() { return t; },
    advance(ms) { t += ms; run.tick(); },
  };
  return { run, clock };
}

// a motion message; `frames` counts the token's frames since setup
function motion(clock, { yaw = 0, gyro = [0, 0, 0], accel = [0, 0, -1], q = FLAT_Q, frames = 0, rate = 52 } = {}) {
  return { quaternion: q, euler: [0, 0, yaw], gyro, accel, button: false, frames, rate, ts: clock.t / 1000 };
}

function goTo(run, id) {
  while (run.step.id !== id) run.skip();
}

// 30 messages a second for `secs`, with the frame counter running at `fps`
function stream(run, clock, secs, fps, extra = () => ({})) {
  const n = Math.round(secs * 30);
  let frames = 0;
  for (let i = 0; i <= n; i++) {
    run.feedMotion(motion(clock, { frames: Math.round(frames), ...extra(i / 30) }));
    if (i < n) { clock.advance(1000 / 30); frames += fps / 30; }
  }
}

test("rest passes on a clean link and reports the figures", () => {
  const { run, clock } = rig();
  assert.equal(run.step.id, "rest");
  assert.ok(run.start());
  stream(run, clock, 10.1, 53);
  assert.equal(run.phase, "done");
  const r = run.results.rest;
  assert.equal(r.status, "pass");
  assert.equal(r.values.loss_pct, 0);
  assert.equal(r.values.via, "hm-ble-esp32");
});

test("rest fails on a lossy link", () => {
  const { run, clock } = rig();
  run.start();
  stream(run, clock, 10.1, 26); // half the frames arrive
  assert.equal(run.results.rest.status, "fail");
  assert.equal(run.results.rest.reason, "loss");
  assert.ok(run.results.rest.values.loss_pct >= 45);
});

test("rest fails when the token is moved", () => {
  const { run, clock } = rig();
  run.start();
  stream(run, clock, 10.1, 53, (s) => ({ gyro: [0, 0, s > 5 && s < 6 ? 60 : 0] }));
  assert.equal(run.results.rest.reason, "moved");
});

test("a link drop pauses the step and it starts over", () => {
  const { run, clock } = rig();
  run.start();
  stream(run, clock, 4, 53);
  run.feedStatus({ ...LIVE, connected: false, streaming: false });
  assert.equal(run.phase, "paused");
  clock.advance(20_000); // no timeout while paused
  assert.equal(run.phase, "paused");
  assert.equal(run.start(), false); // not until the token is back
  run.feedStatus(LIVE);
  assert.equal(run.phase, "ready");
  assert.ok(run.start());
  stream(run, clock, 10.1, 53);
  assert.equal(run.results.rest.status, "pass");
});

test("tilt passes when the dot edge rises in the sensor and the model", () => {
  const { run, clock } = rig();
  goTo(run, "tilt");
  run.start();
  // dot edge (sensor -y) up 25 degrees: gravity "up" leans to -y, the model's -y rises
  const s = Math.sin(0.44), c = Math.cos(0.44);
  const q = [Math.cos(0.22), -Math.sin(0.22), 0, 0]; // about x: -y tips upward
  stream(run, clock, 1.5, 53, () => ({ accel: [0, -s, c], q }));
  assert.equal(run.phase, "done");
  assert.equal(run.results.tilt.status, "pass");
});

test("tilt catches a model that leans the wrong way", () => {
  const { run, clock } = rig();
  goTo(run, "tilt");
  run.start();
  const s = Math.sin(0.44), c = Math.cos(0.44);
  const q = [Math.cos(0.22), Math.sin(0.22), 0, 0]; // the model tips the other edge
  stream(run, clock, 1.5, 53, () => ({ accel: [0, -s, c], q }));
  assert.equal(run.results.tilt.status, "fail");
  assert.equal(run.results.tilt.reason, "model_wrong");
});

test("tilt hints when the other edge is raised and times out", () => {
  const { run, clock } = rig();
  goTo(run, "tilt");
  run.start();
  stream(run, clock, 2, 53, () => ({ accel: [0, 0.4, 0.9] }));
  assert.equal(run.view().live.hint, "other_edge");
  clock.advance(30_000);
  assert.equal(run.results.tilt.reason, "not_raised");
});

// two quarter turns with a regrip between them: turn, pause, turn
function turn(run, clock, degrees, events, kind = "rotate_cw") {
  const secs = 8;
  let fired = 0;
  const angleAt = (s) => {
    const half = degrees / 2;
    if (s < 3) return (s / 3) * half; // first quarter
    if (s < 5) return half; // let go, regrip
    return half + ((s - 5) / 3) * half;
  };
  stream(run, clock, secs, 53, (s) => {
    const due = Math.floor((Math.abs(angleAt(s)) / Math.abs(degrees)) * events);
    while (fired < due) { run.feedEvent(kind, { steps: 1, degrees: 30 }); fired++; }
    return { yaw: ((angleAt(s) % 360) + 540) % 360 - 180 };
  });
  while (fired < events) { run.feedEvent(kind, { steps: 1, degrees: 30 }); fired++; }
}

test("two clockwise quarter turns with a regrip and 6 steps pass", () => {
  const { run, clock } = rig();
  goTo(run, "turn_cw");
  run.start();
  turn(run, clock, -180, 6);
  assert.equal(run.view().live.steps, 6);
  run.done();
  const r = run.results.turn_cw;
  assert.equal(r.status, "pass");
  assert.equal(r.values.angle, -180);
});

test("a turn that lost steps fails, a short or reversed one is redone", () => {
  let { run, clock } = rig();
  goTo(run, "turn_cw");
  run.start();
  turn(run, clock, -180, 3);
  run.done();
  assert.equal(run.results.turn_cw.status, "fail");
  assert.equal(run.results.turn_cw.reason, "steps");

  ({ run, clock } = rig());
  goTo(run, "turn_cw");
  run.start();
  turn(run, clock, -100, 3);
  run.done();
  assert.equal(run.results.turn_cw.reason, "short");

  ({ run, clock } = rig());
  goTo(run, "turn_cw");
  run.start();
  turn(run, clock, 180, 6, "rotate_ccw");
  run.done();
  assert.equal(run.results.turn_cw.reason, "direction");
});

test("inverted rotation expects the other event name, the same hand direction", () => {
  const { run, clock } = rig({ ...OPTS, invert_rotation: true });
  goTo(run, "turn_cw");
  run.start();
  turn(run, clock, -180, 6, "rotate_ccw");
  run.done();
  assert.equal(run.results.turn_cw.status, "pass");
});

test("a 45 degree knob step expects 4 steps; the knob off measures the turn only", () => {
  let { run, clock } = rig({ ...OPTS, knob_step: 45 });
  goTo(run, "turn_ccw");
  run.start();
  turn(run, clock, 180, 4, "rotate_ccw");
  run.done();
  assert.equal(run.results.turn_ccw.status, "pass");

  ({ run, clock } = rig({ ...OPTS, knob: false }));
  goTo(run, "turn_ccw");
  run.start();
  turn(run, clock, 180, 0);
  run.done();
  assert.equal(run.results.turn_ccw.status, "skip");
  assert.equal(run.results.turn_ccw.reason, "knob_off");
});

test("presses in order; a wrong one only hints; the wake press is ignored", () => {
  const { run } = rig();
  goTo(run, "press");
  run.start();
  run.feedEvent("press", { count: 1, source: "wake" });
  assert.equal(run.view().live.got, 0);
  run.feedEvent("press", { count: 1 });
  run.feedEvent("long_press", {});
  assert.deepEqual(run.view().live.hint, { got: "long_press", want: "double_press" });
  run.feedEvent("double_press", { count: 2 });
  run.feedEvent("long_press", {});
  assert.equal(run.results.press.status, "pass");
});

test("without multi press the double press is not asked for", () => {
  const { run } = rig({ ...OPTS, multi_press: false });
  goTo(run, "press");
  run.start();
  run.feedEvent("press", {});
  run.feedEvent("long_press", {});
  assert.equal(run.results.press.status, "pass");
});

test("flip needs the other face and back, and flip events when motion gestures are on", () => {
  const { run } = rig();
  goTo(run, "flip");
  run.start();
  run.feedStatus({ ...LIVE, face: "edge" });
  run.feedStatus({ ...LIVE, face: "pcb_up" });
  run.feedEvent("flip");
  assert.equal(run.view().live.stage, 2);
  run.feedStatus({ ...LIVE, face: "cap_up" });
  run.feedEvent("flip");
  assert.equal(run.phase, "done");
  // the second flip event arrived after the face settled: judged on what came in time
  assert.ok(["pass", "warn"].includes(run.results.flip.status));
});

test("flip asks to lay it flat first when it starts on its edge", () => {
  const { run, clock } = rig();
  run.feedStatus({ ...LIVE, face: "edge" });
  goTo(run, "flip");
  run.start();
  assert.equal(run.view().live.stage, 0);
  clock.advance(60_000);
  assert.equal(run.results.flip.reason, "not_flat");
});

test("drift is judged per minute while still", () => {
  const { run, clock } = rig();
  goTo(run, "drift");
  run.start();
  stream(run, clock, 30.1, 53, (s) => ({ yaw: s * (3 / 60) })); // 3 degrees a minute
  const r = run.results.drift;
  assert.equal(r.status, "pass");
  assert.ok(Math.abs(r.values.drift_deg_min - 3) < 0.3);
});

test("the report has numbers but no address or name", () => {
  const { run, clock } = rig();
  run.start();
  stream(run, clock, 10.1, 53);
  const text = run.report({ version: "0.3.0" });
  assert.match(text, /rest: pass/);
  assert.match(text, /integration 0\.3\.0/);
  assert.doesNotMatch(text, /[0-9A-F]{2}(:[0-9A-F]{2}){5}/i);
});

test("skip and redo", () => {
  const { run, clock } = rig();
  run.start();
  stream(run, clock, 10.1, 26);
  assert.equal(run.results.rest.status, "fail");
  run.redo();
  assert.equal(run.phase, "ready");
  assert.equal(run.results.rest, undefined);
  run.skip();
  assert.equal(run.results.rest.status, "skip");
  assert.equal(run.step.id, "flat");
});

test("the gesture steps follow the options", () => {
  const ids = (o) => new CheckRun({ options: o }).steps.map((s) => s.id);
  assert.ok(ids(OPTS).includes("tap") && ids(OPTS).includes("shake") && ids(OPTS).includes("throw"));
  const plain = ids({ ...OPTS, motion_gestures: false, shake: false });
  assert.ok(!plain.includes("tap") && !plain.includes("shake") && !plain.includes("throw"));
  // the options arriving with the first status rebuild the list
  let t = 0;
  const run = new CheckRun({ options: {}, now: () => t });
  assert.ok(!run.steps.some((s) => s.id === "shake"));
  run.feedStatus({ ...LIVE, options: OPTS });
  assert.ok(run.steps.some((s) => s.id === "shake"));
});

test("tap needs two taps, shake one; a step that sees none fails", () => {
  let { run, clock } = rig();
  goTo(run, "tap");
  run.start();
  run.feedEvent("tap");
  assert.equal(run.phase, "running");
  run.feedEvent("tap");
  assert.equal(run.results.tap.status, "pass");

  ({ run, clock } = rig());
  goTo(run, "shake");
  run.start();
  clock.advance(31_000);
  assert.equal(run.results.shake.reason, "not_detected");
  assert.equal(run.view().optional, false);
});

test("throw is optional and may bring a tap and a flip on landing", () => {
  const { run } = rig();
  goTo(run, "throw");
  assert.equal(run.view().optional, true);
  run.start();
  run.feedEvent("tap");
  run.feedEvent("throw");
  assert.equal(run.results.throw.status, "pass");
});

test("a gesture nobody asked for is reported as a false alarm", () => {
  let { run, clock } = rig();
  run.start(); // lying still
  let fired = false;
  stream(run, clock, 10.2, 53, (sec) => {
    if (sec > 5 && !fired) { fired = true; run.feedEvent("shake"); } // garbage read as a shake
    return {};
  });
  assert.equal(run.results.rest.status, "warn");
  assert.equal(run.results.rest.reason, "extra");
  assert.equal(run.results.rest.values.extra, "shake×1");

  ({ run, clock } = rig());
  goTo(run, "turn_cw");
  run.start();
  run.feedEvent("shake"); // a brisk turn read as a shake
  turn(run, clock, -180, 6);
  run.done();
  assert.equal(run.results.turn_cw.status, "warn");
  assert.match(run.report(), /turn_cw: warn \(extra\).*extra=shake×1/);
});

test("the receiver's address never reaches the report", () => {
  assert.equal(stripAddress("hm-ble-esp32 (D0:EF:76:33:5A:0E)"), "hm-ble-esp32");
  assert.equal(stripAddress("xiao-c5"), "xiao-c5");
  assert.equal(stripAddress(null), null);
  let t = 0;
  const run = new CheckRun({ options: OPTS, now: () => t });
  run.feedStatus({ ...LIVE, via: "hm-ble-esp32 (D0:EF:76:33:5A:0E)", options: OPTS });
  run.start();
  let frames = 0;
  for (let i = 0; i <= 310; i++) {
    run.feedMotion({ quaternion: FLAT_Q, euler: [0, 0, 0], gyro: [0, 0, 0], accel: [0, 0, -1], frames: Math.round(frames), rate: 52, ts: t / 1000 });
    t += 1000 / 30; frames += 53 / 30; run.tick();
  }
  assert.equal(run.results.rest.values.via, "hm-ble-esp32");
  assert.doesNotMatch(run.report(), /[0-9A-F]{2}(:[0-9A-F]{2}){5}/i);
});

test("the lean step is there only with the tilt option", () => {
  assert.ok(!new CheckRun({ options: OPTS }).steps.some((s) => s.id === "lean"));
  assert.ok(new CheckRun({ options: { ...OPTS, tilt: true } }).steps.some((s) => s.id === "lean"));
});

test("lean: right then left passes; repeats while held are fine", () => {
  const { run } = rig({ ...OPTS, tilt: true });
  goTo(run, "lean");
  run.start();
  run.feedEvent("rotate_cw", { steps: 1, source: "tilt" });
  run.feedEvent("rotate_cw", { steps: 1, source: "tilt" }); // held: a repeat
  assert.equal(run.view().live.count, 1);
  run.feedEvent("rotate_ccw", { steps: 1, source: "tilt" });
  assert.equal(run.results.lean.status, "pass");
  assert.equal(run.results.lean.values.repeats, 1);
});

test("lean: the other side first warns; a knob step during it is a false alarm", () => {
  const { run, clock } = rig({ ...OPTS, tilt: true });
  goTo(run, "lean");
  run.start();
  run.feedEvent("rotate_ccw", { steps: 1, source: "tilt" }); // held the wrong way round
  assert.equal(run.view().live.hint, "lean_wrong");
  run.feedEvent("rotate_cw", { steps: 1 }); // the knob, not the lean
  run.feedEvent("rotate_cw", { steps: 1, source: "tilt" });
  run.feedEvent("rotate_ccw", { steps: 1, source: "tilt" });
  const r = run.results.lean;
  assert.equal(r.status, "warn");
  assert.match(r.values.extra, /rotate_cw×1/);

  const again = rig({ ...OPTS, tilt: true });
  goTo(again.run, "lean");
  again.run.start();
  again.run.feedEvent("rotate_cw", { steps: 1, source: "tilt" });
  again.clock.advance(41_000);
  assert.equal(again.run.results.lean.reason, "lean_left");
  void clock;
});

test("lean follows invert_rotation", () => {
  const { run } = rig({ ...OPTS, tilt: true, invert_rotation: true });
  goTo(run, "lean");
  run.start();
  run.feedEvent("rotate_ccw", { steps: 1, source: "tilt" });
  run.feedEvent("rotate_cw", { steps: 1, source: "tilt" });
  assert.equal(run.results.lean.status, "pass");
});

test("the flat step is confirmed straight away, without a Start", () => {
  // 2026-11-23: the step said to press Done while only Start was on screen
  const { run } = rig();
  goTo(run, "flat");
  const v = run.view();
  assert.equal(v.phase, "ready");
  assert.equal(v.external, true); // the card shows Done in the ready phase for it
  run.complete({ status: "pass" }); // what the card does once the calibration succeeds
  assert.equal(run.results.flat.status, "pass");
  run.next();
  assert.notEqual(run.step.id, "flat");
  assert.equal(run.view().external, false); // the next step has its Start again
});

// ------------------------------------------------------------------ suggestions
const keys = (run) => run.suggestions().map((g) => `${g.key}=${g.value}`);

test("turns that came out the other way round both times suggest swapping the direction", () => {
  const { run, clock } = rig();
  goTo(run, "turn_cw");
  run.start();
  turn(run, clock, -180, 6, "rotate_ccw"); // the hand turned clockwise, the events said ccw
  run.done();
  run.next();
  run.start();
  turn(run, clock, 180, 6, "rotate_cw");
  run.done();
  assert.deepEqual(keys(run), ["invert_rotation=true"]);
  assert.match(run.report(), /suggest invert_rotation: false -> true/);
});

test("one turn the wrong way, or a hand that turned the wrong way, suggests nothing", () => {
  let { run, clock } = rig();
  goTo(run, "turn_cw");
  run.start();
  turn(run, clock, -180, 6, "rotate_ccw");
  run.done();
  run.next();
  run.start();
  turn(run, clock, 180, 6, "rotate_ccw"); // this one was right
  run.done();
  assert.deepEqual(keys(run), []);

  ({ run, clock } = rig());
  goTo(run, "turn_cw");
  run.start();
  turn(run, clock, 180, 6, "rotate_ccw"); // turned the wrong way: redo, not a setting
  run.done();
  assert.deepEqual(keys(run), []);
});

test("a lossy link suggests 26 Hz, unless it already runs at 26", () => {
  let { run, clock } = rig();
  run.start();
  stream(run, clock, 10.1, 26);
  assert.deepEqual(keys(run), ["sample_rate=26"]);

  ({ run, clock } = rig());
  run.start();
  stream(run, clock, 10.1, 13, () => ({ rate: 26 }));
  assert.equal(run.results.rest.reason, "loss");
  assert.deepEqual(keys(run), []);
});

test("a double press that came as two presses suggests a wider window", () => {
  const { run, clock } = rig({ ...OPTS, multi_press_window: 0.3 });
  goTo(run, "press");
  run.start();
  run.feedEvent("press", { count: 1 }); // the single press asked for first
  clock.advance(3000);
  run.feedEvent("press", { count: 1 }); // the double press, 0.45 s apart
  clock.advance(450);
  run.feedEvent("press", { count: 1 });
  clock.advance(61000); // the step times out without a double_press
  assert.equal(run.results.press.status, "fail");
  assert.equal(run.results.press.values.double_gap, 0.45);
  const [g] = run.suggestions();
  assert.equal(g.key, "multi_press_window");
  assert.equal(g.value, 0.5);
  assert.equal(g.from, 0.3);
});

test("a window that already fits, or presses far apart, suggest nothing", () => {
  const { run, clock } = rig({ ...OPTS, multi_press_window: 0.6 });
  goTo(run, "press");
  run.start();
  run.feedEvent("press", { count: 1 });
  clock.advance(400);
  run.feedEvent("press", { count: 1 });
  clock.advance(2000);
  run.feedEvent("press", { count: 1 });
  clock.advance(61000);
  assert.deepEqual(keys(run), []);
});

test("a shake or a lean that fires by itself twice suggests turning it off", () => {
  let { run, clock } = rig({ ...OPTS, tilt: true });
  goTo(run, "turn_cw");
  run.start();
  run.feedEvent("shake");
  run.feedEvent("rotate_cw", { steps: 1, source: "tilt" });
  turn(run, clock, -180, 6);
  run.done();
  run.next();
  run.start();
  run.feedEvent("shake");
  run.feedEvent("rotate_ccw", { steps: 1, source: "tilt" });
  turn(run, clock, 180, 6, "rotate_ccw");
  run.done();
  assert.deepEqual(keys(run), ["shake=false", "tilt=false"]);

  ({ run, clock } = rig());
  goTo(run, "turn_cw");
  run.start();
  run.feedEvent("shake"); // once is a remark, not a setting
  turn(run, clock, -180, 6);
  run.done();
  assert.deepEqual(keys(run), []);
});

test("a redone step forgets what fired during the first try", () => {
  const { run, clock } = rig();
  goTo(run, "turn_cw");
  run.start();
  run.feedEvent("shake");
  run.feedEvent("shake");
  turn(run, clock, -180, 6);
  run.done();
  run.redo();
  run.start();
  turn(run, clock, -180, 6);
  run.done();
  assert.deepEqual(keys(run), []);
});
