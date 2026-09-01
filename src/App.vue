<!--
  Screen flow of the experiment:
    1. Consent + participant ID          (edit the study information text below)
    2. Browser check: zoom = 100%         (config.browserCheck)
    3. Instructions                       (edit)
    4. Practice trials                    (materials/practice.csv, config.nPractice)
       "Practice complete" screen
    5. Main trials                        (materials/lists/list_NN.csv + fillers.csv)
    6. Survey: device, hand, feedback     (config.survey.enabled)
    7. Completion code

  The MoTR interface itself is in components/MotrTrial.vue; experiment settings are in
  config.js; server settings in magpie.config.js; materials in ../materials/.
-->
<template>
  <Experiment title="Reading Experiment" translate="no" wide>
    <!-- 1. Consent ---------------------------------------------------------------- -->
    <Screen
      title="Welcome"
      class="instructions"
      :validations="{ SubjectID: { minLength: $magpie.v.minLength(2) } }"
    >
      <div class="consent">
        <div class="box"><b>Information About this Study</b></div>
        <p>
          <b>What is being investigated?</b> You are being asked to take part in a research
          study being done at New York University. This study will help us learn about how people
          read. It will take you around 30 minutes to complete.
        </p>
        <p>
          <b>Who can participate?</b> You can participate only if you are an adult native
          speaker of English.
        </p>
        <p>
          <b>What am I supposed to do as a participant?</b> If you choose to be in the study,
          you will use the computer mouse to read sentences in English and answer questions
          about them.
        </p>
        <p>
          <b>What are my rights during participation?</b> Your participation in this study is
          voluntary. If you choose to participate, you may change your mind and leave the
          study at any time by closing the web page. You do not have to provide reasons.
        </p>
        <p>
          <b>What risks and benefits can I expect?</b> There are no foreseeable risks for
          participating in this study.
        </p>
        <p>
          <b>Will I be compensated for participating?</b> If you complete the experiment, you
          will be compensated for your time according to the amount specified on Prolific.
        </p>
        <p>
          <b>What data is collected from me and how is it used?</b> During this study, we will
          track the position of your mouse on screen. At the end of the study you will be
          asked to complete a brief survey. No personally identifying information will be
          collected. The data from this study may be presented at scientific conferences and
          published in scientific journals, as well as in online repositories. All data will
          remain anonymous.
        </p>
        <p>
          <b>Who reviewed this study?</b> This study's protocol has been approved by
          [IRB / ETHICS COMMITTEE].
        </p>
        <p><b>Contact:</b> Please feel free to contact us anonymously via Prolific Direct Message.</p>

        <div class="box"><b>Consent Form</b></div>
        <p>I, the participant, confirm by clicking the button below:</p>
        <ul>
          <li>I have read and understood the study information above.</li>
          <li>I comply with the inclusion and exclusion criteria for participation described above.</li>
          <li>I have had enough time to decide about my participation.</li>
          <li>I participate in this study voluntarily and consent that my personal data be used as described above.</li>
          <li>I understand that I can stop participating at any moment.</li>
        </ul>

        <p>
          Please enter your Prolific ID to continue:&nbsp;
          <input type="text" v-model="$magpie.measurements.SubjectID" />
        </p>

        <div
          v-if="$magpie.measurements.SubjectID && !$magpie.validateMeasurements.SubjectID.$invalid"
        >
          <p>By clicking on the button below you consent to participating in this study:</p>
          <button @click="consent">Proceed</button>
        </div>
      </div>
    </Screen>

    <!-- 2. Browser check (zoom) -------------------------------------------------- -->
    <Screen 
      v-if="config.browserCheck.enabled" 
      title="Before we start"
      class="instructions"
    >
      <div class ="browser-check-text">
        <BrowserCheck @done="browserCheckDone" />
      </div>
    </Screen>

    <!-- 3. Instructions ---------------------------------------------------------- -->
    <InstructionScreen title="Instructions">
      <p>
        In this study, you will read sentences. Unlike in normal reading, however, the text
        will be blurred. To bring the text into focus, move your mouse over it. When you are
        done reading, click the <b>Done Reading</b> button.
      </p>
      <p>
        After each sentence you will be asked a question about it. Indicate your answer by
        clicking the appropriate option, then click <b>Next</b>.
      </p>
      <p v-if="practiceTrials.length">We will start with a few practice sentences.</p>
    </InstructionScreen>

    <!-- 4. Practice trials ------------------------------------------------------- -->
    <template v-for="(trial, i) in practiceTrials">
      <Screen :key="'practice-' + i" class="main_screen" :progress="0">
        <MotrTrial
          :trial="trial"
          :index="i"
          :number="i + 1"
          :total="mainTrials.length"
          :list-id="listId"
          @done="$magpie.nextScreen()"
        />
      </Screen>
    </template>

    <!-- 4b. Practice complete ----------------------------------------------------- -->
    <InstructionScreen v-if="practiceTrials.length" title="Practice complete">
      <p>That was the practice. Press the button to start the main study.</p>
    </InstructionScreen>

    <!-- 5. Main trials ----------------------------------------------------------- -->
    <template v-for="(trial, i) in mainTrials">
      <Screen :key="'trial-' + i" class="main_screen" :progress="i / mainTrials.length">
        <MotrTrial
          :trial="trial"
          :index="practiceTrials.length + i"
          :number="i + 1"
          :total="mainTrials.length"
          :list-id="listId"
          @done="$magpie.nextScreen()"
        />
      </Screen>
    </template>

    <!-- 6. Survey ---------------------------------------------------------------- -->
    <Screen v-if="config.survey.enabled" title="Almost done">
      <p>1. Which input device are you using for this experiment?</p>
      <MultipleChoiceInput
        :response.sync="$magpie.measurements.device"
        orientation="horizontal"
        :options="['Computer Mouse', 'Computer Trackpad', 'Other']"
      />
      <p>2. Which hand are you using during this experiment?</p>
      <MultipleChoiceInput
        :response.sync="$magpie.measurements.hand"
        orientation="horizontal"
        :options="['Left', 'Right', 'Both']"
      />
      <p>
        3. What did you think about the experiment? Please describe how hard or easy the task
        felt, anything you noticed about the sentences, or any other thoughts you have. If
        anything was confusing or frustrating, please let us know!
      </p>
      <TextareaInput :response.sync="$magpie.measurements.feedback" />
      <button :disabled="submitting" @click="finish">
        {{ submitting ? "Submitting…" : "Submit" }}
      </button>
    </Screen>
    <Screen v-else title="Almost done">
      <p>The next screen will submit your results and display your completion code.</p>
      <button :disabled="submitting" @click="finish">
        {{ submitting ? "Submitting…" : "Continue" }}
      </button>
    </Screen>

    <!-- 7. Completion ------------------------------------------------------------ -->
    <Screen title="Study complete">
      <p class="selectable-text large">Completion code:</p>
      <p class="selectable-text large">{{ config.completionCode }}</p>
      <p v-if="$magpie.mode === 'prolific'">
        <a :href="$magpie.completionUrl">Click here to return to Prolific.</a>
      </p>
    </Screen>
  </Experiment>
</template>

<script>
import config from "./config";
import MotrTrial from "./components/MotrTrial.vue";
import BrowserCheck from "./components/BrowserCheck.vue";
import { chooseListId, buildPracticeTrials, buildMainTrials } from "./materials";
import { browserInfo } from "./browser";
import { submitRows } from "./submit";

export default {
  name: "App",
  components: { MotrTrial, BrowserCheck },
  data() {
    const listId = chooseListId();
    const practiceTrials = buildPracticeTrials();
    const mainTrials = buildMainTrials(listId);
    console.log(`[MoTR] list ${listId}: ${practiceTrials.length} practice + ${mainTrials.length} main trials`, mainTrials);
    return { config, listId, practiceTrials, mainTrials, submitting: false };
  },
  created() {
    // magpie replaces the socket with a stub that raises a "no socket URL is set" warning
    // on *any* access -- including magpie's own nextScreen() -- and renders it as a red box
    // on every screen. This experiment does not use sockets, so drop that one warning.
    this.$watch(
      () => this.$magpie.warning,
      (warning) => {
        if (warning && String(warning).includes("no socket URL")) this.$magpie.warning = null;
      }
    );
  },
  mounted() {
    // Pre-fill the participant ID when the study is launched from Prolific.
    const pid = new URLSearchParams(window.location.search).get("PROLIFIC_PID");
    if (pid) this.$magpie.measurements.SubjectID = pid;
  },
  methods: {
    consent() {
      // Experiment-level data. magpie merges it into the first row of getAllData() only;
      // src/submit.js puts it on the first row of every submission.
      this.$magpie.addExpData({
        SubjectId: this.$magpie.measurements.SubjectID,
        ListId: this.listId,
        Experiment: config.experimentName,
      });
      this.$magpie.nextScreen();
    },

    browserCheckDone() {
      this.$magpie.nextScreen();
    },

    /** Record the survey answers, submit, and go to the completion screen. */
    async finish() {
      this.submitting = true;
      const m = this.$magpie.measurements;
      this.$magpie.addTrialData({
        Experiment: config.experimentName,
        TrialType: "survey",
        device: m.device || null,
        hand: m.hand || null,
        feedback: m.feedback || null,
        ...browserInfo(),
        userAgent: navigator.userAgent,
      });
      const all = this.$magpie.getAllData();
      // With per-trial submission only the survey row is still unsent.
      const payload = config.submitEachTrial ? [all[all.length - 1]] : all;
      try {
        await submitRows(this.$magpie, payload, "final");
      } catch (err) {
        // already logged; the completion code is shown regardless
      }
      this.submitting = false;
      this.$magpie.nextScreen();
    },
  },
};
</script>

<style>
.browser-check-text {
  width: 40em;
  max-width: 90%;
  margin: 0 auto;
  text-align: left;
  white-space: normal;
}

.broweser-check-text * {
  white-space: normal;
}

.experiment {
  display: flex;
  align-items: center;
  justify-content: center;
}
.consent {
  width: 40em;
  max-width: 100%;
  margin: auto;
  text-align: left;
}
.consent .box {
  background-color: lightgrey;
  padding: 10px;
  margin: 1em 0;
}
.consent ul {
  padding-left: 30px;
}
.large {
  font-size: 24px;
}

/* Prevent text selection so participants cannot drag-select the sentence. */
* {
  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
}
.selectable-text {
  -webkit-user-select: text;
  -moz-user-select: text;
  -ms-user-select: text;
  user-select: text;
}
</style>
