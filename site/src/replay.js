// The integration's own live card, fed a recording of a real Triki through a
// stand-in for Home Assistant. Nothing here talks to a real cap or server.
const stage = document.getElementById("replay");
const lang = stage.dataset.lang;
const captions = JSON.parse(stage.dataset.captions);
const capText = document.getElementById("capText");

function webgl() {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch { return false; }
}

async function start() {
  for (const n of ["ha-card", "ha-icon"]) if (!customElements.get(n)) customElements.define(n, class extends HTMLElement {});
  await import(new URL("card/triki-card.js", import.meta.url));
  const TL = await (await fetch(new URL("timeline.json", import.meta.url))).json();
  let push;
  const hass = {
    language: lang, locale: { language: lang }, entities: {}, user: { is_admin: false },
    callService: async () => {},
    connection: {
      sendMessagePromise: async (m) => (m.type === "triki/devices" ? [{ device_id: "demo", name: "Triki" }] : null),
      subscribeMessage: async (cb) => { push = cb; return async () => {}; },
    },
  };
  const el = document.createElement("triki-card");
  el.setConfig({ buttons: [] });
  stage.querySelector(".slot").appendChild(el);
  el.hass = hass;
  for (let k = 0; k < 50 && !push; k++) await new Promise((r) => setTimeout(r, 50));
  if (!push) throw new Error("the card did not subscribe");
  const base = { type: "status", name: "Triki", device_id: "demo", connected: true, streaming: true, battery: 90,
    rssi: -61, link_quality: 99, rate: 52, measured_rate: 52.4, button: false, led: false, logo_angle: -90,
    calibrated: true, readiness: "connected", via: "ESP32 Bluetooth proxy" };
  push(base);
  stage.classList.add("live");

  let i = 0, n = 0, loop = 0, btn = false, played = 0, last = null, visible = true;
  new IntersectionObserver(([x]) => { visible = x.isIntersecting; }).observe(stage);
  const frame = (now) => {
    requestAnimationFrame(frame);
    if (last === null || !visible || document.hidden) { last = now; return; }
    played += Math.min(0.1, (now - last) / 1000); // a background tab does not fast-forward
    last = now;
    if (played > TL.length) { played -= TL.length; i = 0; loop++; }
    const label = TL.labels.filter((l) => l[0] <= played).length - 1;
    capText.textContent = captions[Math.max(0, label)];
    while (i < TL.frames.length && TL.frames[i].t <= played) {
      const f = TL.frames[i++]; n++;
      if (f.b !== btn) { btn = f.b; push({ ...base, button: btn }); }
      push({ type: "motion", quaternion: f.q, euler: f.e, gyro: f.g, accel: f.a, button: f.b, frames: n, rate: 52,
        ts: loop * TL.length + f.t });
      for (const [kind, data] of f.ev) push({ type: "event", event: kind, data });
    }
  };
  requestAnimationFrame(frame);
}

// the card and its 3D model load only when the reader gets near it
if (!matchMedia("(prefers-reduced-motion: reduce)").matches && webgl()) {
  const near = new IntersectionObserver(([x]) => {
    if (!x.isIntersecting) return;
    near.disconnect();
    start().catch((err) => { console.warn("live card replay off:", err); stage.classList.remove("live"); });
  }, { rootMargin: "600px" });
  near.observe(stage);
}
