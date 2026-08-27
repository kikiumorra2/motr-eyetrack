<!--
  BrowserCheck — asks the participant to set the browser zoom to 100% before the study.
  The MoTR window and the word boxes are defined in CSS pixels, so a zoomed page changes
  their physical size on screen. The check re-runs whenever the window is resized (zoom
  changes fire a resize event). Settings: config.browserCheck.
-->
<template>
  <div class="browser-check">
    <template v-if="zoomOk">
      <p>&#10003; Your browser zoom is set to 100%.</p>
    </template>
    <template v-else>
      <p>
        <b>Please set your browser zoom to 100%.</b>
        It is currently about {{ zoom }}%.
      </p>
      <p>
        Press <kbd>Ctrl</kbd> + <kbd>0</kbd> (Windows / Linux) or <kbd>&#8984;</kbd> +
        <kbd>0</kbd> (Mac) to reset the zoom. This page updates automatically.
      </p>
    </template>
    <p>
      Please use a desktop or laptop computer with a mouse or trackpad, keep this window
      open and do not change the zoom until the study is complete.
    </p>
    <button v-if="zoomOk" @click="$emit('done')">Continue</button>
    <p v-else-if="canSkip">
      <a href="#" @click.prevent="$emit('done')">I cannot change the zoom &ndash; continue anyway</a>
    </p>
  </div>
</template>

<script>
import config from "../config";
import { zoomPercent } from "../browser";

export default {
  name: "BrowserCheck",
  data() {
    return { zoom: zoomPercent(), canSkip: false, skipTimer: null };
  },
  computed: {
    zoomOk() {
      const c = config.browserCheck;
      if (!c.requireZoom100 || this.zoom === null) return true;
      return Math.abs(this.zoom - 100) <= c.zoomTolerance;
    },
  },
  mounted() {
    window.addEventListener("resize", this.update);
    const seconds = config.browserCheck.allowSkipAfterSeconds;
    if (seconds > 0) this.skipTimer = setTimeout(() => (this.canSkip = true), seconds * 1000);
  },
  beforeDestroy() {
    window.removeEventListener("resize", this.update);
    clearTimeout(this.skipTimer);
  },
  methods: {
    update() {
      this.zoom = zoomPercent();
    },
  },
};
</script>

<style>
.browser-check kbd {
  border: 1px solid #999;
  border-radius: 3px;
  padding: 0 4px;
  font-family: inherit;
}
</style>
