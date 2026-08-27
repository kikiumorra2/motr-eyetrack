/**
 * Experiment-level settings.
 *
 * Together with materials/ and src/magpie.config.js, this file is what you edit for a new
 * MoTR experiment. Consent/instruction text lives in src/App.vue.
 */
export default {
  // Recorded in every data row as `Experiment`. Use a short, unique slug per experiment.
  experimentName: "motr_template",

  // Completion code shown on the final screen. Must match completionUrl in magpie.config.js.
  completionCode: "XXXXXXXX",

  // Which list to use when the URL has no ?LIST_ID=N parameter.
  // "random" picks uniformly among materials/lists/list_*.csv; a number picks that list.
  defaultList: "random",

  // Number of items from materials/practice.csv to show before the main trials (0 = none).
  nPractice: 2,

  // Number of fillers (taken from the top of materials/fillers.csv) that are always shown
  // first, unshuffled, so participants warm up on easy sentences.
  nLeadingFillers: 2,

  // Shuffle the critical items and remaining fillers.
  shuffleTrials: true,

  // Question asked after each sentence. If an item has its own `question`/`options`
  // columns in the materials CSV, those are used instead. Set enabled: false to go
  // straight to the next sentence after "Done Reading" (unless the item has a question).
  question: {
    enabled: true,
    prompt:
      "Please indicate whether the sentence was OK or whether you think it contained an error.",
    options: ["I noticed an error", "Not sure", "Sentence was OK"],
  },

  // Browser-check screen shown after consent. The MoTR window and word boxes are defined in
  // CSS pixels, so browser zoom changes their size on screen; the check asks participants
  // to set the zoom to 100% and blocks until they do (zoom is estimated from
  // window.outerWidth / window.innerWidth, reliable on desktop Chrome/Firefox/Edge). The
  // zoom level is also recorded with every trial (zoomPercent), so it can be checked later.
  browserCheck: {
    enabled: true,
    requireZoom100: true,
    zoomTolerance: 2, // percent
    allowSkipAfterSeconds: 30, // show a "continue anyway" link after this long (0 = never)
  },

  // Post-experiment survey screen (input device, hand, free-text feedback).
  survey: { enabled: true },

  // Mouse sampling interval in ms: how often the word under the cursor and the mouse
  // position are recorded while the cursor is over the text.
  sampleIntervalMs: 50,

  // Submit each trial's data as soon as the trial ends (recommended). MoTR produces a lot
  // of rows, and per-trial submission avoids losing everything if a participant drops out
  // or the final upload fails. If false, everything is submitted once at the end.
  submitEachTrial: true,
};
