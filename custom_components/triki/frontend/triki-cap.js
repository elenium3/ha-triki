// A procedural 3D model of the Triki token for triki-card.
//
// Built in the sensor frame, in millimetres: +z out of the resin side (the PCB under
// green resin, the side the stream calls the top), -y towards the top of the PCB art,
// +x to its left; the brushed metal crown with the logo faces -z. The sensor quaternion
// can then be applied to the returned group as is.
//
// Dimensions are from the owner's calipers (2026-11-18): about 28 mm across the
// flutes and 6.8 mm high. The flute count, 21, is the crown cork standard.
//
// Returns { group, setLed(on), setPressed(on) }.

const FLUTES = 21;
const H = 6.8; // crown face at z = 0, rim at z = H
const R_FACE = 12.0; // flat metal face
const R_SHOULDER = 13.0; // radius where the skirt starts
const FLUTE_DEPTH = 0.9; // how far the flutes stand out at the rim
const RESIN_Z = 6.0; // the resin surface sits a little below the rim
const R_RESIN = 12.6;

function rng(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

// The metal skirt with its flutes: a grid over (angle, profile position).
function shellGeometry(T) {
  const profile = []; // [r, z, flute amount 0..1]
  const SH = 10; // shoulder: quarter circle from the face to the skirt
  for (let i = 0; i <= SH; i++) {
    const a = (i / SH) * (Math.PI / 2);
    const rr = R_SHOULDER - R_FACE;
    profile.push([R_FACE + rr * Math.sin(a), rr - rr * Math.cos(a), 0]);
  }
  const SK = 16;
  for (let i = 1; i <= SK; i++) {
    const t = i / SK;
    const z = (R_SHOULDER - R_FACE) + t * (H - (R_SHOULDER - R_FACE));
    profile.push([R_SHOULDER + 0.35 * t, z, Math.min(1, t * 1.6)]);
  }
  // the rim folds inwards a little
  profile.push([R_SHOULDER + 0.15, H + 0.05, 1]);
  profile.push([R_SHOULDER - 0.25, H, 0.8]);

  const N = FLUTES * 24;
  const pos = [];
  const uv = [];
  for (let j = 0; j < profile.length; j++) {
    const [r0, z, k] = profile[j];
    for (let i = 0; i <= N; i++) {
      const th = (i / N) * Math.PI * 2;
      // rounded crests, sharper valleys
      const f = Math.pow(0.5 + 0.5 * Math.cos(FLUTES * th), 0.55);
      const r = r0 + k * FLUTE_DEPTH * (f - 0.35);
      pos.push(r * Math.cos(th), r * Math.sin(th), z);
      uv.push(i / N, j / (profile.length - 1));
    }
  }
  const idx = [];
  const row = N + 1;
  for (let j = 0; j < profile.length - 1; j++) {
    for (let i = 0; i < N; i++) {
      const a = j * row + i, b = a + 1, c = a + row, d = c + 1;
      idx.push(a, c, b, b, c, d);
    }
  }
  const g = new T.BufferGeometry();
  g.setAttribute("position", new T.Float32BufferAttribute(pos, 3));
  g.setAttribute("uv", new T.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  g.computeVertexNormals();
  return g;
}

function canvas(size) {
  const c = document.createElement("canvas");
  c.width = c.height = size;
  return [c, c.getContext("2d")];
}

// Brushed metal with the three-armed logo, as on the crown side.
function metalTexture(T) {
  const S = 512;
  const [c, g] = canvas(S);
  g.fillStyle = "#c4c6c8";
  g.fillRect(0, 0, S, S);
  const rand = rng(7);
  for (let i = 0; i < 900; i++) {
    const r = rand() * S * 0.5;
    const v = 170 + Math.floor(rand() * 60);
    g.strokeStyle = `rgba(${v},${v},${v + 4},0.35)`;
    g.lineWidth = 0.6 + rand();
    const a0 = rand() * Math.PI * 2;
    g.beginPath();
    g.arc(S / 2, S / 2, r, a0, a0 + 0.4 + rand() * 1.4);
    g.stroke();
  }
  // logo: three rounded arms from one point
  g.strokeStyle = "#141414";
  g.lineCap = "round";
  g.lineJoin = "round";
  g.lineWidth = S * 0.075;
  const cx = S * 0.47, cy = S * 0.52;
  g.beginPath();
  g.moveTo(S * 0.3, S * 0.33);
  g.lineTo(cx, cy);
  g.lineTo(S * 0.72, S * 0.52);
  g.moveTo(cx, cy);
  g.lineTo(S * 0.32, S * 0.7);
  g.stroke();
  const t = new T.CanvasTexture(c);
  t.colorSpace = T.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

// The PCB under the green resin, with the Z pressed into the resin.
function resinTexture(T) {
  const S = 1024;
  const [c, g] = canvas(S);
  const rand = rng(42);
  const u = (v) => (v * 0.5 + 0.5) * S; // -1..1 -> px
  g.fillStyle = "#1d5a14";
  g.fillRect(0, 0, S, S);
  // copper traces under the solder mask
  g.strokeStyle = "rgba(90, 170, 40, 0.6)";
  g.lineCap = "round";
  for (let i = 0; i < 70; i++) {
    let x = u(rand() * 1.6 - 0.8), y = u(rand() * 1.6 - 0.8);
    g.lineWidth = 2 + rand() * 4;
    g.beginPath();
    g.moveTo(x, y);
    for (let k = 0; k < 3; k++) {
      const l = 30 + rand() * 120;
      const dir = Math.floor(rand() * 4);
      if (dir === 0) x += l; else if (dir === 1) x -= l; else if (dir === 2) y += l; else y -= l;
      g.lineTo(x, y);
    }
    g.stroke();
  }
  // vias
  g.fillStyle = "rgba(210, 190, 90, 0.8)";
  for (let i = 0; i < 90; i++) {
    g.beginPath();
    g.arc(u(rand() * 1.5 - 0.75), u(rand() * 1.5 - 0.75), 4, 0, Math.PI * 2);
    g.fill();
  }
  const chip = (x, y, w, h, rot, color) => {
    g.save();
    g.translate(u(x), u(y));
    g.rotate(rot);
    g.fillStyle = color;
    g.fillRect((-w / 2) * S * 0.5, (-h / 2) * S * 0.5, w * S * 0.5, h * S * 0.5);
    g.restore();
  };
  chip(-0.2, 0.0, 0.36, 0.36, Math.PI / 4, "#151a15"); // the SoC
  chip(0.38, -0.05, 0.18, 0.18, 0, "#1b211b"); // the IMU
  for (let i = 0; i < 16; i++) {
    chip(rand() * 1.2 - 0.6, rand() * 1.2 - 0.6, 0.06, 0.03, rand() < 0.5 ? 0 : Math.PI / 2,
      rand() < 0.5 ? "#c9a46a" : "#2a2a2a");
  }
  // gold pads near the edge and the one in the middle
  g.fillStyle = "#e3c45a";
  for (const [x, y, r] of [[0.0, -0.72, 0.075], [-0.68, 0.18, 0.075], [0.62, 0.42, 0.075],
    [0.5, -0.5, 0.06], [0.05, 0.05, 0.035]]) {
    g.beginPath();
    g.arc(u(x), u(y), r * S * 0.5, 0, Math.PI * 2);
    g.fill();
  }
  // the resin: yellow-green, lighter towards the rim
  const grad = g.createRadialGradient(S / 2, S / 2, S * 0.1, S / 2, S / 2, S * 0.5);
  grad.addColorStop(0, "rgba(120, 210, 20, 0.30)");
  grad.addColorStop(0.85, "rgba(150, 230, 30, 0.40)");
  grad.addColorStop(1, "rgba(190, 250, 80, 0.70)");
  g.fillStyle = grad;
  g.fillRect(0, 0, S, S);
  // the Z pressed into the resin: a light outline
  g.strokeStyle = "rgba(215, 255, 170, 0.45)";
  g.lineWidth = 7;
  g.lineJoin = "round";
  const zp = [[-0.32, -0.42], [0.36, -0.42], [-0.12, 0.3], [0.36, 0.3], [0.36, 0.44], [-0.36, 0.44],
    [0.12, -0.28], [-0.32, -0.28]];
  g.beginPath();
  zp.forEach(([x, y], i) => (i ? g.lineTo(u(x), u(y)) : g.moveTo(u(x), u(y))));
  g.closePath();
  g.stroke();
  const t = new T.CanvasTexture(c);
  t.colorSpace = T.SRGBColorSpace;
  t.anisotropy = 4;
  // canvas up is -y and canvas right is -x (see the header): turn the map half a turn
  t.center.set(0.5, 0.5);
  t.rotation = Math.PI;
  return t;
}

export function buildCap(T) {
  const group = new T.Group();
  const inner = new T.Group();
  inner.position.z = -H / 2; // rotate about the middle of the token
  group.add(inner);

  const metal = new T.MeshStandardMaterial({
    color: 0xd0d2d4, metalness: 1.0, roughness: 0.32, side: T.DoubleSide,
  });
  inner.add(new T.Mesh(shellGeometry(T), metal));

  const faceMat = new T.MeshStandardMaterial({
    map: metalTexture(T), metalness: 0.95, roughness: 0.38,
  });
  const face = new T.Mesh(new T.CircleGeometry(R_FACE + 0.02, 96), faceMat);
  face.rotation.x = Math.PI; // faces -z
  inner.add(face);

  const resinMap = resinTexture(T);
  const resinMat = new T.MeshPhysicalMaterial({
    map: resinMap, emissiveMap: resinMap, emissive: 0x9cff3c, emissiveIntensity: 0.0,
    roughness: 0.18, metalness: 0.0, clearcoat: 1.0, clearcoatRoughness: 0.08,
  });
  const resin = new T.Group();
  const top = new T.Mesh(new T.CircleGeometry(R_RESIN, 96), resinMat);
  top.position.z = RESIN_Z;
  resin.add(top);
  const wall = new T.Mesh(
    new T.CylinderGeometry(R_RESIN, R_RESIN, RESIN_Z - 1.2, 96, 1, true),
    new T.MeshStandardMaterial({ color: 0x7fd43a, roughness: 0.3, transparent: true, opacity: 0.85 }),
  );
  wall.rotation.x = Math.PI / 2;
  wall.position.z = (RESIN_Z + 1.2) / 2;
  resin.add(wall);
  inner.add(resin);

  const glow = new T.PointLight(0x9cff3c, 0, 40, 1.5);
  glow.position.z = RESIN_Z + 4;
  inner.add(glow);

  return {
    group,
    setLed(on) {
      resinMat.emissiveIntensity = on ? 0.35 : 0.0;
      glow.intensity = on ? 40 : 0;
    },
    setPressed(on) {
      resin.position.z = on ? -0.45 : 0;
    },
  };
}
