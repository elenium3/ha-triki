// The card must not switch anything on its own: the LED of a coin-cell token stays
// as the owner left it (2026-11-23: the check's pick blink left it lit).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../../custom_components/triki/frontend/triki-card.js", import.meta.url), "utf8");

test("the only service call is the LED button's", () => {
  const calls = [...src.matchAll(/callService\(/g)];
  assert.equal(calls.length, 1);
  const before = src.slice(0, calls[0].index);
  assert.ok(before.lastIndexOf("_toggleLed()") > before.lastIndexOf("\n  }\n"), "callService outside _toggleLed");
});
