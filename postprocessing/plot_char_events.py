#!/usr/bin/env python3
"""
Visualise one trial recorded in character-event mode (samplingMode "events" or "both").

Input (one of):
  --rows rows.json   JSON array of rows as the app prints them in debug mode. In the browser
                     console: copy(JSON.stringify(window.__motrRows)) and paste into rows.json.
                     A single charEvents row (e.g. the harness's out.row) also works.
  --csv export.csv   magpie export / scripts/simulate_results.py output (one submission per line).

Trial selection: --item ITEM [--condition COND] [--submission ID] or --trial K (K-th charEvents
row found, default 0); --list prints the available trials.

Panels:
  1. reconstructed scanpath: character under the pointer vs time (words as bands); gaps where
     the pointer was on no word / outside the text; layout / visibility markers; the legacy
     50 ms rows overlaid when the same trial also has them ("both" mode)
  2. the recorded layout: character boxes coloured by dwell time, raw pointer trace coloured
     by time, character-change points
  3. dwell time per word
  4. sampling diagnostics: inter-sample intervals of the raw trace, event dts, stats

Usage:
  python postprocessing/plot_char_events.py --rows rows.json --out scanpath.png
  python postprocessing/plot_char_events.py --csv results/exp_0/simulated_export.csv --item 3 --condition obj_rc --show
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import motr_char_events as ce  # noqa: E402

STATE_KINDS = ("c", "n", "o", "e")


# ---------------------------------------------------------------------------
# input

def _parse_results_cell():
    spec = importlib.util.spec_from_file_location("fetch_and_flatten", HERE / "1_fetch_and_flatten.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.parse_results_cell


def load_rows(rows_path: Path | None, csv_path: Path | None) -> list[dict]:
    if rows_path:
        with open(rows_path, encoding="utf-8") as fh:
            data = json.load(fh)
        rows = [data] if isinstance(data, dict) else list(data)
        for r in rows:
            r.setdefault("submission_row_id", 0)
        return rows
    parse = _parse_results_cell()
    rows = []
    csv.field_size_limit(sys.maxsize)          # a submission's `results` cell can exceed 128 KB
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            for r in parse(rec["results"]):
                r["submission_row_id"] = rec.get("id")
                rows.append(r)
    return rows


def _same_trial(a: dict, b: dict) -> bool:
    return (str(a.get("ItemId")) == str(b.get("ItemId")) and str(a.get("Condition")) == str(b.get("Condition"))
            and str(a.get("submission_row_id")) == str(b.get("submission_row_id")))


def select_trial(rows: list[dict], item=None, condition=None, submission=None, trial=0):
    compact = [r for r in rows if ce.is_char_events_row(r)]
    if item is not None:
        compact = [r for r in compact if str(r.get("ItemId")) == str(item)]
    if condition is not None:
        compact = [r for r in compact if str(r.get("Condition")) == str(condition)]
    if submission is not None:
        compact = [r for r in compact if str(r.get("submission_row_id")) == str(submission)]
    if not compact:
        sys.exit("no charEvents row matches (use --list to see what is available)")
    if trial >= len(compact):
        sys.exit(f"--trial {trial}: only {len(compact)} matching trials")
    row = compact[trial]
    legacy = [r for r in rows if ce.is_legacy_sample_row(r) and _same_trial(r, row)]
    return row, legacy


def list_trials(rows: list[dict]):
    for r in rows:
        if ce.is_char_events_row(r):
            try:
                st = ce.decode_stats(r.get("mtStats") or "")
                info = f"{st.get('ne', '?')} events, {st.get('n', '?')} samples, mindt {st.get('mindt', '?')} ms"
            except ce.CharEventsError as e:
                info = f"undecodable ({e})"
            print(f"submission {r.get('submission_row_id')}  item {r.get('ItemId')}  condition {r.get('Condition')}  "
                  f"subject {r.get('SubjectId', '?')}  {info}")


# ---------------------------------------------------------------------------
# analysis

def dwell_by_state(events: list[dict]):
    """(char dwell ms per global index, list of (T_start, T_end, kind, num) state runs)."""
    states = [e for e in events if e["kind"] in STATE_KINDS]
    runs, char_dwell = [], defaultdict(int)
    for cur, nxt in zip(states, states[1:]):
        runs.append((cur["T"], nxt["T"], cur["kind"], cur["num"]))
        if cur["kind"] == "c":
            char_dwell[cur["num"]] += nxt["T"] - cur["T"]
    return char_dwell, runs


def word_dwell(char_dwell: dict, offsets: list[int], n_words: int) -> np.ndarray:
    out = np.zeros(n_words)
    for g, ms in char_dwell.items():
        i, _ = ce.word_of_global(offsets, g)
        out[i] += ms
    return out


# ---------------------------------------------------------------------------
# plotting

def plot_trial(row: dict, legacy: list[dict], out: Path | None, show: bool, dpi: int, layout_id: int | None):
    import matplotlib
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.colors import Normalize
    from matplotlib.patches import Rectangle

    words = ce.words_of(row.get("TrialText") or "")
    fields = {k: row.get(k) or "" for k in ce.MT_FIELDS}
    dec = ce.decode_row(fields)
    events, trace, stats, snapshots = dec["events"], dec["trace"], dec["stats"], dec["snapshots"]
    table = ce.char_table(fields, words)
    offsets = ce.span_offsets(words)
    t0 = int(stats.get("t0", 0))
    T_end = events[-1]["T"] if events else 0
    char_dwell, runs = dwell_by_state(events)
    wdwell = word_dwell(char_dwell, offsets, len(words))
    nbytes = sum(len(v) for v in fields.values())

    # snapshot to draw: the one active for most character events
    by_layout = defaultdict(int)
    for r in table:
        if r["kind"] == "c":
            by_layout[r["layout_id"]] += 1
    if layout_id is None:
        layout_id = max(by_layout, key=by_layout.get) if by_layout else 0
    snap = snapshots[layout_id]

    fig = plt.figure(figsize=(15, 13))
    gs = fig.add_gridspec(3, 3, height_ratios=[1.15, 1.35, 0.8], hspace=0.42, wspace=0.3, top=0.94, bottom=0.07, left=0.07, right=0.97)
    ax_time = fig.add_subplot(gs[0, :])
    ax_lay = fig.add_subplot(gs[1, :])
    ax_word = fig.add_subplot(gs[2, 0])
    ax_iv = fig.add_subplot(gs[2, 1])
    ax_dt = fig.add_subplot(gs[2, 2])

    # ---- 1. scanpath timeline ------------------------------------------------
    sec = lambda T: T / 1000.0  # noqa: E731
    for i, w in enumerate(words):
        lo, hi = offsets[i], offsets[i + 1]
        ax_time.axhspan(lo, hi, color="0.93" if i % 2 else "0.98", lw=0)
    xs, ys = [], []
    for (a, b, kind, num) in runs:
        if kind == "c":
            xs += [sec(a), sec(b), np.nan]
            ys += [num + 0.5, num + 0.5, np.nan]
    ax_time.plot(xs, ys, color="C0", lw=1.6, solid_capstyle="butt", label="character under pointer")
    # vertical connectors between consecutive character runs
    cruns = [r for r in runs if r[2] == "c"]
    for (a, b, _, num), (a2, _, _, num2) in zip(cruns, cruns[1:]):
        if a2 == b:
            ax_time.plot([sec(b), sec(b)], [num + 0.5, num2 + 0.5], color="C0", lw=0.8, alpha=0.7)
    for (a, b, kind, _) in runs:
        if kind == "n":
            ax_time.axvspan(sec(a), sec(b), color="C1", alpha=0.18, lw=0)
        elif kind == "o":
            ax_time.axvspan(sec(a), sec(b), color="0.6", alpha=0.25, lw=0)
    hidden_since = None
    for e in events:
        if e["kind"] == "l":
            ax_time.axvline(sec(e["T"]), color="C3", ls="--", lw=1)
            ax_time.text(sec(e["T"]), offsets[-1], f" layout {e['num']}", color="C3", fontsize=8, va="top")
        elif e["kind"] == "h":
            hidden_since = e["T"]
        elif e["kind"] == "s" and hidden_since is not None:
            ax_time.axvspan(sec(hidden_since), sec(e["T"]), color="C4", alpha=0.2, lw=0)
            hidden_since = None
        elif e["kind"] == "t":
            ax_time.axvline(sec(e["T"]), color="red", lw=1.5)
            ax_time.text(sec(e["T"]), 0, " truncated", color="red", fontsize=8)
    ax_time.axvline(sec(T_end), color="k", lw=1)
    if legacy:
        lt, ly = [], []
        for r in legacy:
            try:
                idx, rt = int(float(r["Index"])), float(r["responseTime"])
            except (TypeError, ValueError, KeyError):
                continue
            lt.append(sec(rt - t0))
            ly.append(-1.5 if idx < 0 else offsets[idx] + (offsets[idx + 1] - offsets[idx]) / 2)
        ax_time.plot(lt, ly, "x", color="C2", ms=4, mew=1, alpha=0.8, label=f"legacy 50 ms rows (n={len(lt)})")
    ax_time.axhspan(-3, 0, color="C1", alpha=0.18, lw=0)
    ax_time.text(0.998, -1.5, "no word (n) ", fontsize=7, va="center", ha="right", transform=ax_time.get_yaxis_transform())
    ticks = [offsets[i] + (offsets[i + 1] - offsets[i]) / 2 for i in range(len(words))]
    step = max(1, len(words) // 30)
    ax_time.set_yticks(ticks[::step])
    ax_time.set_yticklabels(words[::step], fontsize=8)
    ax_time.set_ylim(-3, offsets[-1])
    ax_time.set_xlim(0, sec(T_end) * 1.02 if T_end else 1)
    ax_time.set_xlabel("time since recording start (s)")
    ax_time.set_ylabel("word / character")
    ax_time.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax_time.set_title("Reconstructed scanpath (each step = the pointer moved onto another character; shading: no word / outside text)", fontsize=10)

    # ---- 2. layout with dwell heatmap and raw trace ---------------------------
    B = snap["block"]
    ax_lay.add_patch(Rectangle((B[0], B[1]), B[2] - B[0], B[3] - B[1], fill=False, ec="0.7", lw=1, ls="--"))
    dmax = max(char_dwell.values()) if char_dwell else 1
    norm_d = Normalize(0, dmax)
    cmap_d = plt.get_cmap("YlOrRd")
    for i, w in enumerate(snap["words"]):
        l, t, r, b = w["rect"]
        ax_lay.add_patch(Rectangle((l, t), r - l, b - t, fill=False, ec="0.5", lw=0.6))
        for f in w["frags"]:
            for j in range(len(f["xs"]) - 1):
                g = offsets[i] + f["k0"] + j
                d = char_dwell.get(g, 0)
                x0, x1 = f["xs"][j], f["xs"][j + 1]
                ax_lay.add_patch(Rectangle((x0, f["top"]), x1 - x0, f["bottom"] - f["top"],
                                           fc=cmap_d(norm_d(d)) if d > 0 else "white", ec="0.85", lw=0.4))
                if x1 - x0 >= 4 and i < len(words):
                    ax_lay.text((x0 + x1) / 2, (f["top"] + f["bottom"]) / 2, ce.char_at(words[i], f["k0"] + j),
                                ha="center", va="center", fontsize=7, color="0.25")
    if trace:
        pts = np.array([[p["x"], p["y"]] for p in trace])
        tt = np.array([p["T"] for p in trace])
        segs = np.stack([pts[:-1], pts[1:]], axis=1)
        lc = LineCollection(segs, cmap="viridis", norm=Normalize(0, T_end or 1), lw=1.2, alpha=0.9)
        lc.set_array(tt[:-1])
        ax_lay.add_collection(lc)
        cb = fig.colorbar(lc, ax=ax_lay, pad=0.01, fraction=0.03)
        cb.set_label("trace time (ms)")
    else:
        ax_lay.text(0.5, 0.02, "no raw trace recorded (positions synthesised from character boxes)",
                    transform=ax_lay.transAxes, ha="center", fontsize=8, color="0.4")
    cx = [r["x"] for r in table if r["kind"] == "c"]
    cy = [r["y"] for r in table if r["kind"] == "c"]
    ax_lay.plot(cx, cy, ".", color="k", ms=3, alpha=0.6, label=f"character changes (n={len(cx)})")
    if legacy:
        lx = [float(r["mousePositionX"]) for r in legacy if r.get("mousePositionX") not in (None, "", "NA")]
        lyy = [float(r["mousePositionY"]) for r in legacy if r.get("mousePositionY") not in (None, "", "NA")]
        ax_lay.plot(lx, lyy, "o", mfc="none", mec="C2", ms=5, mew=0.8, alpha=0.8, label="legacy 50 ms samples")
    sm = plt.cm.ScalarMappable(norm=norm_d, cmap=cmap_d)
    cb2 = fig.colorbar(sm, ax=ax_lay, pad=0.01, fraction=0.03)
    cb2.set_label("dwell per character (ms)")
    pad = 15
    ax_lay.set_xlim(B[0] - pad, B[2] + pad)
    ax_lay.set_ylim(B[3] + pad, B[1] - pad)
    ax_lay.set_aspect("equal")
    ax_lay.set_xlabel("x (CSS px, viewport)")
    ax_lay.set_ylabel("y (CSS px)")
    ax_lay.legend(loc="lower right", fontsize=8, framealpha=0.9)
    extra = f" — {len(snapshots)} layouts, showing #{layout_id}" if len(snapshots) > 1 else ""
    ax_lay.set_title(f"Recorded layout, dwell per character and raw pointer trace{extra}", fontsize=10)

    # ---- 3. word dwell --------------------------------------------------------
    ax_word.bar(range(len(words)), wdwell, color="C0")
    ax_word.set_xticks(range(len(words)))
    ax_word.set_xticklabels(words, rotation=90, fontsize=7)
    ax_word.set_ylabel("total dwell (ms)")
    ax_word.set_title("Dwell per word", fontsize=10)

    # ---- 4. diagnostics -------------------------------------------------------
    if len(trace) > 1:
        iv = np.diff([p["T"] for p in trace])
        iv = iv[iv > 0]
        ax_iv.hist(iv, bins=min(60, max(5, int(iv.max()))) if len(iv) else 10, color="C4")
        ax_iv.set_title(f"raw sampling intervals (median {np.median(iv):.0f} ms ≈ {1000 / max(np.median(iv), 1e-9):.0f} Hz)", fontsize=9)
    else:
        ax_iv.set_title("no raw trace", fontsize=9)
    ax_iv.set_xlabel("ms between pointer samples")
    dts = np.array([e["dt"] for e in events if e["kind"] == "c"])
    if len(dts):
        bins = np.logspace(0, np.log10(max(dts.max(), 2)), 40)
        ax_dt.hist(np.clip(dts, 1, None), bins=bins, color="C0")
        ax_dt.set_xscale("log")
    ax_dt.set_xlabel("ms between character changes (log)")
    ax_dt.set_title(f"character-change intervals (n={len(dts)}, median {np.median(dts) if len(dts) else 0:.0f} ms)", fontsize=9)

    info = (f"item {row.get('ItemId')} / {row.get('Condition')} — {len(words)} words · {stats.get('ne')} events · "
            f"{stats.get('n')} pointer samples · {len(snapshots)} layout(s) · {nbytes} bytes · "
            f"mindt {stats.get('mindt')} ms · coalesced {stats.get('coal')} · handler max {stats.get('hmax')} µs · "
            f"reading {T_end / 1000:.2f} s" + ("  ⚠ TRUNCATED" if stats.get("trunc") else ""))
    fig.suptitle(info, fontsize=10)

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=dpi, bbox_inches="tight")
        print(f"wrote {out}")
    if show:
        plt.show()
    plt.close(fig)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--rows", type=Path, help="JSON array of rows (browser debug output)")
    src.add_argument("--csv", type=Path, help="magpie export / simulated export CSV")
    ap.add_argument("--item", help="ItemId of the trial")
    ap.add_argument("--condition", help="Condition of the trial")
    ap.add_argument("--submission", help="submission id (CSV: the id column)")
    ap.add_argument("--trial", type=int, default=0, help="K-th matching charEvents row (default 0)")
    ap.add_argument("--layout", type=int, default=None, help="layout snapshot to draw (default: the most used)")
    ap.add_argument("--list", action="store_true", help="list the charEvents trials in the input and exit")
    ap.add_argument("--out", type=Path, default=None, help="PNG/PDF path (default output/char_events/<item>_<condition>.png)")
    ap.add_argument("--show", action="store_true", help="open an interactive window")
    ap.add_argument("--dpi", type=int, default=130)
    args = ap.parse_args(argv)

    rows = load_rows(args.rows, args.csv)
    if args.list:
        list_trials(rows)
        return 0
    row, legacy = select_trial(rows, args.item, args.condition, args.submission, args.trial)
    out = args.out
    if out is None and not args.show:
        out = ROOT / "output" / "char_events" / f"{row.get('ItemId')}_{row.get('Condition')}_s{row.get('submission_row_id')}.png"
    plot_trial(row, legacy, out, args.show, args.dpi, args.layout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
