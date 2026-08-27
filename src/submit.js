/**
 * The single place where data leaves the browser.
 *
 * By default `rows` (an array of flat objects, one per mouse sample / trial summary) is sent
 * to the magpie server from src/magpie.config.js:
 *     POST {serverUrl}/api/submit_experiment/{experimentId}   body: JSON array of rows
 * To use a different backend, change serverUrl (any magpie server works as is) or replace
 * the body of this function with your own request.
 *
 * In debug mode nothing is sent; the rows are printed to the browser console and collected
 * in window.__motrRows, so a whole session can be saved from the console with
 *     copy(JSON.stringify(window.__motrRows))
 * (paste into rows.json for postprocessing/plot_char_events.py or motr_char_events.py --check).
 */
export async function submitRows(magpie, rows, label) {
  if (!rows.length) return;
  if (magpie.debug) {
    const store = (window.__motrRows = window.__motrRows || []);
    store.push(...rows);
    console.log(
      `[MoTR] debug mode: not submitting ${rows.length} rows (${label}); ${store.length} rows collected in window.__motrRows`,
      rows
    );
    return;
  }
  try {
    await magpie.submitResults(magpie.submissionUrl, rows);
  } catch (err) {
    console.error(`[MoTR] submission failed (${label})`, err);
    throw err;
  }
}
