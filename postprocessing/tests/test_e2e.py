"""End-to-end: simulate exports in both formats from the same pointer paths, run steps
1→3 on each (in a temp dir), and compare the final reading measures.

  legacy  ==  events + `--char-events expand --resample 50`   (byte-identical)
  legacy  ~=  events (raw millisecond events)                  (within 50 ms quantization)
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
PP = ROOT / "postprocessing"
PY = sys.executable
KEY = ["submission_id", "item_id", "condition_id", "word_nr"]
DURATIONS = ["first_duration", "total_duration", "gaze_duration", "first_pass_duration", "right_bounded_rt", "go_past_time"]
BINARY = ["FPFix", "FPReg", "RegIn_excl", "RegIn_incl"]


def run(*args):
    subprocess.run([PY] + [str(a) for a in args], check=True, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def pipeline(tmp, name, export, *step1_args):
    res, out = tmp / f"res_{name}", tmp / f"out_{name}"
    run(PP / "1_fetch_and_flatten.py", "--experiment-id", "0", "--csv", export, "--out-dir", res, *step1_args)
    in_file = next(res.glob("results_processed_exp_0_*.csv"))
    run(PP / "2_compute_reading_measures.py", "--experiment-id", "0", "--in-file", in_file,
        "--trial-file", res / "items_processed.csv", "--out-dir", out)
    run(PP / "3_aggregate.py", "--experiment-id", "0", "--out-dir", out,
        "--participants", next(res.glob("participants_exp_0_*.csv")))
    return pd.read_csv(out / "exp_0" / "reading_measures_all.csv")


@pytest.mark.slow
def test_pipeline_equivalence(tmp_path):
    exports = {}
    for fmt in ("legacy", "events", "both"):
        exports[fmt] = tmp_path / f"{fmt}.csv"
        run(ROOT / "scripts" / "simulate_results.py", "--experiment-id", "0", "--n-participants", "2",
            "--seed", "11", "--format", fmt, "--out", exports[fmt])
    assert exports["events"].stat().st_size * 5 < exports["legacy"].stat().st_size  # far smaller

    legacy = pipeline(tmp_path, "legacy", exports["legacy"])
    resampled = pipeline(tmp_path, "resampled", exports["events"], "--char-events", "expand", "--resample", "50")
    raw = pipeline(tmp_path, "raw", exports["events"], "--char-events", "expand")
    both_auto = pipeline(tmp_path, "both_auto", exports["both"])                     # auto → legacy rows
    both_expand = pipeline(tmp_path, "both_expand", exports["both"], "--char-events", "expand")

    assert len(legacy) > 100 and set(KEY + DURATIONS + BINARY) <= set(legacy.columns)
    # 1) resampling the events at the legacy interval reproduces the legacy pipeline exactly
    pd.testing.assert_frame_equal(legacy, resampled)
    pd.testing.assert_frame_equal(legacy, both_auto)
    pd.testing.assert_frame_equal(raw, both_expand)

    # 2) raw millisecond events: same words, durations within the 50 ms quantization noise
    m = legacy.merge(raw, on=KEY, suffixes=("_l", "_r"))
    assert len(m) == len(legacy) == len(raw)
    for c in DURATIONS:
        a, b = m[c + "_l"].fillna(0), m[c + "_r"].fillna(0)
        r = np.corrcoef(a, b)[0, 1]
        assert r > 0.9, f"{c}: r={r:.3f}"
        assert np.abs(a - b).mean() < 60, f"{c}: mean |diff| {np.abs(a - b).mean():.1f} ms"
    for c in BINARY:
        same = (m[c + "_l"].fillna(-1) == m[c + "_r"].fillna(-1)).mean()
        assert same > 0.9, f"{c}: identical for {same:.1%} of words"

    # 3) the character table is produced and consistent
    char = pd.read_csv(next((tmp_path / "res_raw").glob("char_events_exp_0_*.csv")))
    assert {"submission_id", "ItemId", "t", "kind", "word_idx", "char_idx", "char", "layout_id"} <= set(char.columns)
    n_trials = char.groupby(["submission_id", "ItemId"]).ngroups
    assert n_trials >= 20 and (char["kind"] == "e").sum() == n_trials                 # one end event per trial
    assert (char.loc[char["kind"] == "c", "char_idx"] >= 1).all()
