// Shared test utilities (seeded PRNG so property tests are reproducible).

/** mulberry32: small, fast, deterministic PRNG returning floats in [0, 1). */
export function prng(seed) {
  let a = seed >>> 0;
  return function next() {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function randInt(rnd, lo, hi) {
  return lo + Math.floor(rnd() * (hi - lo + 1));
}
