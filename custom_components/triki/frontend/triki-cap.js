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
// Textures are the owner's photos: the metal face with the logo taken from the photo as a
// mask, and the PCB under the resin as photographed.
//
// Returns a promise of { group, setLed(on), setPressed(on) }.

const FLUTES = 21;
const H = 6.8; // crown face at z = 0, rim at z = H
const R_FACE = 12.0; // flat metal face
const R_SHOULDER = 13.0; // radius where the skirt starts
const FLUTE_DEPTH = 0.9; // how far the flutes stand out at the rim
const RESIN_Z = 6.0; // the resin surface sits a little below the rim
const R_RESIN = 12.6;

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

// Which way the top of the resin photo (tex_resin.webp) points in the sensor frame,
// radians. The photo has the Żabka Z (copper under the resin) upright, and the sensor
// axes are known against that Z (Flopsstuff's axes photo: +x to the left of the Z,
// +y towards its foot), so the photo's top is sensor -y.
export const RESIN_PHOTO_UP = -Math.PI / 2;

// Turn of the metal logo about the cap axis, radians, against the PCB photo.
export const LOGO_ANGLE = 0;

function loadTexture(T, url) {
  return new Promise((resolve, reject) => {
    new T.TextureLoader().load(url, (t) => {
      t.colorSpace = T.SRGBColorSpace;
      t.anisotropy = 4;
      resolve(t);
    }, undefined, reject);
  });
}

export async function buildCap(T, urls) {
  const [metalMap, resinMap] = await Promise.all([loadTexture(T, urls.metal), loadTexture(T, urls.resin)]);
  const group = new T.Group();
  const inner = new T.Group();
  inner.position.z = -H / 2; // rotate about the middle of the token
  group.add(inner);

  const metal = new T.MeshStandardMaterial({
    color: 0xd0d2d4, metalness: 1.0, roughness: 0.32, side: T.DoubleSide,
  });
  inner.add(new T.Mesh(shellGeometry(T), metal));

  // the metal face: photographed from outside; after the half turn about x the
  // photo's top points to -y. The crown is crimped on at any angle, so the logo's
  // angle against the PCB differs from cap to cap; LOGO_ANGLE is the owner's cap.
  const faceMat = new T.MeshStandardMaterial({ map: metalMap, metalness: 0.9, roughness: 0.36 });
  const face = new T.Mesh(new T.CircleGeometry(R_FACE + 0.02, 96), faceMat);
  face.rotation.x = Math.PI; // faces -z
  const logo = new T.Group();
  logo.rotation.z = LOGO_ANGLE;
  logo.add(face);
  inner.add(logo);

  // The photo already carries the resin's look (light, gloss, the PCB under it), so it is
  // shown as is: unlit emission outside the tone mapping. Scene light and reflections on
  // top of it washed it out into a milky green.
  const RESIN_SELF = 0.8;
  const resinMat = new T.MeshStandardMaterial({
    color: 0x000000, emissiveMap: resinMap, emissive: 0xffffff, emissiveIntensity: RESIN_SELF,
    roughness: 1, metalness: 0, envMapIntensity: 0, toneMapped: false,
  });
  const resin = new T.Group();
  const top = new T.Mesh(new T.CircleGeometry(R_RESIN, 96), resinMat);
  top.position.z = RESIN_Z;
  top.rotation.z = RESIN_PHOTO_UP - Math.PI / 2; // the photo's top was +y
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
      resinMat.emissive.set(on ? 0xd8ffb0 : 0xffffff);
      resinMat.emissiveIntensity = on ? 1.6 : RESIN_SELF;
      glow.intensity = on ? 40 : 0;
    },
    setPressed(on) {
      resin.position.z = on ? -0.45 : 0;
    },
  };
}
