// Character-level layout table and hit testing (pure, no DOM).
//
// A layout *table* describes where every character of the reading text is on screen:
//   { block: [l,t,r,b],                       // .readingText bounding rect
//     words: [ { rect: [l,t,r,b],             // span i bounding rect (legacy wordPosition*)
//                frags: [ { k0, top, bottom, xs: [x0, x1, ...] } ] } ] }
// Fragment: consecutive non-zero-width characters of one span on one line, starting at
// local character index k0; character k0+j occupies [xs[j], xs[j+1]) x [top, bottom).
// Local index k of span i: 0 = leading space, 1..len = code points, len+1 = trailing space.
// Global index g = spanOffsets(words)[i] + k.
//
// hitState() reproduces the legacy sampler exactly: outside the block -> OUT; character at
// (x, y); else at (x, y-3) ("look slightly above so the line above still counts"); else NONE.

export const OUT = -2;
export const NONE = -1;
export const LOOK_ABOVE_PX = 3;

/** Number of code points in a word (what Array.from counts; Python: len(word)). */
export function wordLength(word) {
  return Array.from(word).length;
}

/**
 * Global offsets of each span, plus the total as a final element: offsets.length === n + 1.
 * Span i covers global indices [offsets[i], offsets[i+1]).
 */
export function spanOffsets(words) {
  const offsets = new Array(words.length + 1);
  let off = 0;
  for (let i = 0; i < words.length; i++) {
    offsets[i] = off;
    off += wordLength(words[i]) + 2;
  }
  offsets[words.length] = off;
  return offsets;
}

export function globalIndex(offsets, i, k) {
  return offsets[i] + k;
}

/** Map a global index to {i, k}; throws if out of range. */
export function wordOfGlobal(offsets, g) {
  const n = offsets.length - 1;
  if (!Number.isInteger(g) || g < 0 || g >= offsets[n]) throw new RangeError(`global index ${g} out of range`);
  let lo = 0, hi = n - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (offsets[mid] <= g) lo = mid;
    else hi = mid - 1;
  }
  return { i: lo, k: g - offsets[lo] };
}

/** The character at local index k of `word` (" " for the padding spaces). */
export function charAt(word, k) {
  const cps = Array.from(word);
  if (k === 0 || k === cps.length + 1) return " ";
  return cps[k - 1];
}

/** Box [l,t,r,b] of global character g in `table`, or null if it has no box (zero-width). */
export function charBox(table, offsets, g) {
  const { i, k } = wordOfGlobal(offsets, g);
  const word = table.words[i];
  if (!word) return null;
  for (const f of word.frags) {
    const j = k - f.k0;
    if (j >= 0 && j < f.xs.length - 1) return [f.xs[j], f.top, f.xs[j + 1], f.bottom];
  }
  return null;
}

/**
 * Build a search index over a table. Fragments are grouped into vertical bands by
 * (top, bottom); bands are sorted by top then bottom; fragments in a band by their left x.
 */
export function buildIndex(table) {
  const bands = new Map();
  table.words.forEach((w, i) => {
    for (const f of w.frags) {
      if (f.xs.length < 2) continue;
      const key = `${f.top},${f.bottom}`;
      if (!bands.has(key)) bands.set(key, { top: f.top, bottom: f.bottom, frags: [] });
      bands.get(key).frags.push({ i, k0: f.k0, xs: f.xs, left: f.xs[0], right: f.xs[f.xs.length - 1] });
    }
  });
  const list = [...bands.values()];
  list.sort((a, b) => a.top - b.top || a.bottom - b.bottom);
  for (const b of list) {
    b.frags.sort((p, q) => p.left - q.left || p.i - q.i || p.k0 - q.k0);
    b.lefts = Float64Array.from(b.frags, (f) => f.left);
  }
  return { bands: list, block: table.block };
}

/** Largest index j with arr[j] <= x, or -1. */
function upperIndex(arr, x) {
  let lo = 0, hi = arr.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (arr[mid] <= x) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans;
}

/**
 * Character at (x, y) as {i, k} or null. Half-open boxes: [x_j, x_{j+1}) x [top, bottom).
 * Overlapping fragments (should not happen) resolve to the right-most starting one.
 */
export function hitCharIK(index, x, y) {
  const bands = index.bands;
  for (let b = 0; b < bands.length; b++) {
    const band = bands[b];
    if (y < band.top) break;               // bands sorted by top; later bands start lower
    if (y >= band.bottom) continue;
    let fi = upperIndex(band.lefts, x);
    for (; fi >= 0; fi--) {
      const f = band.frags[fi];
      if (x < f.right) {
        const j = upperIndex(f.xs, x);       // xs sorted ascending
        if (j >= 0 && j < f.xs.length - 1) return { i: f.i, k: f.k0 + j };
      }
      // x beyond this fragment's right edge: an earlier (further left) fragment cannot
      // contain it unless fragments overlap; keep scanning only while lefts are equal.
      if (fi > 0 && band.lefts[fi - 1] < band.lefts[fi]) break;
    }
  }
  return null;
}

/**
 * Legacy-equivalent state for a pointer position:
 *   OUT (-2)  outside the text block (legacy records nothing),
 *   NONE (-1) inside the block but on no character (legacy Index = -1),
 *   g >= 0    global character index.
 */
export function hitState(index, offsets, x, y) {
  const B = index.block;
  if (!(x >= B[0] && x < B[2] && y >= B[1] && y < B[3])) return OUT;
  let ik = hitCharIK(index, x, y);
  if (!ik) ik = hitCharIK(index, x, y - LOOK_ABOVE_PX);
  if (!ik) return NONE;
  return offsets[ik.i] + ik.k;
}

/** Compare two tables number-by-number with tolerance `eps` (default 0.05 px). */
export function tablesEqual(a, b, eps = 0.05) {
  const close = (p, q) => Math.abs(p - q) <= eps;
  const rectEq = (p, q) => p.length === 4 && q.length === 4 && p.every((v, i) => close(v, q[i]));
  if (!rectEq(a.block, b.block)) return false;
  if (a.words.length !== b.words.length) return false;
  for (let i = 0; i < a.words.length; i++) {
    const wa = a.words[i], wb = b.words[i];
    if (!rectEq(wa.rect, wb.rect)) return false;
    if (wa.frags.length !== wb.frags.length) return false;
    for (let j = 0; j < wa.frags.length; j++) {
      const fa = wa.frags[j], fb = wb.frags[j];
      if (fa.k0 !== fb.k0 || !close(fa.top, fb.top) || !close(fa.bottom, fb.bottom)) return false;
      if (fa.xs.length !== fb.xs.length) return false;
      for (let m = 0; m < fa.xs.length; m++) if (!close(fa.xs[m], fb.xs[m])) return false;
    }
  }
  return true;
}
