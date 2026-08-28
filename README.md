# MoTR experiment template

A blank, ready-to-clone project for **Mouse Tracking for Reading (MoTR)** experiments
(Wilcox, Cui & Ćeplö, 2024). MoTR approximates eye-tracking in the browser: the text is
blurred and a small sharp window follows the mouse, so where the mouse goes is where the
participant reads. The app records which *character* is under the cursor with millisecond
timestamps (from every hardware mouse report, stored as compact change events — or, in the
legacy mode, the word under the cursor every 50 ms), and the postprocessing pipeline turns
those records into fixation-like "associations" and standard reading measures (first-pass,
gaze, go-past, …).

The app is built on [magpie](https://magpie-experiments.org/) (Vue 2), using the
[`magpie-base-MoTR`](https://github.com/cuierd/magpie-base-MoTR) fork.

## Repository layout

```
src/
  config.js                 ← experiment settings (name, lists, practice, question, zoom check …)
  magpie.config.js          ← server settings (experiment ID, server URL, mode, completion URL)
  App.vue                   ← screen flow: consent → browser check → instructions → practice → trials → survey → code
  components/MotrTrial.vue  ← the MoTR reading interface (one trial); records the data
  components/BrowserCheck.vue ← asks for 100% browser zoom before the study
  materials.js              ← loads the CSVs below and builds the trial sequence
  submit.js                 ← the one place that sends data to the server
  browser.js                ← zoom / screen measurements
  main.js                   ← boots Vue + magpie
materials/
  items.csv                 ← all critical items × conditions (source of truth)
  lists/list_NN.csv         ← one list per participant group (generated)
  fillers.csv, practice.csv
  README.md                 ← column spec
scripts/
  make_lists.py             ← Latin-square lists from items.csv
  simulate_results.py       ← fake data to test the pipeline
  update_magpie.sh          ← reinstall the magpie fork
  vue-cli.js                ← wrapper that makes Vue CLI 4 run on modern Node
postprocessing/
  run_pipeline.py           ← ONE command: raw export → reading_measures_all.csv (installs Python deps itself)
  1_fetch_and_flatten.py    ← raw submissions → flat sample CSV
  2_compute_reading_measures.py ← MoTR pipeline → per-participant reading measures
  3_aggregate.py            ← one analysis-ready CSV
  READING_MEASURES.md       ← exact definition of every reading measure (read before analysing)
  plot_trial_mouse_overlay.py, utils/, README.md
results/                    ← downloaded / flattened data   (git-ignored)
output/                     ← pipeline output               (git-ignored)
.github/workflows/          ← build & deploy to GitHub Pages on push
```

## Quick start

```bash
git clone <this repo> my-experiment && cd my-experiment
npm install                 # Node 16 recommended (.nvmrc); 18–22 work via scripts/vue-cli.js
npm run serve               # http://localhost:8080  (mode: "debug" → nothing is sent anywhere)
```

Open the browser console to see the trial sequence and, in debug mode, the rows that
would be submitted.

## Setting up a new experiment

1. **Materials** – edit `materials/items.csv`, `fillers.csv`, `practice.csv` (schema in
   `materials/README.md`), then `python scripts/make_lists.py`. Rebuild after any change.
2. **Settings** – `src/config.js`: experiment name, practice/filler counts, the post-sentence
   question (per-item questions go in the CSV), zoom check, completion code. Then
   `src/magpie.config.js`: the server that receives the data (`serverUrl`), the experiment
   ID you created there, and `mode` (see *Where the data goes*).
3. **Text** – consent form and instructions in `src/App.vue` (look for `[INSTITUTION]`,
   `[DURATION]`, `[IRB / ETHICS COMMITTEE]`).
4. **Test** – `npm run serve`, run through the experiment, check the console output. Try
   `?LIST_ID=2` to force a list.
5. **Deploy** – push to GitHub `main`; the workflow builds and publishes to the `gh-pages`
   branch (enable Pages → branch `gh-pages` in the repo settings). The study URL is
   `https://<user>.github.io/<repo>/?LIST_ID=1`. Alternatively `npm run build` and host
   `dist/` anywhere (`npm start` serves it with Express).
6. **Recruit** – with `mode: "prolific"`, add `&PROLIFIC_PID={{%PROLIFIC_PID%}}` to the study
   URL; the ID is pre-filled on the consent screen and participants are redirected to
   `completionUrl` at the end. One Prolific study per list, or `defaultList: "random"`.
7. **Analyse** – download the results from the server and run one command
   (see `postprocessing/README.md` for the step-by-step version):

   ```bash
   python3 postprocessing/run_pipeline.py --experiment-id 42 --csv results/raw/export.csv
   ```

## Where the data goes

Every trial's rows are sent as soon as the trial ends (`submitEachTrial` in `config.js`),
and the survey row at the very end, by `src/submit.js`:

```
POST {serverUrl}/api/submit_experiment/{experimentId}      body: JSON array of rows
```

`serverUrl` and `experimentId` live in `src/magpie.config.js`, so any magpie backend
(magpie-serverless, a self-hosted magpie server) is a one-line change. To send the data
somewhere else entirely, replace the body of `submitRows()` in `src/submit.js` — that is
the only place data leaves the browser. In `debug` mode nothing is sent; the rows are
printed to the browser console.

## Browser check

MoTR's window and word boxes are defined in CSS pixels, so browser zoom changes their
physical size. After consent, a check screen asks participants to set the zoom to 100 %
(Ctrl/⌘ + 0) and only continues once it is (estimated from
`window.outerWidth / window.innerWidth`, which tracks zoom in desktop Chrome, Firefox and
Edge; a "continue anyway" link appears after 30 s in case the estimate is wrong on some
setup). The zoom level, device pixel ratio and window size are recorded with every trial
(`zoomPercent`, `devicePixelRatio`, `windowInnerWidth/Height`) and screen size / user agent
in the survey row, so you can also filter afterwards. Settings: `browserCheck` in
`src/config.js`.

## How the interface works

`MotrTrial.vue` renders the sentence twice, exactly overlaid: a blurred black copy and a
sharp white copy split into one `<span>` per word. A white oval with
`mix-blend-mode: difference` follows the cursor, inverting the white text to black and
cancelling the blur under it – the moving "window". Because the spans receive the mouse
events, `document.elementFromPoint` tells us which word is under the cursor.

What gets recorded depends on `samplingMode` in `src/config.js`:

- **`"events"` (default)** — the character-event recorder (`src/charEvents/`). When a trial
  starts, the box of every character is measured once (with DOM `Range`s over the existing
  word spans, so nothing about the rendering changes). Every pointer sample the hardware
  delivers (`pointermove` + `getCoalescedEvents()`, typically 125–1000 Hz) is hit-tested
  against those boxes with the same rule the legacy sampler uses (`(x, y)`, then
  `(x, y − 3)`, else "no word"), and only *changes* of the character under the cursor are
  kept, with their millisecond timestamps. Optionally every raw sample is kept too, delta-coded
  (~3 bytes each). The layout is re-measured on resize/scroll/zoom/font load. "Done Reading"
  closes the recording and stores **one row per trial** (`TrialType = "charEvents"`, fields
  `mtFormat/mtLayout/mtEvents/mtTrace/mtStats`; format spec: `src/charEvents/FORMAT.md`).
  A typical trial is ~5–10 KB instead of ~60–100 KB.
- **`"interval"`** — the original sampler: every `sampleIntervalMs` while the cursor is over
  the text, a row is recorded with `Index`/`Word`, the word's bounding box, and the mouse
  position; magpie adds `responseTime`. "Done Reading" records an end-of-reading marker
  (`Index = -1`) so the last word's fixation can be closed.
- **`"both"`** — both at once, for validation studies.

`postprocessing/1_fetch_and_flatten.py` expands charEvents rows back into the classic
per-sample rows (one row per character change, plus the marker), so the rest of the pipeline
is identical for all modes; it also writes a character-level table.

In every mode, after "Done Reading" the question is shown. "Next" records a trial-summary
row and, with `submitEachTrial`, immediately sends that trial's rows to the server (per-trial
submission means a dropout still leaves usable data). See the comment block at the top of
`MotrTrial.vue` for the full column list.

Layout details that the data depends on: `font-size: 18px; line-height: 40px;` and
`padding: 2% 11%` on both text layers. Keep the two layers identical if you restyle.

## Data format

Each submission is one JSON array of rows. Its **first row** carries the experiment-level data
(`SubjectId`, `ListId`, `Experiment`, `experiment_start_time`, …): magpie itself only puts that
on the first row of *all* recorded data, so `src/submit.js` adds it to every per-trial submission
and to the survey row (step 1 spreads it over the submission's other rows). Rows hold either sample columns,
the per-trial `charEvents` fields (`samplingMode: "events"`; see `src/charEvents/FORMAT.md`)
or summary columns; magpie fills absent columns with `"NA"`. `1_fetch_and_flatten.py`
produces the flat CSV documented in `postprocessing/README.md`.

## Tests

```bash
npm test                     # JS unit tests (node:test, Node >= 22): codecs, hit test,
                             #   recorder, decoder, legacy equivalence, cross-language fixtures,
                             #   and a headless-Chrome check when Chrome is installed
npm run test:perf            # strict throughput / payload-size thresholds
python -m pip install -r postprocessing/requirements-dev.txt
python -m pytest postprocessing          # Python decoder + pipeline tests (add -m slow for the
                                         #   end-to-end run over simulated data)
```

The JS and Python implementations of the `motr-ce/1` format are pinned to each other by
`test/fixtures/*.json`: scenarios encoded on one side must decode — and re-encode
byte-for-byte — on the other. Regenerate with `npm run fixtures` /
`MOTR_WRITE_FIXTURES=1 python -m pytest postprocessing` after changing the format.
`.github/workflows/test.yml` runs everything on push.

## Requirements

- Node 16 (see `.nvmrc`); newer versions work because `scripts/vue-cli.js` adds
  `--openssl-legacy-provider`. npm ≥ 7 (installs magpie's peer dependencies).
- Python ≥ 3.9 for postprocessing; `run_pipeline.py` installs `pandas`/`numpy`/`matplotlib`
  into a private `.venv/` by itself.

## References

Wilcox, E. G., Cui, D., & Ćeplö, S. (2024). Mouse Tracking for Reading (MoTR): A new
naturalistic incremental processing measurement tool. *Journal of Memory and Language*.
