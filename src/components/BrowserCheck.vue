<!--
  BrowserCheck — asks the participant to set the browser zoom to 100% before the study.
  The MoTR window and the word boxes are defined in CSS pixels, so a zoomed page changes
  their physical size on screen. The check re-runs whenever the window is resized (zoom
  changes fire a resize event). Settings: config.browserCheck.
-->
<template>
  <div class="browser-check">
    <p>
      <b>Please reset your browser zoom to 100% before continuing.</b>
    </p>

    <p>
      Press <kbd>Ctrl</kbd> + <kbd>0</kbd> on Windows/Linux,
      or <kbd>&#8984;</kbd> + <kbd>0</kbd> on Mac.
    </p>
    
    <p>
      Please use a desktop or laptop computer with a mouse or trackpad, keep this window
      open and do not change the zoom until the study is complete.
    </p>
    <button @click="$emit('done')">
      I have reset the zoom to 100%
    </button>
  </div>
</template>

<script>

export default {
  name: "BrowserCheck",
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
