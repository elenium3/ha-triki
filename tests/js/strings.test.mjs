// The card's texts: every language has the keys and the {placeholders} of English.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../../custom_components/triki/frontend/triki-card.js", import.meta.url), "utf8");
const start = src.indexOf("const STRINGS = ");
const end = src.indexOf("\n};", start);
const STRINGS = new Function(`return (${src.slice(start + "const STRINGS = ".length, end + 2)});`)();

const flat = (o, p = "") =>
  Object.entries(o).flatMap(([k, v]) =>
    v && typeof v === "object" ? flat(v, `${p}${k}.`) : [[`${p}${k}`, v]]);
const holes = (v) => (typeof v === "string" ? [...v.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort() : typeof v);

test("the card speaks English, Russian and Polish", () => {
  assert.deepEqual(Object.keys(STRINGS).sort(), ["en", "pl", "ru"]);
});

for (const lang of ["ru", "pl"]) {
  test(`${lang} has every English key and placeholder`, () => {
    const en = Object.fromEntries(flat(STRINGS.en));
    const other = Object.fromEntries(flat(STRINGS[lang]));
    assert.deepEqual(Object.keys(other).sort(), Object.keys(en).sort());
    for (const [k, v] of Object.entries(en)) assert.deepEqual(holes(other[k]), holes(v), k);
  });
}
