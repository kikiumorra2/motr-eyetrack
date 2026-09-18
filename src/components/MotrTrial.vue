<!--
  MotrTrial — one Mouse-Tracking-for-Reading trial.

  Markup and CSS replicate the original MoTR experiment screen exactly (class names
  included), so layout, font, blur and the cursor window are identical:

    <Screen class="main_screen">        position: relative; isolation: isolate; 18px / 40px
      <div>                             this component's root (plays the role of magpie's <Slide>)
        .oval-cursor                    the moving "window": a white oval with mix-blend-mode: difference
        counter                         "Sentence i of N"
        .readingText                    sharp WHITE text, absolutely positioned, one <span> per word
        .blurry-layer                   BLACK text, blurred, 30% opacity, painted on top of the white text
        spacer / buttons / question

  On a white page the white text is invisible and the participant only sees the blurred
  black copy. Under the oval, difference blending inverts the white text to black and
  cancels the blur, producing a sharp window that follows the mouse. The blurry layer has
  pointer-events: none, so the word <span>s receive the mouse events.

  Trial flow:
    1. Sentence is displayed blurred with a green start button.
    2. Participant clicks the green button.
    3. Reading begins; spotlight appears and tracking starts.
    4. Participant reads and moves the spotlight horizontally.
    5. Participant clicks the red finish button.
    6. Reading ends and the comprehension question appears.
    7. After answering, the next trial begins with a green start button.

  Data (config.samplingMode):
    "interval"  legacy 20 Hz sampler: while the cursor is over the text, every
                `sampleIntervalMs` a row is recorded with the word under the cursor
                (Index/Word), its bounding box and the spotlight position.
    "events"    (default) character-event recorder (src/charEvents/): every coalesced pointer
                sample is hit-tested against measured character boxes and only changes
                of the character under the cursor are kept, with millisecond timestamps;
                one compact row per trial.
    "both"      both, for validation.

  "Start Reading" records the beginning of the reading period.
  "Finish Reading" records the end-of-reading marker and shows the question (if any).
  "Next Trial" records a trial-summary row and emits `done`.

  mousePositionX/Y:
    X = horizontal position of the spotlight.
    Y = fixed vertical position of the spotlight relative to the text.
    The participant's actual physical mouse Y position is not recorded.
-->

<template>
  <div>
    <div
      class="main_screen"
      @mousemove="started ? onMouseMove($event) : null"
      @mouseleave="started ? onMouseLeave() : null"
    >

      <!-- Spotlight -->
      <div
        class="oval-cursor"
        :style="{ fontSize: sentenceFontSize + 'px' }"
      ></div>

      <div class="trial-counter">
        <template v-if="trial.phase === 'practice'">
          Practice sentence {{ number }}
        </template>
        <template v-else>
          Sentence {{ number }} of {{ total }}
        </template>
      </div>

      <!--
        Reading area.

        The green button is shown before reading starts.
        The red button is shown after reading starts.
      -->
      <div
          v-if="reading"
          class="reading-row"
        >

        <!-- Green start button -->
          <button
            class="trial-button start-button"
            :class="{ 'button-hidden': started }"
            @click="startReading"
            aria-label="Start reading"
          ></button>

          <!-- Sentence -->
          <div class="sentence-container">

            <!-- Sharp text -->
            <div
              class="readingText"
              :style="{ fontSize: sentenceFontSize + 'px' }"
            >
              <template v-for="(word, i) of words">
                <span :key="i" :data-index="i">
                  {{ word }}
                </span>
              </template>
            </div>

            <!-- Blurred text -->
            <div
              class="blurry-layer"
              :style="{
                fontSize: sentenceFontSize + 'px',
                opacity: 0.3,
                filter: 'blur(0.28em)',
                transition: 'all 0.3s linear 0s'
              }"
            >
              {{ trial.text }}
            </div>

          </div>

          <!-- Red finish button -->
          <button
            class="trial-button finish-button"
            :class="{ 'button-hidden': !started }"
            @click="finishReading"
            aria-label="Finish reading"
          ></button>
        </div>

      <div style="height: 75px"></div>

      <!-- Comprehension question -->
      <div>
        <div v-if="!reading && question" class="userInput">
          <p>{{ question.prompt }}</p>

          <MultipleChoiceInput
            :response.sync="$magpie.measurements.response"
            :options="question.options"
          />
        </div>
      </div>

      <!-- Next trial -->
      <button
        v-if="!reading && question && $magpie.measurements.response"
        @click="finishTrial"
      >
        Next Trial
      </button>

    </div>
  </div>
</template>

<script>
import config from "../config";
import { zoomPercent } from "../browser";
import { submitRows } from "../submit";
import { CharEventRecorder } from "../charEvents/recorder.js";
import { measureLayout } from "../charEvents/measure.js";
import { attachRecorder } from "../charEvents/dom.js";
import { decodeRow } from "../charEvents/decoder.js";

const samplingMode = () => config.samplingMode || "interval";

export default {
  name: "MotrTrial",

  props: {
    /** Trial object from src/materials.js */
    trial: { type: Object, required: true },

    /** 0-based position of this trial in the whole sequence (recorded as TrialId) */
    index: { type: Number, required: true },

    /** 1-based number shown in the counter ("Sentence 3 of 10") */
    number: { type: Number, required: true },

    /** Number of main trials (for the "Sentence i of N" counter) */
    total: { type: Number, required: true },

    listId: { type: [Number, String], default: null },

    sentenceFontSize: { type: Number, default: 16 },
  },

  data() {
    return {
      /*
       * reading = whether the reading/question screen is active.
       * started = whether the participant has clicked the green start button.
       */
      reading: true,
      started: false,

      hasMoved: false,

      // Word index under the spotlight:
      // >= 0 on a word
      // -1 inside the text area but not on a word
      // null when outside the text area
      currentIndex: null,

      /*
       * Position of the spotlight, NOT the physical mouse.
       *
       * x = participant's horizontal cursor position
       * y = fixed vertical spotlight position
       */
      mouse: { x: 0, y: 0 },

      readingStart: null,
      readingTime: null,
      timer: null,

      /*
       * Vertical position of the buttons relative to .reading-row.
       *
       * This is deliberately separate from spotlightY(), because
       * spotlightY() is a viewport coordinate whereas the buttons
       * are absolutely positioned inside .reading-row.
       */
    };
  },

  computed: {
    words() {
      return this.trial.text.split(/\s+/);
    },

    /** Per-item question if present in the materials, else the default from config. */
    question() {
      if (this.trial.question) {
        return {
          prompt: this.trial.question,
          options: this.trial.options || []
        };
      }

      if (config.question.enabled) {
        return {
          prompt: config.question.prompt,
          options: config.question.options
        };
      }

      return null;
    },
  },

  mounted() {
    const mode = samplingMode();

    /*
     * The interval sampler can be running continuously, but recordSample()
     * will ignore all samples until the participant clicks the green button.
     */
    if (mode !== "events") {
      this.timer = setInterval(
        this.recordSample,
        config.sampleIntervalMs
      );
    }

    /*
     * The character-event recorder is deliberately NOT started here.
     * It starts when the participant clicks the green start button.
     */

  },

  beforeDestroy() {
    clearInterval(this.timer);
    this.stopRecorder();


  },

  methods: {

    isCorrectResponse(response) {
      const correct = String(
        this.trial.correct || ""
      ).trim().toUpperCase();

      if (correct === "BOTH" || correct === "NA") {
        return true;
      }

      return response === correct;
    },

    cursorEl() {
      return this.$el.querySelector(".oval-cursor");
    },

    baseRow() {
      return {
        Experiment: config.experimentName,
        Condition: this.trial.condition_id,
        ItemId: this.trial.item_id,
      };
    },

    /**
     * Start the reading portion of the trial.
     *
     * The green button is the start point for:
     *   - reading time
     *   - mouse tracking
     *   - character-event recording
     *   - spotlight visibility
     */
    startReading() {
      if (this.started) return;

      this.started = true;
      this.hasMoved = false;
      this.readingStart = Date.now();

      const cursor = this.cursorEl();

      // Spotlight starts invisible/tiny.
      cursor.classList.remove("grow", "blank");

      /*
       * Start the character-event recorder at the same point as
       * the reading trial.
       */
      if (samplingMode() !== "interval") {
        this.$nextTick(() => this.startRecorder());
      }
    },

    /**
     * Called every sampleIntervalMs; records the word under the spotlight.
     */
    recordSample() {
      // Do not record anything before the participant starts reading.
      if (!this.started || this.currentIndex === null) return;

      const row = {
        ...this.baseRow(),
        Index: this.currentIndex,
        mousePositionX: this.mouse.x,
        mousePositionY: this.mouse.y,
      };

      const el =
        this.currentIndex >= 0
          ? this.$el.querySelector(
              `span[data-index="${this.currentIndex}"]`
            )
          : null;

      if (el) {
        const rect = el.getBoundingClientRect();

        // The span text is " word " (padded, as in the original);
        // store it trimmed.
        row.Word = el.textContent.trim();

        row.wordPositionTop = rect.top;
        row.wordPositionLeft = rect.left;
        row.wordPositionBottom = rect.bottom;
        row.wordPositionRight = rect.right;
      }

      this.$magpie.addTrialData(row);
    },

    /**
     * Return the word span at a particular screen coordinate.
     */
    wordAt(x, y) {
      const el = document.elementFromPoint(x, y);
      return el ? el.closest("span[data-index]") : null;
    },

    /**
     * Get the fixed vertical position of the spotlight.
     *
     * The spotlight is centered on the text line, with an additional
     * sentenceFontSize offset downward.
     *
     * Importantly, this does NOT use the participant's actual mouse Y.
     */
    spotlightY() {
      if (!this.$el) return 0;

      const firstWord = this.$el.querySelector(
        ".readingText span"
      );

      if (!firstWord) return 0;

      const rect = firstWord.getBoundingClientRect();

      return (
        rect.top +
        rect.height / 2 +
        this.sentenceFontSize
      );
    },

    /**
     * Mouse movement while the participant is reading.
     *
     * Only the X coordinate comes from the participant's cursor.
     * Y is fixed to the vertical position of the sentence.
     */
    onMouseMove(e) {
      if (!this.started) return;

      /*
       * Don't treat movement over the start/finish buttons as
       * movement through the sentence.
       */
      if (
        e.target.closest &&
        e.target.closest(".trial-button")
      ) {
        return;
      }

      const cursor = this.cursorEl();

      cursor.classList.add("grow");

      const x = e.clientX;
      const y = this.spotlightY();

      /*
       * Hit-test the sentence at the fixed spotlight Y position,
       * rather than at the participant's physical mouse Y.
       */
      let el = this.wordAt(x, y);

      if (el) {
        cursor.classList.remove("blank");
      } else {
        /*
         * Not on a word: shrink the window and look slightly above
         * the cursor so the word on the line still counts.
         */
        cursor.classList.add("blank");
        el = this.wordAt(x, y - 3);
      }

      this.currentIndex = el
        ? Number(el.getAttribute("data-index"))
        : -1;

      /*
       * The spotlight follows X but has a fixed Y.
       */
      cursor.style.left = `${x + 12}px`;
      cursor.style.top = `${y - 16}px`;

      /*
       * Record the spotlight position.
       *
       * mousePositionY is deliberately NOT e.clientY.
       */
      this.mouse.x = x;
      this.mouse.y = y;

      this.hasMoved = true;
    },

    onMouseLeave() {
      if (!this.started) return;

      this.cursorEl().classList.remove(
        "grow",
        "blank"
      );

      this.currentIndex = null;
    },

    // ------------------------------------------------------------------
    // Character-event recorder
    // ------------------------------------------------------------------

    /**
     * The recorder is deliberately NOT part of data(): it is written
     * to on every pointer sample and must not be made reactive.
     */
    startRecorder() {
      const el = this.$el.querySelector(".readingText");

      if (!el || this._recorder) return;

      const recorder = new CharEventRecorder(
        config.charEvents || {}
      );

      const t0 = performance.now();
      const screenStart =
        this.$magpie.responseTimeStart || Date.now();

      recorder.start(
        t0,
        this.words,
        measureLayout(el, this.words),
        {
          t0Response: Date.now() - screenStart,
          tsrc: "event",
        }
      );

      this._recorder = recorder;

      this._detachRecorder = attachRecorder({
        recorder,
        readingTextEl: el,
        words: this.words
      });
    },

    stopRecorder() {
      if (this._detachRecorder) {
        this._detachRecorder();
      }

      this._detachRecorder = null;
    },

    /**
     * Ends the recording and stores the trial's charEvents row.
     */
    pushCharEventsRow() {
      const recorder = this._recorder;

      if (!recorder) return;

      recorder.end(performance.now());

      const fields = recorder.fields();

      this.$magpie.addTrialData({
        ...this.baseRow(),
        TrialType: "charEvents",
        TrialText: this.trial.text,
        ...fields,
      });

      if (
        config.charEvents &&
        config.charEvents.selfCheck
      ) {
        const decoded = decodeRow(fields);

        const size = Object.values(fields).reduce(
          (n, v) => n + v.length,
          0
        );

        console.assert(
          decoded.events.length ===
            recorder.events.length,
          "charEvents self-check: event count"
        );

        console.log(
          `charEvents ${this.trial.item_id}: ` +
          `${decoded.events.length} events, ` +
          `${decoded.trace.length} trace samples, ` +
          `${decoded.snapshots.length} layout(s), ` +
          `${size} bytes, ` +
          `stats ${fields.mtStats}`
        );
      }

      this._recorder = null;
    },

    /**
     * Finish the reading portion of the trial.
     *
     * This is now called by the red square rather than a
     * "Done Reading" button.
     */
    finishReading() {
      if (!this.started) return;

      const mode = samplingMode();

      if (mode !== "events") {
        /*
         * End-of-reading marker:
         * lets postprocessing close the fixation on the last word.
         *
         * mousePositionY is the fixed spotlight Y.
         */
        this.$magpie.addTrialData({
          ...this.baseRow(),
          Index: -1,
          mousePositionX: this.mouse.x,
          mousePositionY: this.mouse.y,
        });
      }

      if (mode !== "interval") {
        this.pushCharEventsRow();
      }

      this.stopRecorder();

      this.currentIndex = null;

      const cursor = this.cursorEl();

      cursor.classList.remove(
        "grow",
        "blank"
      );

      this.readingTime =
        Date.now() - this.readingStart;

      /*
       * Reading has ended.
       */
      this.started = false;
      this.reading = false;

      /*
       * Show the question, or immediately finish the trial
       * if there is no question.
       */
      if (!this.question) {
        this.finishTrial();
      }
    },

    finishTrial() {
      const response =
        this.$magpie.measurements.response || null;

      const isCorrect = response
        ? this.isCorrectResponse(response)
        : null;

      this.$magpie.addTrialData({
        ...this.baseRow(),

        TrialId: this.index,
        TrialType: "trial",
        Phase: this.trial.phase,
        TrialText: this.trial.text,

        userResponse: response,
        correctResponse: this.trial.correct,
        isCorrect: isCorrect,

        readingTime: this.readingTime,
        ListId: this.listId,
        zoomPercent: zoomPercent(),
        devicePixelRatio: window.devicePixelRatio,
        windowInnerWidth: window.innerWidth,
        windowInnerHeight: window.innerHeight,
      });

      if (config.submitEachTrial) {
        this.submitTrial();
      }

      this.$emit("done");
    },

    /** Send this trial's rows (samples + summary) to the magpie server. */
    submitTrial() {
      const rows = this.$magpie
        .getAllData()
        .filter(
          (r) =>
            String(r.ItemId) ===
              this.trial.item_id &&
            String(r.Condition) ===
              this.trial.condition_id
        );

      submitRows(
        this.$magpie,
        rows,
        `trial ${this.trial.item_id}`
      ).catch(() => {});
    },
  },
};
</script>

<style>
/*
 * Main screen
 */
.main_screen {
  isolation: isolate;
  position: relative;
  width: 100%;
  min-height: 100vh;
  font-family: Arial, sans-serif;
  font-size: 16px;
  line-height: 40px;
}

/*
 * Reading row
 *
 * The sentence and its buttons form one horizontal group.
 * This means the buttons are positioned immediately adjacent
 * to the actual rendered sentence rather than relative to
 * the screen.
 */
.reading-row {
  position: relative;

  width: 100%;

  display: flex;
  align-items: center;
  justify-content: center;

  min-height: 100px;
}

/*
 * Container for the sentence.
 *
 * The container shrinks to exactly the width of the sentence,
 * allowing the buttons to sit immediately beside it.
 */

.sentence-container {
  display: grid;
  width: max-content;
}


/*
 * Counter
 */
.trial-counter {
  position: relative;
  z-index: 5;
}

.readingText,
.blurry-layer {
  grid-area: 1 / 1;

  margin: 0;
  padding-top: 10%;
  padding-bottom: 10%;
  padding-left: 0;
  padding-right: 0;

  width: max-content;
  box-sizing: border-box;

  text-align: center;
  font-weight: 450;
  font-family: Consolas, monospace;
  white-space: nowrap;
}

.readingText {
  position: relative;
  color: white;
  cursor: pointer;
}

.blurry-layer {
  position: relative;
  pointer-events: none;
  color: black;
}

/*
 * Start / finish buttons
 */
.trial-button {
  flex: 0 0 auto;

  width: 32px;
  height: 260px;

  padding: 0;

  border: none;
  border-radius: 2px;

  cursor: pointer;

  margin: 20px auto 20px auto;

  z-index: 5;
}

/*
 * Put a small gap between the sentence and the buttons.
 */
.start-button {
  background-color: green;
}

.finish-button {
  background-color: red;
}

.trial-button:hover {
  opacity: 0.85;
}

/*
 * Comprehension question
 */
.userInput {
  padding-top: 2%;
  padding-bottom: 2%;
  padding-left: 20%;
  padding-right: 20%;
}

button {
  left: 50%;
}

.button-hidden {
  visibility: hidden;
  pointer-events: none;
}

/*
 * Spotlight
 */
.oval-cursor {
  position: fixed;
  z-index: 2;

  width: 1px;
  height: 1px;

  transform: translate(-50%, -50%);

  background-color: white;
  mix-blend-mode: difference;
  border-radius: 50%;

  pointer-events: none;

  transition: width 0.5s, height 0.5s;
}

/*
 * Small/shrunken spotlight when no word is directly under it.
 */
.oval-cursor.grow.blank {
  width: 5em;
  height: 10em;
}

/*
 * Normal spotlight.
 */
.oval-cursor.grow {
  width: 5em;
  height: 10em;

  border-radius: 50%;

  box-shadow:
    30px 0 8px -4px rgba(255, 255, 255, 0.1),
    -30px 0 8px -4px rgba(255, 255, 255, 0.1);

  background-color: rgba(255, 255, 255, 0.3);
  background-blend-mode: screen;

  pointer-events: none;

  transition: width 0.5s, height 0.5s;

  filter: blur(3px);
}

/*
 * Sharp center of spotlight.
 */
.oval-cursor.grow::before {
  content: "";

  position: absolute;

  top: 50%;
  left: 50%;

  transform: translate(-50%, -50%);

  width: 70%;
  height: 70%;

  background-color: white;
  mix-blend-mode: normal;

  border-radius: 50%;
}


</style>