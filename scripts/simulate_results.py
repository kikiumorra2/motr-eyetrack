#!/usr/bin/env python3
"""
Generate fake MoTR data in the format the magpie server exports, so the postprocessing
pipeline can be tested before any real data is collected.

Each participant reads practice items, then one list plus the fillers. Per trial, one
submission (one row of the export) is produced - exactly like the app with
`submitEachTrial: true` - followed by one submission with the survey answers.

Usage:
  python scripts/simulate_results.py --experiment-id 0 --n-participants 3
  python postprocessing/1_fetch_and_flatten.py --experiment-id 0 --csv results/exp_0/simulated_export.csv
"""
import argparse
import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINE_HEIGHT, CHAR_WIDTH, LEFT, TOP, LINE_CHARS = 40, 10, 120, 180, 60


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def layout(words):
    """Fake bounding boxes: words laid out left-to-right, wrapping every LINE_CHARS chars."""
    boxes, x, line = [], 0, 0
    for w in words:
        if x + len(w) > LINE_CHARS:
            x, line = 0, line + 1
        left = LEFT + x * CHAR_WIDTH
        top = TOP + line * LINE_HEIGHT
        boxes.append((left, top, left + len(w) * CHAR_WIDTH, top + LINE_HEIGHT))
        x += len(w) + 1
    return boxes


def simulate_trial(rng, trial, trial_idx, exp_data, sample_ms, options):
    words = trial["text"].split()
    boxes = layout(words)
    base = {"Experiment": exp_data["Experiment"], "Condition": trial["condition_id"], "ItemId": trial["item_id"]}
    rows, t = [], 500
    path = list(range(len(words)))
    # occasional regression: jump back 1-3 words and re-read
    for i in range(2, len(words)):
        if rng.random() < 0.15:
            back = rng.randint(1, min(3, i))
            path[i:i] = list(range(i - back, i))
    for idx in path:
        left, top, right, bottom = boxes[idx]
        dwell = int(rng.lognormvariate(5.6, 0.4))  # ~270 ms median
        for _ in range(max(1, dwell // sample_ms)):
            rows.append({**base, "Index": idx, "Word": words[idx], "responseTime": t,
                         "mousePositionX": rng.uniform(left, right), "mousePositionY": rng.uniform(top + 10, bottom - 10),
                         "wordPositionTop": top, "wordPositionLeft": left, "wordPositionBottom": bottom, "wordPositionRight": right})
            t += sample_ms
    rows.append({**base, "Index": -1, "responseTime": t, "mousePositionX": rows[-1]["mousePositionX"], "mousePositionY": rows[-1]["mousePositionY"]})
    opts = trial["options"].split("|") if trial.get("options") else options
    response = trial["correct"] if trial.get("correct") and rng.random() < 0.9 else rng.choice(opts)
    rows.append({**base, "TrialId": trial_idx, "TrialType": "trial", "Phase": "practice" if trial["condition_id"] == "practice" else "main",
                 "TrialText": trial["text"], "userResponse": response, "correctResponse": trial.get("correct") or "NA",
                 "readingTime": t - 500, "ListId": exp_data["ListId"], "responseTime": t + 1500,
                 "zoomPercent": 100, "devicePixelRatio": 2, "windowInnerWidth": 1440, "windowInnerHeight": 900})
    return rows


def finalize(rows, exp_data):
    """Mimic magpie: merge expData into every row and fill missing columns with 'NA'."""
    cols = set(exp_data)
    for r in rows:
        cols |= set(r)
    return [{**{c: "NA" for c in cols}, **exp_data, **r} for r in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--experiment-id", default="0")
    parser.add_argument("--n-participants", type=int, default=3)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, default=None, help="default: results/exp_<ID>/simulated_export.csv")
    args = parser.parse_args()
    rng = random.Random(args.seed)

    materials = ROOT / "materials"
    lists = sorted(materials.glob("lists/list_*.csv"))
    fillers, practice = read(materials / "fillers.csv"), read(materials / "practice.csv")
    options = ["I noticed an error", "Not sure", "Sentence was OK"]

    out = args.out or ROOT / "results" / f"exp_{args.experiment_id}" / "simulated_export.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    submissions, row_id = [], 1
    for p in range(args.n_participants):
        list_path = lists[p % len(lists)]
        list_id = int(list_path.stem.split("_")[1])
        subject = f"{rng.getrandbits(96):024x}"  # Prolific-style 24-hex ID
        start = 1_700_000_000_000 + p * 3_600_000
        exp_data = {"SubjectId": subject, "ListId": list_id, "Experiment": "motr_template",
                    "experiment_start_time": start, "experiment_end_time": start + 900_000, "experiment_duration": 900_000}
        main_trials = fillers[:2] + rng.sample(read(list_path) + fillers[2:], len(read(list_path)) + len(fillers) - 2)
        for i, trial in enumerate(practice + main_trials):
            rows = finalize(simulate_trial(rng, trial, i, exp_data, 50, options), exp_data)
            submissions.append((row_id, rows)); row_id += 1
        survey = finalize([{"Experiment": "motr_template", "TrialType": "survey", "responseTime": 20000,
                            "device": rng.choice(["Computer Mouse", "Computer Trackpad"]), "hand": "Right", "feedback": "simulated",
                            "zoomPercent": 100, "devicePixelRatio": 2, "screenWidth": 1440, "screenHeight": 900,
                            "windowInnerWidth": 1440, "windowInnerHeight": 900, "userAgent": "simulated"}], exp_data)
        submissions.append((row_id, survey)); row_id += 1

    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "inserted_at", "updated_at", "experiment_id", "results", "variant", "chain", "generation", "is_intermediate", "player"])
        for rid, rows in submissions:
            w.writerow([rid, "2026-01-01 12:00:00", "2026-01-01 12:00:00", args.experiment_id, json.dumps(rows), "", "", "", "false", ""])
    print(f"wrote {out}: {args.n_participants} participants, {len(submissions)} submissions")


if __name__ == "__main__":
    main()
