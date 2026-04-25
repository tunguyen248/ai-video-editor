<template>
  <div class="player-shell">
    <video ref="videoEl" class="video-js vjs-big-play-centered editor-video" controls playsinline preload="auto"></video>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import videojs from 'video.js'
import 'video.js/dist/video-js.css'

const props = defineProps({
  source: { type: String, default: '' },
  type: { type: String, default: 'video/mp4' },
})

const videoEl = ref(null)
let player = null

const setSource = source => {
  if (!player || !source) return
  player.src({ src: source, type: props.type || 'video/mp4' })
}

const seekTo = time => {
  if (!player) return
  player.currentTime(Math.max(0, Number(time) || 0))
}

const playFrom = async time => {
  seekTo(time)
  try {
    await player.play()
  } catch {
    // Browser autoplay rules can reject programmatic playback until user gesture.
  }
}

onMounted(async () => {
  await nextTick()
  player = videojs(videoEl.value, {
    fluid: true,
    responsive: true,
    controls: true,
    playbackRates: [0.5, 1, 1.5, 2],
  })
  setSource(props.source)
})

watch(() => props.source, source => setSource(source))
watch(() => props.type, () => setSource(props.source))

onBeforeUnmount(() => {
  if (player) {
    player.dispose()
    player = null
  }
})

defineExpose({ seekTo, playFrom })
</script>

<style scoped>
.player-shell {
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  overflow: hidden;
}

.editor-video {
  width: 100%;
  min-height: 320px;
}
</style>
