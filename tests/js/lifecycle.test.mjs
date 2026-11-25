// The card's life cycle: subscribing, retrying, rebuilding, being removed.
// A minimal DOM stands in for the browser; the real module is imported.
import { test, mock, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";

class FakeEl {
  constructor(id = "") {
    this.id = id; this._html = ""; this.hidden = false; this.style = {}; this.dataset = {};
    this.classList = { add() {}, remove() {}, toggle() {}, contains() { return false; } };
  }
  set innerHTML(v) { this._html = v; } get innerHTML() { return this._html; }
  set textContent(v) { this._text = v; } get textContent() { return this._text; }
  addEventListener() {} toggleAttribute() {} setAttribute() {}
  querySelectorAll() { return []; } querySelector() { return null; }
}
class FakeShadow {
  constructor() { this._els = new Map(); this.card = new FakeEl("ha-card"); this.builds = 0; }
  set innerHTML(v) { this._html = v; this._els = new Map(); this.card = new FakeEl("ha-card"); this.builds++; }
  get innerHTML() { return this._html; }
  getElementById(id) { if (!this._els.has(id)) this._els.set(id, new FakeEl(id)); return this._els.get(id); }
  querySelector(sel) { return sel === "ha-card" ? this.card : null; }
  querySelectorAll() { return []; }
}
const observers = { io: [] };
globalThis.HTMLElement = class {
  attachShadow() { this.shadowRoot = new FakeShadow(); return this.shadowRoot; }
  get isConnected() { return !!this._conn; }
};
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
globalThis.IntersectionObserver = class {
  constructor() { this.n = 0; observers.io.push(this); }
  observe() { this.n++; } disconnect() { this.n = 0; }
};
globalThis.cancelAnimationFrame = () => {};
const defs = {};
globalThis.customElements = { get: (n) => defs[n], define: (n, c) => { defs[n] = c; } };
globalThis.window = globalThis;
globalThis.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
console.warn = () => {}; // "subscribe failed" is expected here

await import("../../custom_components/triki/frontend/triki-card.js");
const Card = defs["triki-card"];
const flush = async () => { for (let i = 0; i < 5; i++) await new Promise((r) => setImmediate(r)); };

function makeHass({ devices = () => [{ device_id: "a", name: "A" }], subscribe = async () => {} } = {}) {
  const log = { devices: 0, subscribe: [], unsub: [] };
  const connection = {
    async sendMessagePromise(m) {
      if (m.type === "triki/devices") { log.devices++; return devices(log.devices); }
      return null;
    },
    async subscribeMessage(cb, m) {
      log.subscribe.push(m.device_id);
      await subscribe(m.device_id, log.subscribe.length, cb);
      return () => { log.unsub.push(m.device_id); return Promise.resolve(); };
    },
  };
  return { log, hass: () => ({ connection, language: "en", user: { is_admin: true }, entities: {} }) };
}

function card(config = {}) {
  const c = new Card();
  c._conn = true;
  c.setConfig(config);
  return c;
}

beforeEach(() => mock.timers.enable({ apis: ["setTimeout", "setInterval"] }));
afterEach(() => mock.timers.reset());

test("a cap that shows up after Home Assistant started is picked up and the card rebuilt", async () => {
  const { log, hass } = makeHass({ devices: (n) => (n === 1 ? [] : [{ device_id: "a", name: "A" }]) });
  const c = card();
  c.hass = hass(); await flush();
  assert.match(c.shadowRoot.card.innerHTML, /No Triki cap found/);
  mock.timers.tick(2000); await flush();
  assert.ok(c._unsub, "subscribed on the retry");
  assert.equal(log.subscribe.length, 1);
  assert.doesNotMatch(c.shadowRoot.card.innerHTML, /No Triki cap found/);
  assert.equal(c._el.card, c.shadowRoot.card, "the element map points at the shown markup");
});

test("hass updates do not resend a failed subscribe; a backing-off timer does", async () => {
  const { log, hass } = makeHass({ devices: () => [] });
  const c = card();
  for (let i = 0; i < 50; i++) { c.hass = hass(); await flush(); }
  assert.equal(log.devices, 1);
  mock.timers.tick(2000); await flush();
  assert.equal(log.devices, 2);
  mock.timers.tick(2000); await flush();
  assert.equal(log.devices, 2, "the second wait is longer");
  mock.timers.tick(2000); await flush();
  assert.equal(log.devices, 3);
});

test("one cap failing drops the others' subscriptions instead of piling them up", async () => {
  const { log, hass } = makeHass({
    devices: () => [{ device_id: "a" }, { device_id: "b" }],
    subscribe: async (id) => { if (id === "b") throw { code: "not_found" }; },
  });
  const c = card();
  for (let i = 0; i < 5; i++) { c.hass = hass(); await flush(); }
  assert.deepEqual(log.subscribe, ["a", "b"]);
  assert.deepEqual(log.unsub, ["a"]);
  assert.equal(c._unsub, undefined);
});

test("a status that comes before the subscribe call returns is shown, not thrown on", async () => {
  // Home Assistant sends the result and the first status in one frame, so the
  // callback runs before the code that awaits the subscription does
  const thrown = [];
  const status = (id) => ({ type: "status", device_id: id, name: id, connected: id === "b", streaming: id === "b" });
  const { hass } = makeHass({
    devices: () => [{ device_id: "a" }, { device_id: "b" }],
    subscribe: async (id, _n, cb) => { try { cb(status(id)); } catch (err) { thrown.push(err); } },
  });
  const c = card();
  c.hass = hass(); await flush();
  assert.deepEqual(thrown, []);
  assert.ok(c._unsub, "subscribed");
  assert.equal(c._statuses.a.name, "a");
  assert.equal(c._statuses.b.connected, true);
  assert.equal(c._deviceId, "b", "the early status of the awake cap is followed");
});

test("an error while handling a message does not reach Home Assistant's socket loop", async () => {
  // its loop handles a frame of several messages; an exception from one callback
  // would drop the rest of the frame
  let push;
  const { hass } = makeHass({ subscribe: async (_id, _n, cb) => { push = cb; } });
  const c = card();
  c.hass = hass(); await flush();
  const logged = [];
  const error = console.error;
  console.error = (...a) => logged.push(a);
  c._showStatus = () => { throw new Error("boom"); };
  try {
    assert.doesNotThrow(() => push({ type: "status", device_id: "a", connected: true, streaming: true }));
  } finally {
    console.error = error;
  }
  assert.equal(logged.length, 1);
  assert.match(String(logged[0][1]), /boom/);
});

test("early messages of a subscribe that was dropped meanwhile are ignored", async () => {
  let early;
  const { hass } = makeHass({ subscribe: async (_id, _n, cb) => { early = cb; } });
  const c = card();
  c.hass = hass(); await flush();
  c.disconnectedCallback();
  assert.doesNotThrow(() => early({ type: "status", device_id: "a", connected: true, streaming: true }));
  assert.equal(c._statuses.a, undefined);
});

test("a card removed while subscribing drops the subscription it gets", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const { log, hass } = makeHass({ subscribe: () => gate });
  const c = card();
  c.hass = hass(); await flush();
  c._conn = false; c.disconnectedCallback();
  release(); await flush();
  assert.equal(c._unsub ?? null, null);
  assert.deepEqual(log.unsub, ["a"]);
});

test("another device_id in the config follows the new cap", async () => {
  const { log, hass } = makeHass();
  const c = card({ device_id: "a" });
  c.hass = hass(); await flush();
  c.setConfig({ device_id: "b" }); await flush();
  assert.deepEqual(log.subscribe, ["a", "b"]);
  assert.deepEqual(log.unsub, ["a"]);
  assert.equal(c._deviceId, "b");
});

test("a rebuild gives the WebGL context back and stops the old observer", async () => {
  const { hass } = makeHass();
  const c = card();
  c.hass = hass(); await flush();
  const calls = [];
  c._scene = {};
  c._renderer = { dispose: () => calls.push("dispose"), forceContextLoss: () => calls.push("lost") };
  const io = c._io;
  c.setConfig({ title: "x" });
  assert.deepEqual(calls, ["dispose", "lost"]);
  assert.equal(c._renderer, null);
  assert.equal(c._scene, null, "the next frame builds a scene on the new canvas");
  assert.equal(io.n, 0);
});

test("a removed card gives its WebGL context back, a moved one keeps it", async () => {
  const { hass } = makeHass();
  const c = card();
  c.hass = hass(); await flush();
  let lost = 0;
  const renderer = { dispose() {}, forceContextLoss: () => { lost++; } };
  c._scene = {}; c._renderer = renderer;
  c._conn = false; c.disconnectedCallback(); c._conn = true; c.connectedCallback();
  mock.timers.tick(1000);
  assert.equal(lost, 0, "moved in edit mode");
  c._conn = false; c.disconnectedCallback();
  mock.timers.tick(1000);
  assert.equal(lost, 1);
});

test("the title is text, not markup", async () => {
  const c = card({ title: "R&D <b>bench</b>" });
  c.hass = makeHass().hass(); await flush();
  assert.equal(c._el.name.textContent, "R&D <b>bench</b>");
  assert.doesNotMatch(c.shadowRoot.innerHTML, /<b>bench/);
});

test("a reload of the integration does not blank the card while the cap comes back", async () => {
  const { hass } = makeHass({ subscribe: async (_id, n) => { if (n === 2) throw { code: "not_found" }; } });
  const c = card();
  c.hass = hass(); await flush();
  const shown = c.shadowRoot.card;
  c._onMessage("a", { type: "reload" });
  mock.timers.tick(2000); await flush(); // the entry is still setting up
  assert.equal(c.shadowRoot.card, shown);
  assert.doesNotMatch(shown.innerHTML, /No Triki cap found/);
  mock.timers.tick(4000); await flush();
  assert.ok(c._unsub, "back once the entry is up");
});

test("a check closed while it starts stops what it started", async () => {
  let release;
  const gate = new Promise((r) => { release = r; });
  const sent = [];
  const { hass } = makeHass();
  const c = card();
  c.hass = hass(); await flush();
  c._send = async (m) => { sent.push(`${m.action}:${m.device_id}`); if (m.action === "start") await gate; };
  const open = c._checkOpen();
  c._checkClose(); // the card was removed meanwhile
  release(); await open; await flush();
  assert.deepEqual(sent, ["start:a", "stop:a"]);
});
