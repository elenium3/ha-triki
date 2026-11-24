// The card's defaults, which the editor shows too: an unset list is all of it.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../../custom_components/triki/frontend/triki-card.js", import.meta.url), "utf8");
const start = src.indexOf("const BUTTONS = ");
const end = src.indexOf("\n}\n", src.indexOf("export function cardConfig")) + 2;
const cardConfig = new Function(`${src.slice(start, end).replace("export function", "function")}; return cardConfig;`)();

test("an empty config shows everything", () => {
  const c = cardConfig({ type: "custom:triki-card", entity: "event.x" });
  assert.deepEqual(c.chips, ["state", "rate", "signal", "battery", "link"]);
  assert.deepEqual(c.buttons, ["calibrate", "align", "led", "check"]);
  assert.equal(c.show_gestures, true);
  assert.equal(c.show_help, true);
  assert.equal(c.entity, "event.x");
});

test("the old switches still hide their part", () => {
  const c = cardConfig({ show_controls: false, show_status: false });
  assert.deepEqual(c.chips, []);
  assert.deepEqual(c.buttons, []);
  assert.equal(c.show_help, false);
});

test("a picked list is kept as is", () => {
  const c = cardConfig({ chips: ["battery"], buttons: ["led"] });
  assert.deepEqual(c.chips, ["battery"]);
  assert.deepEqual(c.buttons, ["led"]);
});

test("the editor gets the filled-in config", () => {
  assert.match(src, /cardConfig\(this\._config\);\s*this\._form\.data = data;/);
});

test("the lean hint rolls the cap about its dot axis, the axis the tilt gesture reads", () => {
  // the dot is at sensor -y; _tilt in gestures.py reads ux, a turn about y
  assert.match(src, /const lr = new T\.Vector3\(0, 1, 0\)\.applyQuaternion\(q0\);/);
});
