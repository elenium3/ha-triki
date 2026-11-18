// custom:triki-card: a live 3D view of a Żabka Triki token, part of the Triki integration.
//
// Data: the integration's websocket command triki/subscribe sends `status` (link, battery,
// RSSI, rate), `motion` (pose quaternion in the sensor frame, roll/pitch/yaw, the last gyro
// and accelerometer reading) at up to 30 per second while the token streams, and `event`
// (gestures). Nothing of this goes through entity states.
//
// Frames: the sensor has +z out of the top (logo side), +x to the left of the logo and -y
// towards the top of the logo (docs/protocol.md). The glTF model is Y-up with the logo on +Y
// and its top towards -Z, so a sensor vector (x, y, z) is (-x, z, y) in the model frame and a
// sensor quaternion (w, x, y, z) becomes (w, -x, z, y).
//
// 3D model: Flopsstuff/triki (MIT), textures resized to 1024 px WebP. Renderer: three.js (MIT),
// bundled as triki-three.js. Both are loaded only when a card is on screen.

const BASE = new URL(".", import.meta.url).href;
const VERSION = new URL(import.meta.url).searchParams.get("v") || "";
const asset = (name) => `${BASE}${name}${VERSION ? `?v=${VERSION}` : ""}`;

const STRINGS = {
  en: {
    asleep: "Asleep", connected: "Connected", streaming: "Live", unresponsive: "Not responding",
    wake: "Press or shake the cap to wake it", gyro: "Gyroscope, °/s", accel: "Accelerometer, g",
    roll: "Roll", pitch: "Pitch", yaw: "Yaw", reset: "Zero heading", led: "LED",
    button: "Button", rate: "Hz", history: "Last 10 s", nodevice: "No Triki token found",
    gestures: {
      single_press: "Press", double_press: "Double press", triple_press: "Triple press",
      long_press: "Long press", tap: "Tap", double_tap: "Double tap", shake: "Shake",
      flip: "Flip", rotate_cw: "Knob ↻", rotate_ccw: "Knob ↺", wake: "Woke up", motion: "Motion",
    },
  },
  ru: {
    asleep: "Спит", connected: "Подключён", streaming: "Онлайн", unresponsive: "Не отвечает",
    wake: "Нажми или встряхни крышку, чтобы разбудить", gyro: "Гироскоп, °/с",
    accel: "Акселерометр, g", roll: "Крен", pitch: "Тангаж", yaw: "Курс", reset: "Обнулить курс",
    led: "Диод", button: "Кнопка", rate: "Гц", history: "Последние 10 с",
    nodevice: "Трики не найден",
    gestures: {
      single_press: "Нажатие", double_press: "Двойное нажатие", triple_press: "Тройное нажатие",
      long_press: "Долгое нажатие", tap: "Тап", double_tap: "Двойной тап", shake: "Встряхивание",
      flip: "Переворот", rotate_cw: "Поворот ↻", rotate_ccw: "Поворот ↺", wake: "Проснулся",
      motion: "Движение",
    },
  },
  pl: {
    asleep: "Śpi", connected: "Połączony", streaming: "Na żywo", unresponsive: "Nie odpowiada",
    wake: "Naciśnij lub potrząśnij kapslem, żeby go obudzić", gyro: "Żyroskop, °/s",
    accel: "Akcelerometr, g", roll: "Przechył", pitch: "Pochylenie", yaw: "Kurs",
    reset: "Wyzeruj kurs", led: "Dioda", button: "Przycisk", rate: "Hz", history: "Ostatnie 10 s",
    nodevice: "Nie znaleziono kapsla Triki",
    gestures: {
      single_press: "Naciśnięcie", double_press: "Podwójne naciśnięcie",
      triple_press: "Potrójne naciśnięcie", long_press: "Długie naciśnięcie", tap: "Stuknięcie",
      double_tap: "Podwójne stuknięcie", shake: "Potrząśnięcie", flip: "Obrót",
      rotate_cw: "Pokrętło ↻", rotate_ccw: "Pokrętło ↺", wake: "Obudzony", motion: "Ruch",
    },
  },
};

const AXIS_COLORS = ["#ef5350", "#66bb6a", "#42a5f5"];
const HISTORY_S = 10;
const GYRO_RANGE = 500; // °/s at full bar
const ACCEL_RANGE = 2; // g at full bar

let threePromise = null;
let modelPromise = null;
function loadThree() {
  if (!threePromise) threePromise = import(asset("triki-three.js"));
  return threePromise;
}
function loadModel(T) {
  if (!modelPromise) modelPromise = new T.GLTFLoader().loadAsync(asset("triki.glb"));
  return modelPromise;
}

const CSS = `
  :host { display: block; }
  ha-card { overflow: hidden; }
  .head { display: flex; align-items: center; gap: 8px; padding: 12px 16px 4px; flex-wrap: wrap; }
  .name { font-size: 1.15em; font-weight: 500; margin-right: auto; }
  .chip { display: inline-flex; align-items: center; gap: 4px; font-size: 0.85em; padding: 2px 8px;
    border-radius: 12px; background: var(--secondary-background-color); color: var(--secondary-text-color); }
  .chip.live { background: rgba(102,187,106,.2); color: #66bb6a; }
  .chip.warn { background: rgba(255,152,0,.2); color: #ff9800; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
  .chip.live .dot { animation: pulse 1.2s infinite; }
  @keyframes pulse { 50% { opacity: .3; } }
  .stage { position: relative; aspect-ratio: 16 / 10; min-height: 220px; }
  canvas.gl { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
  .angles { position: absolute; left: 12px; top: 8px; display: flex; gap: 14px; pointer-events: none; }
  .angle { display: flex; flex-direction: column; }
  .angle small { font-size: .72em; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .04em; }
  .angle b { font-size: 1.35em; font-variant-numeric: tabular-nums; min-width: 3.2em; }
  .btn-ind { position: absolute; right: 12px; top: 10px; display: flex; align-items: center; gap: 6px;
    font-size: .8em; color: var(--secondary-text-color); }
  .btn-ind .led { width: 14px; height: 14px; border-radius: 50%; border: 2px solid var(--divider-color);
    transition: background .08s, box-shadow .08s; }
  .btn-ind.on .led { background: #66bb6a; box-shadow: 0 0 10px #66bb6a; border-color: #66bb6a; }
  .toast { position: absolute; left: 50%; bottom: 14px; transform: translateX(-50%) scale(.9); opacity: 0;
    background: var(--primary-color); color: var(--text-primary-color, #fff); padding: 6px 14px;
    border-radius: 16px; font-weight: 500; transition: opacity .2s, transform .2s; pointer-events: none; }
  .toast.show { opacity: 1; transform: translateX(-50%) scale(1); }
  .sleep { position: absolute; inset: 0; display: none; align-items: flex-end; justify-content: center;
    padding-bottom: 16px; color: var(--secondary-text-color); font-size: .9em; pointer-events: none; }
  .asleep .sleep { display: flex; }
  .asleep canvas.gl { opacity: .45; filter: grayscale(.7); }
  .values { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 20px; padding: 8px 16px 4px; }
  .values h4 { margin: 4px 0 2px; font-size: .78em; font-weight: 500; color: var(--secondary-text-color); }
  .row { display: grid; grid-template-columns: 14px 1fr 4.2em; align-items: center; gap: 6px; height: 20px; }
  .row span { font-size: .8em; font-weight: 600; }
  .row output { text-align: right; font-variant-numeric: tabular-nums; font-size: .9em; }
  .bar { position: relative; height: 6px; border-radius: 3px; background: var(--divider-color); overflow: hidden; }
  .bar i { position: absolute; top: 0; bottom: 0; left: 50%; width: 0; border-radius: 3px; }
  .bar::after { content: ""; position: absolute; left: 50%; top: -2px; bottom: -2px; width: 1px; background: var(--secondary-text-color); opacity: .5; }
  .chart { padding: 4px 16px 0; }
  .chart small { font-size: .72em; color: var(--secondary-text-color); }
  canvas.hist { width: 100%; height: 70px; display: block; }
  .actions { display: flex; gap: 8px; padding: 8px 16px 14px; }
  .actions button { flex: 1; font: inherit; font-size: .9em; padding: 8px; border-radius: 8px; cursor: pointer;
    border: 1px solid var(--divider-color); background: var(--secondary-background-color); color: var(--primary-text-color); }
  .actions button:disabled { opacity: .45; cursor: default; }
  .actions button.on { border-color: #66bb6a; color: #66bb6a; }
  .empty { padding: 24px 16px; color: var(--secondary-text-color); }
`;

class TrikiCard extends HTMLElement {
  static getStubConfig() { return {}; }
  static getConfigElement() { return document.createElement("triki-card-editor"); }

  setConfig(config) {
    this._config = { show_values: true, show_history: true, ...config };
    if (this._built) this._build();
  }

  getCardSize() { return 8; }
  getGridOptions() { return { columns: 12, min_columns: 6, rows: "auto" }; }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._t = STRINGS[(hass.locale?.language || hass.language || "en").slice(0, 2)] || STRINGS.en;
    if (!this._built) this._build();
    if (this.isConnected && !this._unsub && !this._subscribing) this._subscribe();
  }

  connectedCallback() {
    if (this._hass && !this._unsub && !this._subscribing) this._subscribe();
    if (this._io) this._io.observe(this);
  }

  disconnectedCallback() {
    this._unsubscribe();
    if (this._io) this._io.disconnect();
    this._visible = false;
  }

  // ------------------------------------------------------------------ DOM
  _build() {
    const t = this._t || STRINGS.en;
    const c = this._config || {};
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const axisRows = (id) => ["x", "y", "z"].map((a, i) =>
      `<div class="row"><span style="color:${AXIS_COLORS[i]}">${a}</span><div class="bar"><i id="${id}${a}" style="background:${AXIS_COLORS[i]}"></i></div><output id="${id}${a}v">—</output></div>`).join("");
    this.shadowRoot.innerHTML = `<style>${CSS}</style>
      <ha-card>
        <div class="head">
          <div class="name" id="name">${c.title || "Triki"}</div>
          <div class="chip" id="state"><div class="dot"></div><span id="stateText">${t.asleep}</span></div>
          <div class="chip" id="rateChip" hidden><ha-icon icon="mdi:sine-wave" style="--mdc-icon-size:14px"></ha-icon><span id="rate"></span></div>
          <div class="chip" id="rssiChip" hidden><ha-icon icon="mdi:bluetooth" style="--mdc-icon-size:14px"></ha-icon><span id="rssi"></span></div>
          <div class="chip" id="battChip" hidden><ha-icon id="battIcon" icon="mdi:battery" style="--mdc-icon-size:14px"></ha-icon><span id="batt"></span></div>
        </div>
        <div class="stage asleep" id="stage">
          <canvas class="gl" id="gl"></canvas>
          <div class="angles">
            <div class="angle"><small>${t.roll}</small><b id="roll">—</b></div>
            <div class="angle"><small>${t.pitch}</small><b id="pitch">—</b></div>
            <div class="angle"><small>${t.yaw}</small><b id="yaw">—</b></div>
          </div>
          <div class="btn-ind" id="btnInd"><div class="led"></div>${t.button}</div>
          <div class="toast" id="toast"></div>
          <div class="sleep">${t.wake}</div>
        </div>
        ${c.show_values ? `<div class="values"><div><h4>${t.gyro}</h4>${axisRows("g")}</div><div><h4>${t.accel}</h4>${axisRows("a")}</div></div>` : ""}
        ${c.show_history ? `<div class="chart"><small>${t.gyro} · ${t.history}</small><canvas class="hist" id="hist"></canvas></div>` : ""}
        <div class="actions">
          <button id="reset" disabled>${t.reset}</button>
          <button id="led" disabled>${t.led}</button>
        </div>
      </ha-card>`;
    const $ = (id) => this.shadowRoot.getElementById(id);
    this._el = {
      name: $("name"), state: $("state"), stateText: $("stateText"), rate: $("rate"), rateChip: $("rateChip"),
      rssi: $("rssi"), rssiChip: $("rssiChip"), batt: $("batt"), battChip: $("battChip"), battIcon: $("battIcon"),
      stage: $("stage"), gl: $("gl"), roll: $("roll"), pitch: $("pitch"), yaw: $("yaw"), btnInd: $("btnInd"),
      toast: $("toast"), hist: $("hist"), reset: $("reset"), led: $("led"),
    };
    for (const p of ["g", "a"]) for (const a of ["x", "y", "z"]) {
      this._el[`${p}${a}`] = $(`${p}${a}`);
      this._el[`${p}${a}v`] = $(`${p}${a}v`);
    }
    this._el.reset.addEventListener("click", () => this._resetHeading());
    this._el.led.addEventListener("click", () => this._toggleLed());
    this._history = [];
    this._built = true;
    this._io = new IntersectionObserver((entries) => {
      this._visible = entries.some((e) => e.isIntersecting);
      if (this._visible) this._startRender();
    });
    if (this.isConnected) this._io.observe(this);
    if (this._status) this._showStatus(this._status);
  }

  // ------------------------------------------------------------------ data
  async _subscribe() {
    this._subscribing = true;
    try {
      let deviceId = this._config?.device_id;
      if (!deviceId) {
        const devices = await this._hass.connection.sendMessagePromise({ type: "triki/devices" });
        deviceId = devices[0]?.device_id;
        if (!deviceId) { this._noDevice(); return; }
      }
      this._deviceId = deviceId;
      this._unsub = await this._hass.connection.subscribeMessage(
        (msg) => this._onMessage(msg), { type: "triki/subscribe", device_id: deviceId });
    } catch (err) {
      console.warn("triki-card: subscribe failed", err);
      this._noDevice();
    } finally {
      this._subscribing = false;
    }
  }

  _unsubscribe() {
    if (this._unsub) { this._unsub().catch?.(() => {}); this._unsub = null; }
  }

  _noDevice() {
    const card = this.shadowRoot?.querySelector("ha-card");
    if (card) card.innerHTML = `<div class="empty">${(this._t || STRINGS.en).nodevice}</div>`;
  }

  _onMessage(msg) {
    if (msg.type === "status") this._showStatus(msg);
    else if (msg.type === "motion") this._showMotion(msg);
    else if (msg.type === "event") this._showEvent(msg.event, msg.data);
  }

  _showStatus(s) {
    this._status = s;
    const t = this._t, el = this._el;
    if (!el) return;
    if (!this._config?.title && s.name) el.name.textContent = s.name;
    const live = s.connected && s.streaming;
    el.state.className = `chip ${live ? "live" : s.unresponsive ? "warn" : ""}`;
    el.stateText.textContent = live ? t.streaming : s.connected ? t.connected : s.unresponsive ? t.unresponsive : t.asleep;
    el.stage.classList.toggle("asleep", !live);
    el.rateChip.hidden = !live;
    if (live) el.rate.textContent = `${Math.round(s.measured_rate ?? s.rate ?? 0)} ${t.rate}`;
    el.rssiChip.hidden = s.rssi == null;
    if (s.rssi != null) el.rssi.textContent = `${s.rssi} dBm`;
    el.battChip.hidden = s.battery == null;
    if (s.battery != null) {
      el.batt.textContent = `${s.battery}%`;
      const step = Math.max(1, Math.min(10, Math.round(s.battery / 10))) * 10;
      el.battIcon.setAttribute("icon", step >= 100 ? "mdi:battery" : `mdi:battery-${step}`);
    }
    el.reset.disabled = !live;
    el.led.disabled = !s.connected;
    el.led.classList.toggle("on", !!s.led);
    el.btnInd.classList.toggle("on", !!s.button);
    if (!live) {
      this._target = null;
      for (const k of ["roll", "pitch", "yaw"]) el[k].textContent = "—";
    }
  }

  _showMotion(m) {
    const el = this._el;
    if (!el) return;
    const [w, x, y, z] = m.quaternion;
    this._target = [w, -x, z, y]; // sensor frame -> model frame, see the header
    el.roll.textContent = `${Math.round(m.euler[0])}°`;
    el.pitch.textContent = `${Math.round(m.euler[1])}°`;
    el.yaw.textContent = `${Math.round(m.euler[2])}°`;
    el.btnInd.classList.toggle("on", !!m.button);
    if (this._config.show_values) {
      ["x", "y", "z"].forEach((a, i) => {
        this._bar(el[`g${a}`], m.gyro[i] / GYRO_RANGE);
        el[`g${a}v`].textContent = m.gyro[i].toFixed(0);
        this._bar(el[`a${a}`], m.accel[i] / ACCEL_RANGE);
        el[`a${a}v`].textContent = m.accel[i].toFixed(2);
      });
    }
    if (this._config.show_history) {
      const now = performance.now() / 1000;
      this._history.push([now, ...m.gyro]);
      while (this._history.length && now - this._history[0][0] > HISTORY_S) this._history.shift();
      this._historyDirty = true;
    }
    this._startRender();
  }

  _bar(i, v) {
    const f = Math.max(-1, Math.min(1, v));
    i.style.width = `${Math.abs(f) * 50}%`;
    i.style.left = f < 0 ? `${50 + f * 50}%` : "50%";
  }

  _showEvent(kind, data) {
    const names = this._t.gestures;
    let label = names[kind];
    if (!label) return;
    if ((kind === "rotate_cw" || kind === "rotate_ccw") && data?.steps) label += ` ×${data.steps}`;
    if (kind === "motion") return; // too frequent to be worth a toast
    const el = this._el.toast;
    el.textContent = label;
    el.classList.add("show");
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => el.classList.remove("show"), 1200);
  }

  async _resetHeading() {
    try {
      await this._hass.connection.sendMessagePromise({ type: "triki/reset_heading", device_id: this._deviceId });
    } catch (err) { console.warn("triki-card: reset failed", err); }
  }

  _toggleLed() {
    const ent = Object.values(this._hass.entities || {}).find(
      (e) => e.device_id === this._deviceId && e.entity_id.startsWith("switch.") && e.translation_key === "led");
    if (!ent) return;
    this._hass.callService("switch", this._status?.led ? "turn_off" : "turn_on", { entity_id: ent.entity_id });
  }

  // ------------------------------------------------------------------ 3D
  async _ensureScene() {
    if (this._scene || this._sceneLoading) return;
    this._sceneLoading = true;
    try {
      const T = await loadThree();
      this._T = T;
      const renderer = new T.WebGLRenderer({ canvas: this._el.gl, antialias: true, alpha: true });
      renderer.outputColorSpace = T.SRGBColorSpace;
      renderer.toneMapping = T.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.0;
      const scene = new T.Scene();
      const pmrem = new T.PMREMGenerator(renderer);
      scene.environment = pmrem.fromScene(new T.RoomEnvironment(), 0.04).texture;
      scene.add(new T.HemisphereLight(0xffffff, 0x404040, 0.8));
      const key = new T.DirectionalLight(0xffffff, 1.6);
      key.position.set(2, 4, 3);
      scene.add(key);
      const camera = new T.PerspectiveCamera(32, 1, 0.1, 50);
      camera.position.set(0, 3.3, 2.3);
      camera.lookAt(0, 0, 0);
      const pivot = new T.Group();
      scene.add(pivot);
      const gltf = await loadModel(T);
      const model = gltf.scene.clone(true);
      const box = new T.Box3().setFromObject(model);
      const size = box.getSize(new T.Vector3()).length();
      model.position.sub(box.getCenter(new T.Vector3()));
      model.scale.setScalar(2.9 / size);
      model.position.multiplyScalar(2.9 / size);
      pivot.add(model);
      Object.assign(this, { _renderer: renderer, _scene: scene, _camera: camera, _pivot: pivot });
      this._q = new T.Quaternion();
      this._qTarget = new T.Quaternion();
      this._ro = new ResizeObserver(() => this._resize());
      this._ro.observe(this._el.stage);
      this._resize();
    } catch (err) {
      console.warn("triki-card: 3D view unavailable", err);
    } finally {
      this._sceneLoading = false;
    }
  }

  _resize() {
    if (!this._renderer) return;
    const r = this._el.stage.getBoundingClientRect();
    if (!r.width || !r.height) return;
    this._renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this._renderer.setSize(r.width, r.height, false);
    this._camera.aspect = r.width / r.height;
    this._camera.updateProjectionMatrix();
    this._needsFrame = true;
    this._startRender();
  }

  async _startRender() {
    if (this._raf || !this._visible) return;
    await this._ensureScene();
    if (!this._scene || this._raf || !this._visible) return;
    const tick = () => {
      this._raf = null;
      if (!this._visible || !this.isConnected) return;
      let moving = false;
      if (this._target) {
        this._qTarget.set(this._target[1], this._target[2], this._target[3], this._target[0]);
        if (this._q.angleTo(this._qTarget) > 0.0005) {
          this._q.slerp(this._qTarget, 0.35);
          moving = true;
        }
      } else if (this._q.angleTo(this._qTarget.identity()) > 0.0005) {
        this._q.slerp(this._qTarget, 0.1); // back to the rest pose while asleep
        moving = true;
      }
      if (moving || this._needsFrame) {
        this._pivot.quaternion.copy(this._q);
        this._renderer.render(this._scene, this._camera);
        this._needsFrame = false;
      }
      if (this._historyDirty) { this._drawHistory(); this._historyDirty = false; }
      if (moving || this._target) this._raf = requestAnimationFrame(tick);
    };
    this._needsFrame = true;
    this._raf = requestAnimationFrame(tick);
  }

  _drawHistory() {
    const cv = this._el.hist;
    if (!cv) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = cv.clientWidth, h = cv.clientHeight;
    if (!w || !h) return;
    if (cv.width !== w * dpr) { cv.width = w * dpr; cv.height = h * dpr; }
    const ctx = cv.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = getComputedStyle(this).getPropertyValue("--divider-color") || "#444";
    ctx.beginPath(); ctx.moveTo(0, h / 2); ctx.lineTo(w, h / 2); ctx.stroke();
    const hist = this._history;
    if (hist.length < 2) return;
    const now = hist[hist.length - 1][0];
    let peak = 90;
    for (const p of hist) for (let i = 1; i < 4; i++) peak = Math.max(peak, Math.abs(p[i]));
    for (let axis = 1; axis < 4; axis++) {
      ctx.strokeStyle = AXIS_COLORS[axis - 1];
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      hist.forEach((p, k) => {
        const x = w - ((now - p[0]) / HISTORY_S) * w;
        const y = h / 2 - (p[axis] / peak) * (h / 2 - 2);
        if (k) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      });
      ctx.stroke();
    }
  }
}

class TrikiCardEditor extends HTMLElement {
  setConfig(config) { this._config = config; this._render(); }
  set hass(hass) { this._hass = hass; this._render(); }
  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => ({
        device_id: "Triki", title: "Title", show_values: "Gyro and accelerometer bars",
        show_history: "Gyro history",
      })[s.name] || s.name;
      this._form.addEventListener("value-changed", (ev) => {
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: ev.detail.value } }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = this._config;
    this._form.schema = [
      { name: "device_id", selector: { device: { integration: "triki" } } },
      { name: "title", selector: { text: {} } },
      { name: "show_values", selector: { boolean: {} } },
      { name: "show_history", selector: { boolean: {} } },
    ];
  }
}

if (!customElements.get("triki-card")) {
  customElements.define("triki-card", TrikiCard);
  customElements.define("triki-card-editor", TrikiCardEditor);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "triki-card",
    name: "Triki live 3D",
    description: "A Żabka Triki token in 3D, moving with the real one, with its gyro and accelerometer.",
    preview: false,
    documentationURL: "https://github.com/elenium3/ha-triki/blob/main/docs/live-card.md",
  });
}
