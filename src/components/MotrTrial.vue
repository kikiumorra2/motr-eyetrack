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

  Data: while the cursor is over the text, every `sampleIntervalMs` a row is recorded with
  the word under the cursor (Index/Word), its bounding box and the mouse position. "Done
  Reading" records a marker row (Index = -1) and shows the question (if any). "Next Trial"
  records a trial-summary row (TrialType = "trial"), optionally submits this trial's rows
  to the server, and emits `done`. magpie adds `responseTime` (ms since screen start).

    sample rows:  Experiment, Condition, ItemId, Index, Word, mousePositionX/Y,
                  wordPositionTop/Left/Bottom/Right
    summary row:  Experiment, Condition, ItemId, TrialId, TrialType, Phase, TrialText,
                  userResponse, correctResponse, readingTime, ListId, zoomPercent,
                  devicePixelRatio, windowInnerWidth, windowInnerHeight
-->
<template>
  <div>
    <div class="oval-cursor"></div>

    <div class="trial-counter">
      <template v-if="trial.phase === 'practice'">Practice sentence {{ number }}</template>
      <template v-else>Sentence {{ number }} of {{ total }}</template>
    </div>

    <div
      v-if="reading"
      class="readingText"
      @mousemove="onMouseMove"
      @mouseleave="onMouseLeave"
    >
      <template v-for="(word, i) of words">
        <span :key="i" :data-index="i">
          {{ word }}
        </span>
      </template>
    </div>

    <div
      class="blurry-layer"
      style="opacity: 0.3; filter: blur(5px); transition: all 0.3s linear 0s"
    >
      {{ trial.text }}
    </div>

    <div style="height: 75px"></div>

    <div>
      <button v-if="reading" :disabled="!hasMoved" @click="finishReading">
        Done Reading
      </button>
    </div>

    <div v-if="!reading && question" class="userInput">
      <p>{{ question.prompt }}</p>
      <MultipleChoiceInput
        :response.sync="$magpie.measurements.response"
        :options="question.options"
      />
    </div>

    <button
      v-if="!reading && question && $magpie.measurements.response"
      @click="finishTrial"
    >
      Next Trial
    </button>
  </div>
</template>

<script>
import config from "../config";
import { zoomPercent } from "../browser";
import { submitRows } from "../submit";

export default {
  name: "MotrTrial",
  props: {
    /** Trial object from src/materials.js */
    trial: { type: Object, required: true },
    /** 0-based position of this trial in the whole sequence (recorded as TrialId) */
    index: { type: Number, required: true },
    /** 1-based number shown in the counter ("Sentence 3 of 10"), within practice or main */
    number: { type: Number, required: true },
    /** Number of main trials (for the "Sentence i of N" counter) */
    total: { type: Number, required: true },
    listId: { type: [Number, String], default: null },
  },
  data() {
    return {
      reading: true,
      hasMoved: false,
      // Word index under the cursor: >= 0 on a word, -1 inside the text area but not on a
      // word, null when the cursor is outside the text area (no samples are recorded).
      currentIndex: null,
      mouse: { x: 0, y: 0 },
      readingStart: null,
      readingTime: null,
      timer: null,
    };
  },
  computed: {
    words() {
      return this.trial.text.split(/\s+/);
    },
    /** Per-item question if present in the materials, else the default from config. */
    question() {
      if (this.trial.question) {
        return { prompt: this.trial.question, options: this.trial.options || [] };
      }
      if (config.question.enabled) {
        return { prompt: config.question.prompt, options: config.question.options };
      }
      return null;
    },
  },
  mounted() {
    this.timer = setInterval(this.recordSample, config.sampleIntervalMs);
  },
  beforeDestroy() {
    clearInterval(this.timer);
  },
  methods: {
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

    /** Called every sampleIntervalMs; records the word under the cursor. */
    recordSample() {
      if (this.currentIndex === null) return;
      const row = {
        ...this.baseRow(),
        Index: this.currentIndex,
        mousePositionX: this.mouse.x,
        mousePositionY: this.mouse.y,
      };
      const el =
        this.currentIndex >= 0
          ? this.$el.querySelector(`span[data-index="${this.currentIndex}"]`)
          : null;
      if (el) {
        const rect = el.getBoundingClientRect();
        // The span text is " word " (padded, as in the original); store it trimmed.
        row.Word = el.textContent.trim();
        row.wordPositionTop = rect.top;
        row.wordPositionLeft = rect.left;
        row.wordPositionBottom = rect.bottom;
        row.wordPositionRight = rect.right;
      }
      this.$magpie.addTrialData(row);
    },

    wordAt(x, y) {
      const el = document.elementFromPoint(x, y);
      return el ? el.closest("span[data-index]") : null;
    },

    onMouseMove(e) {
      const cursor = this.cursorEl();
      if (!this.hasMoved) {
        this.hasMoved = true;
        this.readingStart = Date.now();
      }
      cursor.classList.add("grow");

      const x = e.clientX;
      const y = e.clientY;
      let el = this.wordAt(x, y);
      if (el) {
        cursor.classList.remove("blank");
      } else {
        // Not on a word: shrink the window and look slightly above the cursor so the
        // word on the line above still counts.
        cursor.classList.add("blank");
        el = this.wordAt(x, y - 3);
      }
      this.currentIndex = el ? Number(el.getAttribute("data-index")) : -1;

      cursor.style.left = `${x + 12}px`;
      cursor.style.top = `${y - 6}px`;
      this.mouse.x = x;
      this.mouse.y = y;
    },

    onMouseLeave() {
      this.cursorEl().classList.remove("grow", "blank");
      this.currentIndex = null;
    },

    finishReading() {
      // End-of-reading marker: lets postprocessing close the fixation on the last word.
      this.$magpie.addTrialData({
        ...this.baseRow(),
        Index: -1,
        mousePositionX: this.mouse.x,
        mousePositionY: this.mouse.y,
      });
      this.currentIndex = null;
      this.cursorEl().classList.remove("grow", "blank");
      this.readingTime = Date.now() - this.readingStart;
      this.reading = false;
      if (!this.question) this.finishTrial();
    },

    finishTrial() {
      this.$magpie.addTrialData({
        ...this.baseRow(),
        TrialId: this.index,
        TrialType: "trial",
        Phase: this.trial.phase,
        TrialText: this.trial.text,
        userResponse: this.$magpie.measurements.response || null,
        correctResponse: this.trial.correct,
        readingTime: this.readingTime,
        ListId: this.listId,
        zoomPercent: zoomPercent(),
        devicePixelRatio: window.devicePixelRatio,
        windowInnerWidth: window.innerWidth,
        windowInnerHeight: window.innerHeight,
      });
      if (config.submitEachTrial) this.submitTrial();
      this.$emit("done");
    },

    /** Send this trial's rows (samples + summary) to the magpie server. */
    submitTrial() {
      const rows = this.$magpie
        .getAllData()
        .filter(
          (r) =>
            String(r.ItemId) === this.trial.item_id &&
            String(r.Condition) === this.trial.condition_id
        );
      submitRows(this.$magpie, rows, `trial ${this.trial.item_id}`).catch(() => {});
    },
  },
};
</script>

<style>
/* Copied verbatim from the original MoTR experiment. Keep .readingText and .blurry-layer
   identical (font, padding) so the two text layers line up exactly. */
.main_screen {
  isolation: isolate;
  position: relative;
  width: 100%;
  height: auto;
  font-size: 18px;
  line-height: 40px;
}
.debugResults {
  width: 100%;
}
.readingText {
  /* z-index: 1; */
  position: absolute;
  color: white;
  text-align: left;
  font-weight: 450;
  cursor: pointer;
  padding-top: 2%;
  padding-bottom: 2%;
  padding-left: 11%;
  padding-right: 11%;
}
.userInput {
  padding-top: 2%;
  padding-bottom: 2%;
  padding-left: 20%;
  padding-right: 20%;
}
button {
  /* position: absolute; */
  /* bottom: 0; */
  left: 50%;
}
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
.oval-cursor.grow.blank {
  width: 80px;
  height: 13px;
}
.oval-cursor.grow {
  width: 102px;
  height: 38px;
  border-radius: 50%;
  box-shadow: 30px 0 8px -4px rgba(255, 255, 255, 0.1),
    -30px 0 8px -4px rgba(255, 255, 255, 0.1);
  background-color: rgba(255, 255, 255, 0.3);
  background-blend-mode: screen;
  pointer-events: none;
  transition: width 0.5s, height 0.5s;
  filter: blur(3px);
}
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
.blurry-layer {
  position: absolute;
  pointer-events: none;
  color: black;
  text-align: left;
  font-weight: 450;
  padding-top: 2%;
  padding-bottom: 2%;
  padding-left: 11%;
  padding-right: 11%;
}
</style>
