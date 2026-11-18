// node --test tests/js
import { test } from "node:test";
import assert from "node:assert/strict";

import { CheckRun } from "../../custom_components/triki/frontend/triki-check.js";

const LIVE = { connected: true, streaming: true, rate: 52, face: "cap_up", via: "hm-ble-esp32", rssi: -60 };
const OPTS = { knob: true, knob_step: 30, invert_rotation: false, motion_gestures: true, multi_press: true };
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

function turn(run, clock, degrees, events, kind = "rotate_cw") {
  const secs = 12;
  let fired = 0;
  stream(run, clock, secs, 53, (s) => {
    const due = Math.floor((s / secs) * events);
    while (fired < due) { run.feedEvent(kind, { steps: 1, degrees: 30 }); fired++; }
    return { yaw: ((((s / secs) * degrees) % 360) + 540) % 360 - 180, gyro: [0, 0, degrees / secs] };
  });
  while (fired < events) { run.feedEvent(kind, { steps: 1, degrees: 30 }); fired++; }
}

test("a clockwise turn with 12 steps passes", () => {
  const { run, clock } = rig();
  goTo(run, "turn_cw");
  run.start();
  turn(run, clock, -360, 12);
  assert.equal(run.view().live.steps, 12);
  run.done();
  const r = run.results.turn_cw;
  assert.equal(r.status, "pass");
  assert.equal(r.values.angle, -360);
});

test("a turn that lost steps fails, a short or reversed one is redone", () => {
  let { run, clock } = rig();
  goTo(run, "turn_cw");
  run.start();
  turn(run, clock, -360, 8);
  run.done();
  assert.equal(run.results.turn_cw.status, "fail");
  assert.equal(run.results.turn_cw.reason, "steps");

  ({ run, clock } = rig());
  goTo(run, "turn_cw");
  run.start();
  turn(run, clock, -200, 6);
  run.done();
  assert.equal(run.results.turn_cw.reason, "short");

  ({ run, clock } = rig());
  goTo(run, "turn_cw");
  run.start();
  turn(run, clock, 360, 12, "rotate_ccw");
  run.done();
  assert.equal(run.results.turn_cw.reason, "direction");
});

test("inverted rotation expects the other event name, the same hand direction", () => {
  const { run, clock } = rig({ ...OPTS, invert_rotation: true });
  goTo(run, "turn_cw");
  run.start();
  turn(run, clock, -360, 12, "rotate_ccw");
  run.done();
  assert.equal(run.results.turn_cw.status, "pass");
});

test("a 45 degree knob step expects 8 steps; the knob off measures the turn only", () => {
  let { run, clock } = rig({ ...OPTS, knob_step: 45 });
  goTo(run, "turn_ccw");
  run.start();
  turn(run, clock, 360, 8, "rotate_ccw");
  run.done();
  assert.equal(run.results.turn_ccw.status, "pass");

  ({ run, clock } = rig({ ...OPTS, knob: false }));
  goTo(run, "turn_ccw");
  run.start();
  turn(run, clock, 360, 0);
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
