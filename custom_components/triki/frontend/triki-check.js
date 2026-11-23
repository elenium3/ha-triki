// The guided check of triki-card: the steps, what each one measures and how it is judged.
// Pure logic, no DOM: the card feeds it the token's websocket messages and draws `view()`.
// Tested with `node --test tests/js`.
//
// A step goes ready -> running -> done. "ready" waits for the user's Start (the
// instruction is on screen, nothing is measured yet). A link that drops while a step
// runs pauses the check; when the token is back the same step starts over, so a
// result is never made of two halves.

export const ODR_FACTOR = 1.02; // the token streams about 2 % faster than the rate asked for

const STILL_DPS = 8; // above this the token is being moved
const TILT_SIN = 0.26; // an edge raised by 15 degrees or more
const HOLD_S = 1.0;

// Two quarter turns of the knob (a wrist turns about 90 degrees comfortably; the hand
// lets go between them), judged against the angle the pose integrated.
export const TURN_TARGET_DEG = 180;
const TURN_MIN_DEG = 140;
const TURN_MAX_DEG = 250;

// Gestures a step does not ask for are false alarms worth reporting.
// Suggestions: a double press whose two presses came further apart than this was
// two presses; the window is not stretched past WINDOW_MAX_S (a single press
// waits that long); a gesture that fired by itself this often is better off.
const DOUBLE_GAP_MAX_S = 1.2;
const WINDOW_MAX_S = 0.8;
const LOSS_SUGGEST_PCT = 30;
const FALSE_ALARMS = 2;
const TILT = ["tilt_left", "tilt_right"];

// Picking the cap up and putting it back: every gesture that fires meanwhile is a
// false one. A handling is motion that ends with the cap still again.
export const HANDLE_WANT = 5;
const HANDLE_MOVE_DPS = 40;
const HANDLE_MOVE_G = 0.15;
const HANDLE_STILL_S = 0.8; // still this long: put down (or held still), one handling over
const HANDLE_MIN_S = 0.4; // shorter motion is a nudge, not a pick-up
const HANDLE_END_S = 1.5; // the last one put down and still this long: the step is over

// Shake: a try is a burst of fast rotation; a try with no shake event is a miss.
export const SHAKE_WANT = 3;
const SHAKE_TRY_DPS = 400;
const SHAKE_TRY_FRAMES = 3; // motion messages above SHAKE_TRY_DPS in one burst
const SHAKE_TRY_QUIET_S = 1.0; // below SHAKE_TRY_QUIET_DPS this long ends the burst
const SHAKE_TRY_QUIET_DPS = 100;
const SHAKE_TRIES_MAX = 6; // the step ends after this many tries even with misses

// Lean in the hand: right, left, three times.
export const LEAN_TARGETS = ["tilt_right", "tilt_left", "tilt_right", "tilt_left", "tilt_right", "tilt_left"];

// Sleep and wake: Home Assistant drops the link as after idling, the token dozes
// (~3 min, presses not seen) and sleeps, then a press must wake it.
const SLEEP_DOZE_MAX_S = 240; // longer means a press while dozing, or no sleep at all
const SLEEP_PRESS_WAIT_S = 3; // the wake press follows the wake within this
const GESTURES = ["shake", "tap", "throw", "flip", "rotate_cw", "rotate_ccw"];
const EXPECTED = {
  turn_cw: ["rotate_cw", "rotate_ccw"], turn_ccw: ["rotate_cw", "rotate_ccw"],
  flip: ["flip"], tap: ["tap"], shake: ["shake"], throw: ["throw", "tap", "flip"],
};

export function buildSteps(options = {}) {
  const steps = [
    { id: "rest", auto: 10 },
    { id: "flat", manual: true, external: true },
    { id: "tilt", timeout: 30 },
    { id: "turn_cw", manual: true, timeout: 60, dir: -1 },
    { id: "turn_ccw", manual: true, timeout: 60, dir: 1 },
    { id: "handle", timeout: 90 },
    { id: "lean", timeout: 60, need: "tilt" },
    { id: "press", timeout: 60 },
    { id: "flip", timeout: 60 },
    { id: "tap", timeout: 30, need: "motion_gestures" },
    { id: "shake", timeout: 60, need: "shake" },
    { id: "throw", timeout: 40, need: "motion_gestures", optional: true },
    { id: "drift", auto: 30 },
    { id: "sleep", timeout: 360, optional: true, link: true },
  ];
  return steps.filter((s) => !s.need || options[s.need]).map((s) => ({ ...s, options }));
}

const opposite = { cap_up: "pcb_up", pcb_up: "cap_up" };

// a scanner's name without the " (D0:EF:76:33:5A:0E)" HA appends: the report is shared
export const stripAddress = (name) =>
  name ? name.replace(/\s*\((?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\)\s*$/i, "") || null : null;

function rotate(q, v) {
  // q = [w, x, y, z] applied to vector v
  const [w, x, y, z] = q;
  const [vx, vy, vz] = v;
  const tx = 2 * (y * vz - z * vy), ty = 2 * (z * vx - x * vz), tz = 2 * (x * vy - y * vx);
  return [
    vx + w * tx + (y * tz - z * ty),
    vy + w * ty + (z * tx - x * tz),
    vz + w * tz + (x * ty - y * tx),
  ];
}

const unit = (v) => {
  const n = Math.hypot(...v);
  return n > 0 ? v.map((c) => c / n) : null;
};

export class CheckRun {
  constructor({ options = {}, now = () => Date.now() } = {}) {
    this.options = options;
    this.now = now;
    this.steps = buildSteps(options);
    this.index = 0;
    this.phase = "ready";
    this.results = {};
    this.status = null;
    this.motion = null;
    this._enter();
  }

  get step() { return this.steps[this.index]; }
  get finished() { return this.index >= this.steps.length; }

  // ------------------------------------------------------------------ input
  feedStatus(s) {
    const was = this._live(this.status);
    this.status = s;
    if (s?.options) {
      this.options = { ...this.options, ...s.options };
      if (this.index === 0 && this.phase === "ready" && !Object.keys(this.results).length) {
        this.steps = buildSteps(this.options);
      }
    }
    const live = this._live(s);
    if (this.step?.link && this.phase === "running") {
      this._onStatus(s); // the sleep step drops the link on purpose
      return;
    }
    if (!live && was && this.phase === "running") {
      this.phase = "paused";
      this._st = this._fresh();
    } else if (live && this.phase === "paused") {
      this.phase = "ready";
    }
    if (this.phase === "running") this._onStatus(s);
  }

  feedMotion(m) {
    this.motion = m;
    if (this.phase === "running") this._onMotion(m);
  }

  feedEvent(kind, data = {}) {
    if (this.phase === "running") this._onEvent(kind, data);
  }

  tick() {
    if (this.phase !== "running" || this.finished) return;
    const s = this.step, el = this._elapsed();
    if (s.id === "sleep" && this._st.woke && !this._st.done && this.now() / 1000 - this._st.wokeAt > SLEEP_PRESS_WAIT_S) {
      this._st.done = true; // woke, but no press came with it
      this._finish(this._judge());
    } else if (s.auto && el >= s.auto) this._finish(this._judge());
    else if (s.timeout && el >= s.timeout) this._finish(this._judge(true));
  }

  // ------------------------------------------------------------------ user
  start() {
    if (this.finished || this.phase === "running" || !this._live(this.status)) return false;
    this._st = this._fresh();
    this.phase = "running";
    if (this.step.id === "flip") this._flipProgress(this._st);
    return true;
  }

  done() {
    if (this.phase !== "running" || !this.step.manual || this.step.external) return;
    this._finish(this._judge());
  }

  // the card reports the outcome of an external step (the flat calibration)
  complete(result) {
    if (this.finished) return;
    this._finish(result);
  }

  redo() {
    if (this.phase === "done") {
      delete this.results[this.step.id];
    }
    this._enter();
  }

  skip() {
    if (this.finished) return;
    this.results[this.step.id] = { status: "skip" };
    this._next();
  }

  next() {
    if (this.phase === "done") this._next();
  }

  // ------------------------------------------------------------------ view
  view() {
    const s = this.step;
    if (!s) return { finished: true, results: this.results, summary: this.summary() };
    const st = this._st || {};
    const v = {
      id: s.id, index: this.index, total: this.steps.length, phase: this.phase,
      manual: !!s.manual, external: !!s.external, result: this.results[s.id] || null,
      elapsed: this.phase === "running" ? this._elapsed() : 0,
      // the sleep step's limit is only a backstop: the doze has its own countdown
      limit: s.id === "sleep" ? null : s.auto || s.timeout || null, live: {}, ghost: null,
      online: this._live(this.status),
    };
    if (s.id === "turn_cw" || s.id === "turn_ccw") {
      v.live = { steps: st.steps || 0, wrong: st.wrong || 0, angle: Math.round(st.angle || 0),
        expected: this._knobStep() ? Math.round(Math.abs(st.angle || 0) / this._knobStep()) : null };
      v.ghost = { type: "quarter", dir: s.dir };
    } else if (s.id === "tilt") {
      v.ghost = { type: "tilt" };
      v.live = { hint: st.hint || null };
    } else if (s.id === "flip") {
      v.ghost = { type: "flip" };
      v.live = { stage: st.stage || 0, face: this.status?.face || null };
    } else if (s.id === "press") {
      v.live = { want: this._pressTargets(), got: st.got || 0, hint: st.hint || null };
    } else if (s.id === "rest" || s.id === "drift") {
      v.live = { moved: !!st.moved };
    } else if (s.id === "tap" || s.id === "throw") {
      v.live = { count: st[s.id] || 0, want: s.id === "tap" ? 2 : 1 };
    } else if (s.id === "shake") {
      v.live = { count: st.shake || 0, want: SHAKE_WANT, tries: st.tries || 0 };
    } else if (s.id === "lean") {
      v.live = { count: st.got || 0, want: LEAN_TARGETS.length, hint: st.hint || null };
    } else if (s.id === "handle") {
      v.live = { count: st.count || 0, want: HANDLE_WANT };
    } else if (s.id === "sleep") {
      v.live = { stage: st.stage || 0, left: this.status?.doze_left_s ?? null };
    }
    v.optional = !!s.optional;
    v.extra = st.extra || null;
    return v;
  }

  summary() {
    const counts = { pass: 0, warn: 0, fail: 0, skip: 0 };
    for (const r of Object.values(this.results)) counts[r.status] = (counts[r.status] || 0) + 1;
    return counts;
  }

  // Settings the results point to, each with what it was. Only clear cases: the
  // owner applies them with one button, so a guess here would be a wrong setting.
  suggestions() {
    const o = this.options, r = this.results, out = [];
    const cw = r.turn_cw?.values, ccw = r.turn_ccw?.values;
    // turned the right way (by the model) both times, the events said the opposite
    const backwards = (v, dir) => v && Math.sign(v.angle) === dir && v.wrong >= 2 && v.wrong > (v.steps || 0);
    if (o.knob && backwards(cw, -1) && backwards(ccw, 1)) {
      out.push({ key: "invert_rotation", value: !o.invert_rotation, from: !!o.invert_rotation });
    }
    const rest = r.rest?.values;
    if (rest && rest.loss_pct > LOSS_SUGGEST_PCT && rest.asked > 26) {
      out.push({ key: "sample_rate", value: 26, from: rest.asked, loss: rest.loss_pct });
    }
    const gap = r.press?.values?.double_gap;
    const win = +(o.multi_press_window ?? 0.5);
    if (o.multi_press && gap != null) {
      // the gap between the two press events is the pause plus the second press
      const want = Math.min(WINDOW_MAX_S, Math.ceil((gap + 0.05) * 20) / 20);
      if (want > win) out.push({ key: "multi_press_window", value: want, from: win });
    }
    const extra = {};
    for (const res of Object.values(r)) {
      for (const [k, n] of Object.entries(res.extraCounts || {})) extra[k] = (extra[k] || 0) + n;
    }
    if (o.shake && (extra.shake || 0) >= FALSE_ALARMS) out.push({ key: "shake", value: false, from: true, count: extra.shake });
    const tilts = (extra.tilt_left || 0) + (extra.tilt_right || 0);
    if (o.tilt && tilts >= FALSE_ALARMS) out.push({ key: "tilt", value: false, from: true, count: tilts });
    return out;
  }

  // A plain-text report for a bug report: numbers only, no address or name.
  report(meta = {}) {
    const lines = ["Triki guided check"];
    if (meta.version) lines.push(`integration ${meta.version}`);
    if (this.status?.firmware) lines.push(`firmware ${this.status.firmware}`);
    const o = this.options;
    lines.push(`options knob=${!!o.knob} step=${o.knob_step} invert=${!!o.invert_rotation} motion=${!!o.motion_gestures} multi_press=${!!o.multi_press} tilt=${!!o.tilt}`);
    for (const s of this.steps) {
      const r = this.results[s.id];
      if (!r) continue;
      const vals = Object.entries(r.values || {}).map(([k, v]) => `${k}=${v}`).join(" ");
      lines.push(`${s.id}: ${r.status}${r.reason ? ` (${r.reason})` : ""}${vals ? ` ${vals}` : ""}`);
    }
    for (const g of this.suggestions()) lines.push(`suggest ${g.key}: ${g.from} -> ${g.value}`);
    return lines.join("\n");
  }

  // ------------------------------------------------------------------ internals
  _live(s) { return !!(s && s.connected && s.streaming); }
  _elapsed() { return (this.now() - (this._st?.t0 ?? this.now())) / 1000; }
  _knobStep() { return +this.options.knob_step || 30; }
  _fresh() { return { t0: this.now() }; }

  _enter() {
    this.phase = "ready";
    this._st = null;
  }

  _next() {
    this.index += 1;
    this._enter();
  }

  _finish(result) {
    // what fired unasked during this step, kept for suggestions (a redo replaces it)
    this.results[this.step.id] = { ...result, extraCounts: { ...(this._st?.extra || {}) } };
    this.phase = "done";
  }

  _pressTargets() {
    return this.options.multi_press ? ["press", "double_press", "long_press"] : ["press", "long_press"];
  }

  _onStatus(status) {
    const s = this.step, st = this._st;
    if (s.id === "flip") this._flipProgress(st);
    else if (s.id === "sleep") this._sleepProgress(st, status);
  }

  // stage 0: asked to drop the link; 1: dozing; 2: asleep, press now; 3: woke
  _sleepProgress(st, status) {
    const t = this.now() / 1000, r = status?.readiness;
    const stage = st.stage || 0;
    if (stage === 0 && !status?.connected) { st.stage = 1; st.dropAt = t; }
    else if (stage === 1 && status?.connected) {
      st.stage = 3; // back without having slept: it connected while dozing
      this._finish(this._judge());
    } else if (stage === 1 && r === "asleep") { st.stage = 2; st.sleptAt = t; }
    else if (stage === 2 && status?.connected) { st.stage = 3; st.wokeAt = t; }
  }

  _onMotion(m) {
    const s = this.step, st = this._st;
    const gyro = Math.hypot(...(m.gyro || [0, 0, 0]));
    if (s.id === "rest" || s.id === "drift") {
      if (!st.first) st.first = m;
      st.last = m;
      st.n = (st.n || 0) + 1;
      st.sq = (st.sq || 0) + gyro * gyro;
      st.max = Math.max(st.max || 0, gyro);
      if (gyro > STILL_DPS) st.moved = true;
      st.yaw = this._unwrap(st, m.euler[2]);
    } else if (s.id === "tilt") {
      const up = unit(m.accel || [0, 0, 1]);
      const model = rotate(m.quaternion, [0, -1, 0])[2]; // the dot edge's height in the model
      const sensor = up ? -up[1] : 0; // the dot edge (sensor -y) against gravity
      const t = this.now() / 1000;
      if (sensor > TILT_SIN) {
        st.since ??= t;
        st.model = model;
        st.hint = model > TILT_SIN ? null : "model";
        if (t - st.since >= HOLD_S) this._finish(this._judge());
      } else {
        st.since = null;
        st.hint = up && up[1] > TILT_SIN ? "other_edge" : null;
      }
    } else if (s.id === "turn_cw" || s.id === "turn_ccw") {
      st.angle = this._unwrap(st, m.euler[2]);
    } else if (s.id === "handle") {
      this._handleMotion(st, m, gyro);
    } else if (s.id === "shake") {
      this._shakeMotion(st, gyro);
    }
  }

  _handleMotion(st, m, gyro) {
    const t = this.now() / 1000;
    const a = Math.hypot(...(m.accel || [0, 0, 1]));
    const moving = gyro > HANDLE_MOVE_DPS || Math.abs(a - 1) > HANDLE_MOVE_G;
    if (moving) {
      st.moveFrom ??= t;
      st.lastMove = t;
    } else if (st.moveFrom != null && t - st.lastMove >= HANDLE_STILL_S) {
      if (st.lastMove - st.moveFrom >= HANDLE_MIN_S) st.count = (st.count || 0) + 1;
      st.moveFrom = null;
    }
    if ((st.count || 0) >= HANDLE_WANT && st.moveFrom == null && t - (st.lastMove ?? t) >= HANDLE_END_S) {
      this._finish(this._judge());
    }
  }

  _shakeMotion(st, gyro) {
    const t = this.now() / 1000;
    if (gyro > SHAKE_TRY_DPS) {
      st.fast = (st.fast || 0) + 1;
      st.burstLast = t;
      if (st.fast === SHAKE_TRY_FRAMES) {
        st.tries = (st.tries || 0) + 1;
        st.shakesAtTry = st.shake || 0;
      }
    } else if (gyro > SHAKE_TRY_QUIET_DPS) {
      st.burstLast = t;
    } else if (st.fast && t - st.burstLast >= SHAKE_TRY_QUIET_S) {
      st.fast = 0; // the burst is over
      if ((st.tries || 0) >= SHAKE_TRIES_MAX || (st.shake || 0) >= SHAKE_WANT) this._finish(this._judge());
    }
  }

  _unwrap(st, yaw) {
    if (st.prevYaw == null) { st.prevYaw = yaw; st.acc = 0; return 0; }
    let d = yaw - st.prevYaw;
    if (d > 180) d -= 360;
    if (d < -180) d += 360;
    st.prevYaw = yaw;
    st.acc += d;
    return st.acc;
  }

  _onEvent(kind, data) {
    const s = this.step, st = this._st;
    if (s.id === "lean" && TILT.includes(kind)) {
      this._leanEvent(kind);
      return;
    }
    if (TILT.includes(kind)) {
      // a lean step outside the lean step: tilt in the hand fired by itself
      st.extra ??= {};
      st.extra[kind] = (st.extra[kind] || 0) + 1;
      return;
    }
    if (GESTURES.includes(kind) && !(EXPECTED[s.id] || []).includes(kind)) {
      st.extra ??= {};
      st.extra[kind] = (st.extra[kind] || 0) + 1;
      return;
    }
    if (s.id === "tap" || s.id === "throw") {
      if (kind !== s.id) return;
      st[kind] = (st[kind] || 0) + 1;
      if (st[kind] >= (s.id === "tap" ? 2 : 1)) this._finish(this._judge());
      return;
    }
    if (s.id === "shake") {
      // judged when the burst is over: the try that brought it is counted first
      if (kind === "shake") st.shake = (st.shake || 0) + 1;
      return;
    }
    if (s.id === "sleep") {
      if ((st.stage || 0) < 2 || st.done) return;
      if (kind === "press") st.pressed = true;
      else if (kind === "wake") { st.woke = true; st.wokeAt ??= this.now() / 1000; }
      else return;
      // with "wake as press" the press follows the wake at once: wait for it
      if (st.pressed || !this.options.wake_as_press) {
        st.done = true;
        this._finish(this._judge());
      }
      return;
    }
    if (s.id === "turn_cw" || s.id === "turn_ccw") {
      if (kind !== "rotate_cw" && kind !== "rotate_ccw") return;
      // invert_rotation swaps the event names, not the hand's direction
      const cwEvent = this.options.invert_rotation ? "rotate_ccw" : "rotate_cw";
      const want = s.dir < 0 ? cwEvent : cwEvent === "rotate_cw" ? "rotate_ccw" : "rotate_cw";
      const n = data.steps || 1;
      if (kind === want) st.steps = (st.steps || 0) + n;
      else st.wrong = (st.wrong || 0) + n;
    } else if (s.id === "press") {
      const targets = this._pressTargets();
      if (!["press", "double_press", "triple_press", "long_press"].includes(kind)) return;
      if (data.source === "wake") return; // the press that woke it, not the one asked for
      const want = targets[st.got || 0];
      if (want === "double_press" && kind === "press") {
        // a double press that came as two: how far apart, to fit the window
        const t = this.now() / 1000;
        if (st.lastPress != null && t - st.lastPress <= DOUBLE_GAP_MAX_S) {
          st.doubleGap = Math.min(st.doubleGap ?? Infinity, t - st.lastPress);
        }
        st.lastPress = t;
      }
      if (kind === want) {
        st.got = (st.got || 0) + 1;
        st.hint = null;
        if (st.got >= targets.length) this._finish(this._judge());
      } else {
        st.hint = { got: kind, want };
      }
    } else if (s.id === "flip" && kind === "flip") {
      st.flips = (st.flips || 0) + 1;
    }
  }

  // Right, then left. A lean held on one side repeats its step: those are counted,
  // not held against it. A step for the side not asked for means the cap is held
  // the other way round, or the sides are wired backwards.
  _leanTargets() { return LEAN_TARGETS; }

  _leanEvent(kind) {
    const st = this._st, targets = this._leanTargets(), got = st.got || 0;
    if (kind === targets[got]) {
      st.got = got + 1;
      st.hint = null;
      if (st.got >= targets.length) this._finish(this._judge());
    } else if (got > 0 && kind === targets[got - 1]) {
      st.repeats = (st.repeats || 0) + 1;
    } else {
      st.wrong = (st.wrong || 0) + 1;
      st.hint = "lean_wrong";
    }
  }

  _flipProgress(st) {
    const face = this.status?.face;
    if (st.start == null) st.start = opposite[face] ? face : null;
    if (st.start == null) { st.stage = 0; return; } // lay it flat first
    if ((st.stage || 0) <= 1 && face === opposite[st.start]) st.stage = 2;
    else if (st.stage === 2 && face === st.start) {
      st.stage = 3;
      this._finish(this._judge());
    } else if (!st.stage) st.stage = 1;
  }

  _judge(timedOut = false) {
    const r = this._judgeStep(timedOut);
    const extra = this._st?.extra;
    if (extra && r.status !== "fail" && r.status !== "skip") {
      // something fired that this step did not ask for: a false alarm
      const list = Object.entries(extra).map(([k, n]) => `${k}×${n}`).join(",");
      return { ...r, status: "warn", reason: r.reason || "extra", values: { ...(r.values || {}), extra: list } };
    }
    if (extra && r.values) r.values.extra = Object.entries(extra).map(([k, n]) => `${k}×${n}`).join(",");
    return r;
  }

  _judgeStep(timedOut = false) {
    const s = this.step, st = this._st || {};
    switch (s.id) {
      case "shake": {
        const n = st.shake || 0;
        // a burst too short to count as a try may still have shaken
        const tries = Math.max(st.tries || 0, n);
        const values = { count: n, tries };
        if (!n) return { status: "fail", reason: "not_detected", values };
        if (n < tries) return { status: "warn", reason: "shake_missed", values };
        return { status: "pass", values };
      }
      case "handle": {
        const values = { count: st.count || 0 };
        if (timedOut && (st.count || 0) < HANDLE_WANT) return { status: "fail", reason: "handle_few", values };
        return { status: "pass", values };
      }
      case "sleep": return this._judgeSleep(st, timedOut);
      case "tap":
      case "throw": {
        const n = st[s.id] || 0, want = s.id === "tap" ? 2 : 1;
        return n >= want ? { status: "pass", values: { count: n } }
          : { status: "fail", reason: "not_detected", values: { count: n } };
      }
      case "lean": {
        const got = st.got || 0;
        const values = { repeats: st.repeats || 0, wrong: st.wrong || 0 };
        values.count = got;
        if (got < LEAN_TARGETS.length) {
          const next = LEAN_TARGETS[got];
          return { status: "fail", reason: st.wrong ? "lean_wrong" : next === "tilt_left" ? "lean_left" : "lean_right", values };
        }
        return st.wrong ? { status: "warn", reason: "lean_wrong", values } : { status: "pass", values };
      }
      case "rest": return this._judgeRest(st);
      case "tilt":
        if (timedOut) {
          return { status: "fail", reason: st.hint === "model" ? "model_wrong" : "not_raised" };
        }
        return st.hint === "model"
          ? { status: "fail", reason: "model_wrong" }
          : { status: "pass", values: { model_rise: +(st.model ?? 0).toFixed(2) } };
      case "turn_cw":
      case "turn_ccw": return this._judgeTurn(s, st);
      case "press": {
        const targets = this._pressTargets();
        const got = st.got || 0;
        const values = { missing: targets.slice(got).join(",") };
        if (st.doubleGap != null) values.double_gap = +st.doubleGap.toFixed(2);
        return got >= targets.length
          ? { status: "pass" }
          : { status: "fail", reason: "missing", values };
      }
      case "flip": {
        if ((st.stage || 0) < 3) return { status: "fail", reason: st.start == null ? "not_flat" : "not_flipped" };
        if (this.options.motion_gestures && (st.flips || 0) < 2) {
          return { status: "warn", reason: "flip_events", values: { flips: st.flips || 0 } };
        }
        return { status: "pass", values: { flips: st.flips || 0 } };
      }
      case "drift": return this._judgeDrift(st);
      default: return { status: "pass" };
    }
  }

  _judgeRest(st) {
    if (!st.first || st.n < 5) return { status: "fail", reason: "no_frames" };
    if (st.moved) return { status: "fail", reason: "moved" };
    const dt = st.last.ts - st.first.ts;
    const frames = st.last.frames - st.first.frames;
    const rate = st.last.rate || this.status?.rate || 52;
    const got = dt > 0 ? frames / dt : 0;
    const loss = Math.max(0, 1 - got / (rate * ODR_FACTOR));
    const noise = Math.sqrt(st.sq / st.n);
    const values = { rate: +got.toFixed(1), asked: rate, loss_pct: Math.round(loss * 100),
      noise_dps: +noise.toFixed(1), via: stripAddress(this.status?.via), rssi: this.status?.rssi ?? null };
    if (loss > 0.3) return { status: "fail", reason: "loss", values };
    if (loss > 0.1 || noise > 3) return { status: "warn", reason: loss > 0.1 ? "loss" : "noise", values };
    return { status: "pass", values };
  }

  _judgeTurn(s, st) {
    const angle = st.angle || 0;
    const values = { angle: Math.round(angle), steps: st.steps || 0, wrong: st.wrong || 0 };
    if (Math.abs(angle) < TURN_MIN_DEG) return { status: "fail", reason: "short", values };
    if (Math.sign(angle) !== s.dir) return { status: "fail", reason: "direction", values };
    if (Math.abs(angle) > TURN_MAX_DEG) return { status: "fail", reason: "long", values };
    if (!this.options.knob) return { status: "skip", reason: "knob_off", values };
    const expected = Math.abs(angle) / this._knobStep();
    values.expected = +expected.toFixed(1);
    const off = Math.abs((st.steps || 0) - expected);
    if ((st.wrong || 0) === 0 && off <= 1) return { status: "pass", values };
    if ((st.wrong || 0) <= 1 && off <= 2) return { status: "warn", reason: "steps", values };
    return { status: "fail", reason: (st.wrong || 0) > 1 ? "wrong_way" : "steps", values };
  }

  _judgeSleep(st, timedOut) {
    const stage = st.stage || 0;
    const values = {};
    if (st.dropAt != null && st.sleptAt != null) values.doze_s = Math.round(st.sleptAt - st.dropAt);
    if (stage === 3 && st.sleptAt == null) return { status: "fail", reason: "woke_dozing", values };
    if (stage <= 1) {
      // still dozing at the time limit: a press meanwhile starts the doze over
      return { status: "fail", reason: stage === 0 ? "no_drop" : "no_sleep", values };
    }
    if (timedOut || !st.done) return { status: "fail", reason: "no_wake", values };
    if (values.doze_s > SLEEP_DOZE_MAX_S) return { status: "warn", reason: "long_doze", values };
    if (!st.pressed && this.options.wake_as_press) return { status: "warn", reason: "no_wake_press", values };
    return { status: "pass", values };
  }

  _judgeDrift(st) {
    if (!st.first || st.n < 5) return { status: "fail", reason: "no_frames" };
    if (st.moved) return { status: "fail", reason: "moved" };
    const secs = st.last.ts - st.first.ts || 1;
    const perMin = (Math.abs(st.yaw || 0) * 60) / secs;
    const values = { drift_deg_min: +perMin.toFixed(1) };
    if (perMin > 12) return { status: "fail", reason: "drift", values };
    if (perMin > 4) return { status: "warn", reason: "drift", values };
    return { status: "pass", values };
  }
}
