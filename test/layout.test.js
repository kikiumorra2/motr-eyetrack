import { test } from "node:test";
import assert from "node:assert/strict";
import {
  OUT, NONE, spanOffsets, globalIndex, wordOfGlobal, charAt, charBox, wordLength,
  buildIndex, hitCharIK, hitState, tablesEqual,
} from "../src/charEvents/layout.js";
import { prng, randInt, checkFixture } from "./helpers.js";

import { WORDS, TABLE } from "./sample-layout.js";

const OFF = spanOffsets(WORDS);
const IDX = buildIndex(TABLE);
const g = (i, k) => globalIndex(OFF, i, k);

test("span offsets and global <-> (i, k) mapping", () => {
  assert.deepEqual(OFF, [0, 5, 10, 15, 24, 28, 33, 39]);
  assert.equal(wordLength("wrapped"), 7);
  assert.equal(wordLength("naïve"), 5);
  assert.equal(wordLength("a😀b"), 3); // code points, not UTF-16 units
  for (let gi = 0; gi < OFF[WORDS.length]; gi++) {
    const { i, k } = wordOfGlobal(OFF, gi);
    assert.equal(globalIndex(OFF, i, k), gi);
    assert.ok(k >= 0 && k <= wordLength(WORDS[i]) + 1);
  }
  assert.deepEqual(wordOfGlobal(OFF, 0), { i: 0, k: 0 });
  assert.deepEqual(wordOfGlobal(OFF, 4), { i: 0, k: 4 });
  assert.deepEqual(wordOfGlobal(OFF, 5), { i: 1, k: 0 });
  assert.deepEqual(wordOfGlobal(OFF, 38), { i: 6, k: 5 });
  assert.throws(() => wordOfGlobal(OFF, 39), RangeError);
  assert.throws(() => wordOfGlobal(OFF, -1), RangeError);
  assert.equal(charAt("The", 0), " ");
  assert.equal(charAt("The", 1), "T");
  assert.equal(charAt("The", 3), "e");
  assert.equal(charAt("The", 4), " ");
  assert.deepEqual(spanOffsets([]), [0]);
});

test("half-open boundaries in x", () => {
  // "The": T=[120,130) h=[130,140) e=[140,150) space=[150,160)
  assert.equal(hitState(IDX, OFF, 120, 190), g(0, 1));
  assert.equal(hitState(IDX, OFF, 129.99, 190), g(0, 1));
  assert.equal(hitState(IDX, OFF, 130, 190), g(0, 2));
  assert.equal(hitState(IDX, OFF, 149.99, 190), g(0, 3));
  assert.equal(hitState(IDX, OFF, 150, 190), g(0, 4));       // trailing space of "The"
  assert.equal(hitState(IDX, OFF, 159.99, 190), g(0, 4));
  assert.equal(hitState(IDX, OFF, 160, 190), g(1, 1));       // "c" of "cat"
  assert.equal(hitState(IDX, OFF, 229.99, 190), g(2, 3));    // "t" of "sat"
  assert.equal(hitState(IDX, OFF, 230, 190), NONE);          // past the line end, inside block
  assert.equal(hitState(IDX, OFF, 119.99, 190), NONE);       // left of the first glyph
});

test("half-open boundaries in y and the look-3px-above rule", () => {
  assert.equal(hitState(IDX, OFF, 125, 180), g(0, 1));       // top inclusive
  assert.equal(hitState(IDX, OFF, 125, 179.99), NONE);       // above the band, y-3 also misses
  assert.equal(hitState(IDX, OFF, 125, 200.99), g(0, 1));    // bottom exclusive
  assert.equal(hitState(IDX, OFF, 125, 201), g(0, 1));       // misses, but y-3 = 198 hits
  assert.equal(hitState(IDX, OFF, 125, 203.99), g(0, 1));    // y-3 = 200.99 still hits
  assert.equal(hitState(IDX, OFF, 125, 204), NONE);          // y-3 = 201 misses
  assert.equal(hitState(IDX, OFF, 125, 219), NONE);          // gap between lines
  assert.equal(hitState(IDX, OFF, 125, 220), g(3, 1));       // "w" on line 2
});

test("zero-width leading spaces are never hit; wrapped word has two fragments", () => {
  for (let gi = 0; gi < OFF[WORDS.length]; gi++) {
    const { k } = wordOfGlobal(OFF, gi);
    if (k === 0) assert.equal(charBox(TABLE, OFF, gi), null);
  }
  assert.deepEqual(charBox(TABLE, OFF, g(3, 1)), [120, 220, 130, 241]);  // "w"
  assert.deepEqual(charBox(TABLE, OFF, g(3, 4)), [120, 260, 130, 281]);  // "p" on the next line
  assert.deepEqual(charBox(TABLE, OFF, g(3, 8)), [160, 260, 170, 281]);  // trailing space of "wrapped"
  assert.equal(charBox(TABLE, OFF, g(2, 4)), null);                       // omitted trailing space
  assert.equal(hitState(IDX, OFF, 145, 230), g(3, 3));                    // "a" line 2
  assert.equal(hitState(IDX, OFF, 165, 270), g(3, 8));                    // trailing space line 3
  assert.equal(hitState(IDX, OFF, 175, 270), g(4, 1));                    // "o" of "on"
});

test("outside the block", () => {
  assert.equal(hitState(IDX, OFF, 99.99, 190), OUT);
  assert.equal(hitState(IDX, OFF, 100, 190), NONE);
  assert.equal(hitState(IDX, OFF, 500, 190), OUT);
  assert.equal(hitState(IDX, OFF, 499.99, 190), NONE);
  assert.equal(hitState(IDX, OFF, 125, 149.99), OUT);
  assert.equal(hitState(IDX, OFF, 125, 300), OUT);
  assert.equal(hitState(IDX, OFF, 125, 152), NONE);
  assert.equal(hitState(IDX, OFF, NaN, 190), OUT);
});

test("empty word list and words without fragments", () => {
  const empty = buildIndex({ block: [0, 0, 10, 10], words: [] });
  assert.equal(hitState(empty, spanOffsets([]), 5, 5), NONE);
  assert.equal(hitState(empty, spanOffsets([]), 50, 5), OUT);
  const nofrag = buildIndex({ block: [0, 0, 10, 10], words: [{ rect: [1, 1, 2, 2], frags: [] }] });
  assert.equal(hitState(nofrag, spanOffsets(["x"]), 1.5, 1.5), NONE);
});

test("overlapping fragments resolve deterministically (right-most starting wins)", () => {
  const t = {
    block: [0, 0, 100, 100],
    words: [
      { rect: [10, 10, 40, 20], frags: [{ k0: 1, top: 10, bottom: 20, xs: [10, 20, 30, 40] }] },
      { rect: [25, 10, 55, 20], frags: [{ k0: 1, top: 10, bottom: 20, xs: [25, 35, 45, 55] }] },
    ],
  };
  const off = spanOffsets(["abc", "def"]);
  const idx = buildIndex(t);
  assert.equal(hitState(idx, off, 27, 15), globalIndex(off, 1, 1)); // both contain 27; word 1 starts further right
  assert.equal(hitState(idx, off, 22, 15), globalIndex(off, 0, 2));
  assert.equal(hitState(idx, off, 50, 15), globalIndex(off, 1, 3));
  // identical lefts: still deterministic
  const t2 = { block: [0, 0, 100, 100], words: [
    { rect: [10, 10, 40, 20], frags: [{ k0: 1, top: 10, bottom: 20, xs: [10, 20] }] },
    { rect: [10, 10, 40, 20], frags: [{ k0: 1, top: 10, bottom: 20, xs: [10, 30] }] },
  ] };
  assert.equal(hitState(buildIndex(t2), spanOffsets(["a", "b"]), 25, 15), globalIndex(spanOffsets(["a", "b"]), 1, 1));
});

test("hitState agrees with a brute-force scan over every character box", () => {
  const rnd = prng(2024);
  const boxes = [];
  TABLE.words.forEach((w, i) => w.frags.forEach((f) => {
    for (let j = 0; j < f.xs.length - 1; j++) boxes.push({ g: g(i, f.k0 + j), l: f.xs[j], t: f.top, r: f.xs[j + 1], b: f.bottom });
  }));
  const brute = (x, y) => {
    const B = TABLE.block;
    if (!(x >= B[0] && x < B[2] && y >= B[1] && y < B[3])) return OUT;
    for (const yy of [y, y - 3]) {
      const hit = boxes.find((bx) => x >= bx.l && x < bx.r && yy >= bx.t && yy < bx.b);
      if (hit) return hit.g;
    }
    return NONE;
  };
  for (let n = 0; n < 20000; n++) {
    const x = 90 + rnd() * 420, y = 140 + rnd() * 170;
    assert.equal(hitState(IDX, OFF, x, y), brute(x, y), `at (${x}, ${y})`);
  }
});

test("tablesEqual tolerance", () => {
  const copy = JSON.parse(JSON.stringify(TABLE));
  assert.ok(tablesEqual(TABLE, copy));
  copy.words[3].frags[1].xs[2] += 0.04;
  assert.ok(tablesEqual(TABLE, copy));
  copy.words[3].frags[1].xs[2] += 0.02;
  assert.ok(!tablesEqual(TABLE, copy));
  const fewer = JSON.parse(JSON.stringify(TABLE)); fewer.words.pop();
  assert.ok(!tablesEqual(TABLE, fewer));
  const shifted = JSON.parse(JSON.stringify(TABLE)); shifted.block[1] -= 1;
  assert.ok(!tablesEqual(TABLE, shifted));
});

test("shared hit-test fixture for the Python implementation", () => {
  const rnd = prng(77);
  const cases = [];
  const push = (x, y) => cases.push({ x, y, state: hitState(IDX, OFF, x, y) });
  // exact boundary points
  TABLE.words.forEach((w) => w.frags.forEach((f) => {
    for (const x of f.xs) for (const y of [f.top, f.bottom - 0.1, f.bottom, f.bottom + 2.9, f.bottom + 3]) push(x, y);
  }));
  for (let n = 0; n < 400; n++) push(Math.round((90 + rnd() * 420) * 10) / 10, Math.round((140 + rnd() * 170) * 10) / 10);
  checkFixture("js_hittest.json", { words: WORDS, table: TABLE, offsets: OFF, cases }, assert);
});
