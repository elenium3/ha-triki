// The card's forward-back angle is read from the side that is up.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../../custom_components/triki/frontend/triki-card.js", import.meta.url), "utf8");
const start = src.indexOf("  _faceRoll(roll) {");
const body = src.slice(start + "  _faceRoll(roll) {".length, src.indexOf("\n  }\n", start));
const card = { _faceRoll: new Function("roll", body) };
const show = (r) => Math.round(card._faceRoll(r));

test("flat either side up reads 0", () => {
  assert.equal(show(-178), 2);
  assert.equal(show(179), -1);
  assert.equal(show(1.5), 2);
});

test("a tilt from metal side up keeps its size and side", () => {
  assert.equal(show(-178), 2);
  assert.equal(show(150), -30);
  assert.equal(show(-150), 30);
});

test("no flicker on the edge", () => {
  show(-178); // metal up
  assert.equal(show(95), -85); // past 90 but not below 80: still metal up
  assert.equal(show(85), -95);
  assert.equal(show(60), 60); // below 80: green up
  assert.equal(show(95), 95);
});
