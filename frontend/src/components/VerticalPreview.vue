<template>
  <section class="preview-shell" aria-label="Vertical template preview">
    <div class="phone-frame" :style="frameStyle">
      <template v-if="sourceVideoUrl">
        <video
          ref="sourceVideo"
          class="hidden-video"
          :src="sourceVideoUrl"
          muted
          playsinline
          preload="metadata"
          @loadedmetadata="handleLoadedMetadata"
          @play="startRenderLoop"
          @pause="stopRenderLoop"
          @seeking="drawCurrentFrame"
          @seeked="drawCurrentFrame"
          @ratechange="drawCurrentFrame"
          @ended="stopRenderLoop"
        ></video>

        <canvas
          ref="previewCanvas"
          class="preview-canvas"
          :width="previewWidth"
          :height="previewHeight"
        ></canvas>

        <div v-if="isLoading" class="canvas-status">Loading preview...</div>
      </template>

      <div v-else class="preview-placeholder">
        <strong>9:16 Template Preview</strong>
        <span>{{ template?.name || 'Select a template' }}</span>
      </div>
    </div>

    <div class="preview-meta">
      <span>{{ template?.game || 'Game' }}</span>
      <strong>{{ template?.name || 'No template selected' }}</strong>
      <small>{{ outputLabel }}</small>

      <button
        v-if="sourceVideoUrl"
        type="button"
        class="play-button"
        @click="togglePlayback"
      >
        {{ isPlaying ? 'Pause preview' : 'Play preview' }}
      </button>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  sourceVideoUrl: {
    type: String,
    default: '',
  },
  template: {
    type: Object,
    default: null,
  },
  params: {
    type: Object,
    default: () => ({}),
  },
})

const sourceVideo = ref(null)
const previewCanvas = ref(null)
const animationFrameId = ref(null)
const isPlaying = ref(false)
const isLoading = ref(false)

const PREVIEW_SCALE = 0.35

const output = computed(() => props.template?.output || {})
const outputWidth = computed(() => Number(output.value.width || 1080))
const outputHeight = computed(() => Number(output.value.height || 1920))
const previewWidth = computed(() => Math.round(outputWidth.value * PREVIEW_SCALE))
const previewHeight = computed(() => Math.round(outputHeight.value * PREVIEW_SCALE))

const outputLabel = computed(() => {
  const fps = output.value.fps || 60
  const format = String(output.value.format || 'mp4').toUpperCase()
  return `${outputWidth.value}x${outputHeight.value} / ${fps} FPS / ${format}`
})

const backgroundBlur = computed(() => Math.max(0, Number(props.params.backgroundBlur ?? 18)))
const debugBoxes = computed(() => Boolean(props.params.debugBoxes ?? false))

const frameStyle = computed(() => ({
  '--preview-width': `${previewWidth.value}px`,
  '--preview-height': `${previewHeight.value}px`,
}))

const sortedLayers = computed(() => {
  const layers = props.template?.layers || []
  return [...layers].sort((a, b) => Number(a.zIndex || 0) - Number(b.zIndex || 0))
})

const controlValue = (id, fallback) => Number(props.params?.[id] ?? fallback)

const scaleRect = (rect) => ({
  x: Number(rect.x || 0) * PREVIEW_SCALE,
  y: Number(rect.y || 0) * PREVIEW_SCALE,
  width: Number(rect.width || 0) * PREVIEW_SCALE,
  height: Number(rect.height || 0) * PREVIEW_SCALE,
})

const getSourceRect = (layer, video) => {
  const source = layer.sourceRect
  if (!source) {
    return {
      x: 0,
      y: 0,
      width: video.videoWidth,
      height: video.videoHeight,
    }
  }

  return {
    x: Number(source.x || 0),
    y: Number(source.y || 0),
    width: Number(source.width || video.videoWidth),
    height: Number(source.height || video.videoHeight),
  }
}

const getDestinationRect = (layer) => {
  const destination = layer.destinationRect || layer.transform || {}
  return scaleRect({
    x: destination.x || 0,
    y: destination.y || 0,
    width: destination.width || outputWidth.value,
    height: destination.height || outputHeight.value,
  })
}

const drawCoverVideo = (ctx, video, layer) => {
  const destination = getDestinationRect(layer)
  const sourceRatio = video.videoWidth / video.videoHeight
  const destinationRatio = destination.width / destination.height

  let sx = 0
  let sy = 0
  let sw = video.videoWidth
  let sh = video.videoHeight

  if (sourceRatio > destinationRatio) {
    sw = video.videoHeight * destinationRatio
    sx = (video.videoWidth - sw) / 2
  } else {
    sh = video.videoWidth / destinationRatio
    sy = (video.videoHeight - sh) / 2
  }

  ctx.save()
  if (layer.blur || backgroundBlur.value > 0) {
    ctx.filter = `blur(${backgroundBlur.value * PREVIEW_SCALE}px)`
  }
  ctx.globalAlpha = Number(layer.opacity ?? 1)
  ctx.drawImage(video, sx, sy, sw, sh, destination.x, destination.y, destination.width, destination.height)
  ctx.restore()
}

const drawVideoCrop = (ctx, video, layer) => {
  const source = getSourceRect(layer, video)
  const destination = getDestinationRect(layer)

  ctx.save()
  ctx.globalAlpha = Number(layer.opacity ?? 1)

  const radius = Number(layer.borderRadius || 0) * PREVIEW_SCALE
  if (radius > 0) {
    roundedClip(ctx, destination.x, destination.y, destination.width, destination.height, radius)
  }

  ctx.drawImage(
    video,
    source.x,
    source.y,
    source.width,
    source.height,
    destination.x,
    destination.y,
    destination.width,
    destination.height,
  )

  if (debugBoxes.value || layer.debug) {
    ctx.lineWidth = 3
    ctx.strokeStyle = layer.debugColor || '#ef4444'
    ctx.strokeRect(destination.x, destination.y, destination.width, destination.height)
  }

  ctx.restore()
}

const roundedClip = (ctx, x, y, width, height, radius) => {
  const r = Math.min(radius, width / 2, height / 2)
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.lineTo(x + width - r, y)
  ctx.quadraticCurveTo(x + width, y, x + width, y + r)
  ctx.lineTo(x + width, y + height - r)
  ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height)
  ctx.lineTo(x + r, y + height)
  ctx.quadraticCurveTo(x, y + height, x, y + height - r)
  ctx.lineTo(x, y + r)
  ctx.quadraticCurveTo(x, y, x + r, y)
  ctx.closePath()
  ctx.clip()
}

const drawCurrentFrame = () => {
  const video = sourceVideo.value
  const canvas = previewCanvas.value
  if (!video || !canvas || !video.videoWidth || !video.videoHeight) return

  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.fillStyle = props.template?.output?.background || '#050505'
  ctx.fillRect(0, 0, canvas.width, canvas.height)

  for (const layer of sortedLayers.value) {
    if (layer.hidden || layer.visible === false) continue

    if (layer.type === 'videoFill') {
      drawCoverVideo(ctx, video, layer)
    }

    if (layer.type === 'videoCrop') {
      drawVideoCrop(ctx, video, layer)
    }
  }
}

const renderLoop = () => {
  drawCurrentFrame()
  animationFrameId.value = requestAnimationFrame(renderLoop)
}

const startRenderLoop = () => {
  if (animationFrameId.value) return
  isPlaying.value = true
  renderLoop()
}

const stopRenderLoop = () => {
  isPlaying.value = false
  if (animationFrameId.value) {
    cancelAnimationFrame(animationFrameId.value)
    animationFrameId.value = null
  }
  drawCurrentFrame()
}

const handleLoadedMetadata = () => {
  isLoading.value = false
  drawCurrentFrame()
}

const togglePlayback = async () => {
  const video = sourceVideo.value
  if (!video) return

  if (video.paused) {
    isLoading.value = true
    try {
      await video.play()
      isLoading.value = false
      startRenderLoop()
    } catch {
      isLoading.value = false
    }
  } else {
    video.pause()
    stopRenderLoop()
  }
}

watch(
  () => [props.sourceVideoUrl, props.template, props.params],
  () => {
    nextTick(() => {
      stopRenderLoop()
      drawCurrentFrame()
    })
  },
  { deep: true },
)

watch(
  () => [controlValue('gameplayScale', 1), controlValue('gameplayX', 0), controlValue('gameplayY', 0)],
  () => drawCurrentFrame(),
)

onBeforeUnmount(() => {
  stopRenderLoop()
})
</script>

<style scoped>
.preview-shell {
  display: grid;
  grid-template-columns: minmax(230px, var(--preview-width, 540px)) minmax(180px, 1fr);
  align-items: center;
  justify-content: center;
  gap: 24px;
  width: min(900px, 100%);
  margin: 0 auto;
}

.phone-frame {
  position: relative;
  aspect-ratio: 9 / 16;
  width: min(var(--preview-width, 540px), 100%);
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 14px;
  background: #050505;
  box-shadow: 0 28px 90px rgba(0, 0, 0, 0.58);
}

.hidden-video {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.preview-canvas {
  width: 100%;
  height: 100%;
  display: block;
  background: #050505;
}

.canvas-status {
  position: absolute;
  left: 50%;
  bottom: 18px;
  transform: translateX(-50%);
  padding: 7px 10px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.68);
  color: #f4f4f5;
  font-size: 12px;
}

.preview-placeholder {
  height: 100%;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 6px;
  background:
    linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    #090a0b;
  background-size: 28px 28px;
  text-align: center;
}

.preview-placeholder strong {
  color: #f4f4f5;
}

.preview-placeholder span {
  color: #8a8f98;
  font-size: 12px;
}

.preview-meta {
  display: grid;
  gap: 8px;
}

.preview-meta span {
  color: #67e8f9;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.preview-meta strong {
  color: #f4f4f5;
  font-size: 28px;
  line-height: 1.05;
}

.preview-meta small {
  color: #a1a1aa;
  font-size: 13px;
}

.play-button {
  justify-self: start;
  margin-top: 10px;
  border: 1px solid rgba(103, 232, 249, 0.32);
  border-radius: 999px;
  background: rgba(103, 232, 249, 0.12);
  color: #cffafe;
  cursor: pointer;
  font-weight: 700;
  padding: 9px 13px;
}

@media (max-width: 760px) {
  .preview-shell {
    grid-template-columns: 1fr;
  }

  .phone-frame {
    justify-self: center;
    width: min(360px, 100%);
  }
}
</style>
