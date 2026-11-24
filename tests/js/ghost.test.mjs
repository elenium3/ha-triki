// The check's hint model: every step that asks for a move has one, and it stays
// in view.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../../custom_components/triki/frontend/triki-card.js", import.meta.url), "utf8");
const start = src.indexOf("const DEG = ");
const end = src.indexOf("\n}\n", src.indexOf("export function ghostMotion")) + 2;
const ghostMotion = new Function(`${src.slice(start, end).replace("export function", "function")}; return ghostMotion;`)();
const check = readFileSync(new URL("../../custom_components/triki/frontend/triki-check.js", import.meta.url), "utf8");

for (const type of ["lift", "lean", "press", "shake", "tap", "throw"]) {
  test(`${type}: finite, in view, moves`, () => {
    let moved = false;
    for (let ms = 0; ms < 8000; ms += 20) {
      const m = ghostMotion(type, ms / 1000);
      for (const k of ["lift", "tilt", "lean"]) {
        const x = m[k] ?? 0;
        assert.ok(Number.isFinite(x), `${type} ${k} at ${ms}`);
      }
      assert.ok((m.lift ?? 0) >= -0.2 && (m.lift ?? 0) <= 0.7, `${type} lift ${m.lift} at ${ms}`);
      if (Math.abs(m.lift ?? 0) > 0.05 || Math.abs(m.tilt ?? 0) > 0.1 || Math.abs(m.lean ?? 0) > 0.1) moved = true;
    }
    assert.ok(moved);
  });
}

test("every check step that asks for a move shows a hint", () => {
  for (const id of ["tilt", "turn_cw", "handle", "lean", "press", "flip", "tap", "shake", "throw"]) {
    const branch = check.indexOf(`s.id === "${id}"`, check.indexOf("view() {"));
    assert.ok(branch > 0, id);
    assert.match(check.slice(branch, check.indexOf("} else if", branch + 1)), /v\.ghost = /, id);
  }
});
