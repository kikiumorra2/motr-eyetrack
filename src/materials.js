/**
 * Loads the experimental materials and builds the trial sequence.
 *
 * Files (see materials/README.md for the column spec):
 *   materials/lists/list_NN.csv   critical items, one list per participant group
 *   materials/fillers.csv         filler sentences shown to everyone
 *   materials/practice.csv        practice sentences shown before the main trials
 *
 * All CSVs are bundled into the app at build time by csv-loader (see vue.config.js).
 */
import _ from "lodash";
import config from "./config";
import fillerRows from "../materials/fillers.csv";
import practiceRows from "../materials/practice.csv";

// Bundle every materials/lists/list_NN.csv. The list is chosen at runtime (see chooseListId).
const listContext = require.context("../materials/lists", false, /^\.\/list_\d+\.csv$/);
const lists = {};
listContext.keys().forEach((key) => {
  const id = Number(key.match(/list_(\d+)\.csv$/)[1]);
  lists[id] = listContext(key);
});

/** Sorted numeric IDs of all available lists. */
export const listIds = Object.keys(lists)
  .map(Number)
  .sort((a, b) => a - b);

/**
 * Pick the list for this participant: ?LIST_ID=N in the URL wins; otherwise
 * config.defaultList ("random" or a list number).
 */
export function chooseListId() {
  if (listIds.length === 0) {
    throw new Error("No lists found in materials/lists/. Run scripts/make_lists.py first.");
  }
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("LIST_ID");
  if (requested !== null) {
    const id = Number(requested);
    if (lists[id]) return id;
    console.warn(`[MoTR] LIST_ID=${requested} does not exist; falling back to default.`);
  }
  if (config.defaultList === "random") return _.sample(listIds);
  return lists[config.defaultList] ? Number(config.defaultList) : listIds[0];
}

function isBlank(value) {
  return value === undefined || value === null || String(value).trim() === "";
}

/** Convert a CSV row into the trial object consumed by <MotrTrial>. */
function toTrial(row, phase) {
  return {
    item_id: String(row.item_id),
    condition_id: String(row.condition_id),
    text: String(row.text).trim(),
    question: isBlank(row.question) ? null : String(row.question),
    // options are pipe-separated in the CSV, e.g. "Yes|No"
    options: isBlank(row.options)
      ? null
      : String(row.options)
          .split("|")
          .map((s) => s.trim()),
    correct: isBlank(row.correct) ? null : String(row.correct),
    phase, // "practice" | "main"
    row, // the full original CSV row, in case you need extra columns
  };
}

/** Practice trials, in file order. */
export function buildPracticeTrials() {
  return practiceRows.slice(0, config.nPractice).map((r) => toTrial(r, "practice"));
}

/**
 * Main trials for a list: leading fillers first (unshuffled), then the critical items
 * mixed with the remaining fillers (shuffled if config.shuffleTrials).
 */
export function buildMainTrials(listId) {
  const items = lists[listId].map((r) => toTrial(r, "main"));
  const fillers = fillerRows.map((r) => toTrial(r, "main"));
  const leading = fillers.splice(0, config.nLeadingFillers);
  let rest = items.concat(fillers);
  if (config.shuffleTrials) rest = _.shuffle(rest);
  return leading.concat(rest);
}
