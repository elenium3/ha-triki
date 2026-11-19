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
    { id: "lean", timeout: 40, need: "tilt" },
    { id: "press", timeout: 60 },
    { id: "flip", timeout: 60 },
    { id: "tap", timeout: 30, need: "motion_gestures" },
    { id: "shake", timeout: 30, need: "shake" },
    { id: "throw", timeout: 40, need: "motion_gestures", optional: true },
    { id: "drift", auto: 30 },
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
    if (s.auto && el >= s.auto) this._finish(this._judge());
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
      manual: !!s.manual, result: this.results[s.id] || null,
      elapsed: this.phase === "running" ? this._elapsed() : 0,
      limit: s.auto || s.timeout || null, live: {}, ghost: null,
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
    } else if (s.id === "tap" || s.id === "shake" || s.id === "throw") {
      v.live = { count: st[s.id] || 0, want: s.id === "tap" ? 2 : 1 };
    } else if (s.id === "lean") {
      v.live = { count: st.got || 0, want: 2, hint: st.hint || null };
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
    this.results[this.step.id] = result;
    this.phase = "done";
  }

  _pressTargets() {
    return this.options.multi_press ? ["press", "double_press", "long_press"] : ["press", "long_press"];
  }

  _onStatus(_s) {
    const s = this.step, st = this._st;
    if (s.id === "flip") this._flipProgress(st);
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
    if (s.id === "lean" && data.source === "tilt") {
      this._leanEvent(kind);
      return;
    }
    if (GESTURES.includes(kind) && !(EXPECTED[s.id] || []).includes(kind)) {
      st.extra ??= {};
      st.extra[kind] = (st.extra[kind] || 0) + 1;
      return;
    }
    if (s.id === "tap" || s.id === "shake" || s.id === "throw") {
      if (kind !== s.id) return;
      st[kind] = (st[kind] || 0) + 1;
      if (st[kind] >= (s.id === "tap" ? 2 : 1)) this._finish(this._judge());
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
  _leanTargets() {
    const cw = this.options.invert_rotation ? "rotate_ccw" : "rotate_cw";
    return [cw, cw === "rotate_cw" ? "rotate_ccw" : "rotate_cw"];
  }

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
      case "tap":
      case "shake":
      case "throw": {
        const n = st[s.id] || 0, want = s.id === "tap" ? 2 : 1;
        return n >= want ? { status: "pass", values: { count: n } }
          : { status: "fail", reason: "not_detected", values: { count: n } };
      }
      case "lean": {
        const got = st.got || 0;
        const values = { repeats: st.repeats || 0, wrong: st.wrong || 0 };
        if (got < 2) return { status: "fail", reason: st.wrong ? "lean_wrong" : got ? "lean_left" : "lean_right", values };
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
        return got >= targets.length
          ? { status: "pass" }
          : { status: "fail", reason: "missing", values: { missing: targets.slice(got).join(",") } };
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
