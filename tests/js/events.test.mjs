// The card names gestures by what the hand did; the integration sends Home
// Assistant's standard button event types.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../../custom_components/triki/frontend/triki-card.js", import.meta.url), "utf8");
const start = src.indexOf("function gestureOf(event, data) {");
const body = src.slice(start + "function gestureOf(event, data) {".length, src.indexOf("\n}\n", start));
const gestureOf = new Function("event", "data", body);

test("standard button events map to the card's gestures", () => {
  assert.equal(gestureOf("single_press", {}), "press");
  assert.equal(gestureOf("multi_press", { press_count: 2 }), "double_press");
  assert.equal(gestureOf("multi_press", { press_count: 3 }), "triple_press");
  assert.equal(gestureOf("long_press_start", {}), "long_press");
});

test("the rest passes through", () => {
  for (const e of ["wake", "long_press_end", "rotate_cw", "tilt_left", "shake", "flip"]) assert.equal(gestureOf(e, {}), e);
  assert.equal(gestureOf("multi_press", undefined), "double_press"); // no data: the smallest multi-press
});

test("every gesture the card can show has a label in each language", () => {
  for (const key of ["press", "double_press", "triple_press", "long_press", "long_press_end"]) {
    assert.equal(src.split(`${key}: "`).length - 1 >= 3, true, key);
  }
});
