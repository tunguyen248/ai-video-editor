<template>
  <section class="canvas-workspace glass-panel" :class="`${canvasMode}-mode`" aria-label="Template canvas">
    <div class="canvas-header">
      <div>
        <strong>{{ canvasTitle }}</strong>
        <span>{{ statusLabel }}</span>
      </div>
      <button type="button" class="play-button" :disabled="!sourceVideoUrl" @click="togglePlayback">
        {{ isPlaying ? 'Pause' : 'Play' }}
      </button>
    </div>

    <div class="canvas-stage">
      <div class="preview-frame" :class="frameClass" :style="frameStyle">
        <video
          v-if="sourceVideoUrl"
          ref="sourceVideo"
          class="hidden-video"
          :src="sourceVideoUrl"
          muted
          playsinline
          loop
          preload="metadata"
          @loadedmetadata="handleLoadedMetadata"
          @error="handleVideoError"
          @play="startRenderLoop"
          @pause="stopRenderLoop"
          @seeked="drawCurrentFrame"
        ></video>

        <canvas
          ref="previewCanvas"
          class="preview-canvas"
          :width="previewWidth"
          :height="previewHeight"
        ></canvas>

        <div class="interaction-layer" :style="frameStyle">
          <div
            v-for="layer in visibleLayers"
            :key="layer.id"
            class="crop-box"
            :class="{ selected: layer.id === selectedLayerId }"
            :style="boxStyle(layer)"
            @pointerdown.stop.prevent="startInteraction($event, layer, 'move')"
          >
            <span class="crop-label">{{ layer.name }}</span>
            <template v-if="layer.id === selectedLayerId">
              <i
                v-for="handle in resizeHandles"
                :key="handle"
                class="resize-handle"
                :class="`handle-${handle}`"
                @pointerdown.stop.prevent="startInteraction($event, layer, handle)"
              ></i>
            </template>
          </div>
        </div>

        <div v-if="!sourceVideoUrl" class="canvas-status">No video source</div>
        <div v-else-if="videoError" class="canvas-status error">Video unavailable</div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  template: {
    type: Object,
    required: true,
  },
  sourceVideoUrl: {
    type: String,
    default: '',
  },
  selectedLayerId: {
    type: String,
    default: '',
  },
  previewScale: {
    type: Number,
    default: 0.35,
  },
  canvasMode: {
    type: String,
    default: 'source',
    validator: value => ['source', 'output'].includes(value),
  },
})

const emit = defineEmits(['select-layer', 'update-source', 'update-destination', 'update-source-size'])

const sourceVideo = ref(null)
const previewCanvas = ref(null)
const animationFrameId = ref(null)
const isPlaying = ref(false)
const videoReady = ref(false)
const videoError = ref(false)
const activeInteraction = ref(null)

const resizeHandles = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']
const SOURCE_DISPLAY_WIDTH = 1920

const isSourceMode = computed(() => props.canvasMode === 'source')
const outputWidth = computed(() => Number(props.template?.output?.width || 1080))
const outputHeight = computed(() => Number(props.template?.output?.height || 1920))
const sourceDefinition = computed(() => (
  props.template?.sources?.find(source => source.id === 'main-video')
  || props.template?.sources?.[0]
  || props.template?.source
  || {}
))
const sourceFrameWidth = computed(() => Number(sourceDefinition.value.width || 1920))
const sourceFrameHeight = computed(() => Number(sourceDefinition.value.height || 1080))
const frameWidth = computed(() => (isSourceMode.value ? sourceFrameWidth.value : outputWidth.value))
const frameHeight = computed(() => (isSourceMode.value ? sourceFrameHeight.value : outputHeight.value))
const displayFrameWidth = computed(() => (isSourceMode.value ? SOURCE_DISPLAY_WIDTH : outputWidth.value))
const displayFrameHeight = computed(() => {
  if (!isSourceMode.value) return outputHeight.value
  const sourceRatio = sourceFrameHeight.value / Math.max(1, sourceFrameWidth.value)
  return Math.round(SOURCE_DISPLAY_WIDTH * sourceRatio)
})
const scale = computed(() => Number(props.previewScale || 0.35))
const previewWidth = computed(() => Math.round(displayFrameWidth.value * scale.value))
const previewHeight = computed(() => Math.round(displayFrameHeight.value * scale.value))
const xScale = computed(() => previewWidth.value / frameWidth.value)
const yScale = computed(() => previewHeight.value / frameHeight.value)

const frameStyle = computed(() => ({
  '--preview-width': `${previewWidth.value}px`,
  '--preview-height': `${previewHeight.value}px`,
}))

const frameClass = computed(() => (isSourceMode.value ? 'source-frame' : 'output-frame'))
const canvasTitle = computed(() => (isSourceMode.value ? 'Source Crop Boxes' : '1080x1920 Output Preview'))

const visibleLayers = computed(() => (
  [...(props.template?.layers || [])]
    .filter(layer => layer.type === 'videoCrop' && layer.visible !== false && !layer.hidden)
    .sort((a, b) => Number(a.zIndex || 0) - Number(b.zIndex || 0))
))

const statusLabel = computed(() => {
  if (!props.sourceVideoUrl) return 'Waiting for source'
  if (videoError.value) return 'Source failed to load'
  if (!videoReady.value) return 'Loading source'
  if (isSourceMode.value) return `Editing sourceRect on ${sourceFrameWidth.value}x${sourceFrameHeight.value}`
  return `${visibleLayers.value.length} visible crop layers in the vertical output`
})

function safeNumber(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function normalizedRect(rect, fallback) {
  return {
    x: safeNumber(rect?.x, fallback.x),
    y: safeNumber(rect?.y, fallback.y),
    width: Math.max(1, safeNumber(rect?.width, fallback.width)),
    height: Math.max(1, safeNumber(rect?.height, fallback.height)),
  }
}

function destinationRect(layer) {
  return normalizedRect(layer.destinationRect, {
    x: 0,
    y: 0,
    width: outputWidth.value,
    height: outputHeight.value,
  })
}

function sourceRect(layer, video = null) {
  return normalizedRect(layer.sourceRect, {
    x: 0,
    y: 0,
    width: video?.videoWidth || sourceFrameWidth.value,
    height: video?.videoHeight || sourceFrameHeight.value,
  })
}

function editableRect(layer) {
  return isSourceMode.value ? sourceRect(layer) : destinationRect(layer)
}

function boxStyle(layer) {
  const rect = editableRect(layer)
  return {
    left: `${rect.x * xScale.value}px`,
    top: `${rect.y * yScale.value}px`,
    width: `${rect.width * xScale.value}px`,
    height: `${rect.height * yScale.value}px`,
    zIndex: 20 + Number(layer.zIndex || 0),
    opacity: layer.id === props.selectedLayerId ? 1 : 0.86,
  }
}

function drawEmptyState(ctx) {
  ctx.save()
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.055)'
  ctx.lineWidth = 1
  for (let x = 0; x < previewWidth.value; x += 28) {
    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x, previewHeight.value)
    ctx.stroke()
  }
  for (let y = 0; y < previewHeight.value; y += 28) {
    ctx.beginPath()
    ctx.moveTo(0, y)
    ctx.lineTo(previewWidth.value, y)
    ctx.stroke()
  }
  ctx.fillStyle = 'rgba(244, 244, 245, 0.72)'
  ctx.font = '600 13px Inter, system-ui, sans-serif'
  ctx.textAlign = 'center'
  ctx.fillText('Load a gameplay video to preview crop boxes', previewWidth.value / 2, previewHeight.value / 2)
  ctx.restore()
}

function drawSourceFrame(ctx, video) {
  ctx.drawImage(
    video,
    0,
    0,
    video.videoWidth,
    video.videoHeight,
    0,
    0,
    previewWidth.value,
    previewHeight.value,
  )
}

function drawOutputFrame(ctx, video) {
  for (const layer of visibleLayers.value) {
    const source = sourceRect(layer, video)
    const destination = destinationRect(layer)

    ctx.save()
    ctx.globalAlpha = Math.max(0, Math.min(1, safeNumber(layer.opacity, 1)))

    try {
      ctx.drawImage(
        video,
        source.x,
        source.y,
        source.width,
        source.height,
        destination.x * xScale.value,
        destination.y * yScale.value,
        destination.width * xScale.value,
        destination.height * yScale.value,
      )
    } catch {
      ctx.fillStyle = 'rgba(239, 68, 68, 0.18)'
      ctx.fillRect(
        destination.x * xScale.value,
        destination.y * yScale.value,
        destination.width * xScale.value,
        destination.height * yScale.value,
      )
    }

    ctx.restore()
  }
}

function drawCurrentFrame() {
  const canvas = previewCanvas.value
  if (!canvas) return

  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.fillStyle = props.template?.output?.background || '#101010'
  ctx.fillRect(0, 0, canvas.width, canvas.height)

  const video = sourceVideo.value
  if (!video || !videoReady.value || videoError.value || !video.videoWidth || !video.videoHeight) {
    drawEmptyState(ctx)
    return
  }

  if (isSourceMode.value) {
    drawSourceFrame(ctx, video)
  } else {
    drawOutputFrame(ctx, video)
  }
}

function renderLoop() {
  drawCurrentFrame()
  animationFrameId.value = requestAnimationFrame(renderLoop)
}

function startRenderLoop() {
  if (animationFrameId.value) return
  isPlaying.value = true
  renderLoop()
}

function stopRenderLoop() {
  isPlaying.value = false
  if (animationFrameId.value) {
    cancelAnimationFrame(animationFrameId.value)
    animationFrameId.value = null
  }
  drawCurrentFrame()
}

async function togglePlayback() {
  const video = sourceVideo.value
  if (!video) return

  if (video.paused) {
    try {
      await video.play()
      startRenderLoop()
    } catch {
      videoError.value = true
      drawCurrentFrame()
    }
  } else {
    video.pause()
    stopRenderLoop()
  }
}

function handleLoadedMetadata() {
  const video = sourceVideo.value
  videoReady.value = true
  videoError.value = false
  if (video?.videoWidth && video?.videoHeight) {
    emit('update-source-size', {
      width: video.videoWidth,
      height: video.videoHeight,
    })
  }
  drawCurrentFrame()
}

function handleVideoError() {
  videoReady.value = false
  videoError.value = true
  stopRenderLoop()
}

function clampRect(rect) {
  const minSize = 24
  const width = Math.max(minSize, Math.min(frameWidth.value, rect.width))
  const height = Math.max(minSize, Math.min(frameHeight.value, rect.height))
  const x = Math.max(0, Math.min(frameWidth.value - width, rect.x))
  const y = Math.max(0, Math.min(frameHeight.value - height, rect.y))

  return {
    x: Math.round(x),
    y: Math.round(y),
    width: Math.round(width),
    height: Math.round(height),
  }
}

function resizeRect(startRect, mode, dx, dy) {
  const rect = { ...startRect }

  if (mode.includes('e')) rect.width = startRect.width + dx
  if (mode.includes('s')) rect.height = startRect.height + dy
  if (mode.includes('w')) {
    rect.x = startRect.x + dx
    rect.width = startRect.width - dx
  }
  if (mode.includes('n')) {
    rect.y = startRect.y + dy
    rect.height = startRect.height - dy
  }

  if (rect.width < 24) {
    if (mode.includes('w')) rect.x = startRect.x + startRect.width - 24
    rect.width = 24
  }

  if (rect.height < 24) {
    if (mode.includes('n')) rect.y = startRect.y + startRect.height - 24
    rect.height = 24
  }

  return clampRect(rect)
}

function startInteraction(event, layer, mode) {
  emit('select-layer', layer.id)
  activeInteraction.value = {
    layerId: layer.id,
    mode,
    startX: event.clientX,
    startY: event.clientY,
    startRect: editableRect(layer),
  }

  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', stopInteraction, { once: true })
}

function handlePointerMove(event) {
  if (!activeInteraction.value) return

  const interaction = activeInteraction.value
  const dx = (event.clientX - interaction.startX) / xScale.value
  const dy = (event.clientY - interaction.startY) / yScale.value
  const nextRect = interaction.mode === 'move'
    ? clampRect({
      ...interaction.startRect,
      x: interaction.startRect.x + dx,
      y: interaction.startRect.y + dy,
    })
    : resizeRect(interaction.startRect, interaction.mode, dx, dy)

  emit(isSourceMode.value ? 'update-source' : 'update-destination', interaction.layerId, nextRect)
}

function stopInteraction() {
  activeInteraction.value = null
  window.removeEventListener('pointermove', handlePointerMove)
}

watch(
  () => [props.template, props.previewScale, props.canvasMode],
  () => nextTick(drawCurrentFrame),
  { deep: true },
)

watch(
  () => props.sourceVideoUrl,
  () => {
    videoReady.value = false
    videoError.value = false
    stopRenderLoop()
    nextTick(() => {
      const video = sourceVideo.value
      if (video) video.load()
      drawCurrentFrame()
    })
  },
)

onBeforeUnmount(() => {
  stopRenderLoop()
  window.removeEventListener('pointermove', handlePointerMove)
})
</script>

<style scoped>
.glass-panel {
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.075), rgba(255, 255, 255, 0.035));
  backdrop-filter: blur(30px);
  box-shadow: 0 20px 70px rgba(0, 0, 0, 0.48);
}

.canvas-workspace {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
}

.canvas-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.canvas-header div {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.canvas-header strong {
  color: #f4f4f5;
  font-size: 13px;
}

.canvas-header span {
  color: #8a8f98;
  font-size: 12px;
}

.play-button {
  border: 0;
  border-radius: 8px;
  background: rgba(124, 58, 237, 0.24);
  color: #ede9fe;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 800;
  padding: 9px 13px;
}

.play-button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.canvas-stage {
  min-height: 0;
  display: grid;
  place-items: center;
  overflow: auto;
  padding: 18px;
}

.preview-frame {
  position: relative;
  width: var(--preview-width);
  height: var(--preview-height);
  overflow: hidden;
  border-radius: 14px;
  background: #050505;
  box-shadow:
    0 30px 90px rgba(0, 0, 0, 0.62),
    0 0 0 8px rgba(255, 255, 255, 0.025);
}

.source-frame {
  border: 1px solid rgba(248, 113, 113, 0.36);
  box-shadow:
    0 30px 90px rgba(0, 0, 0, 0.62),
    0 0 0 8px rgba(255, 255, 255, 0.025),
    0 0 44px rgba(248, 113, 113, 0.1);
}

.output-frame {
  border: 1px solid rgba(103, 232, 249, 0.24);
  box-shadow:
    0 30px 90px rgba(0, 0, 0, 0.62),
    0 0 0 8px rgba(255, 255, 255, 0.025),
    0 0 44px rgba(34, 211, 238, 0.12);
}

.hidden-video {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.preview-canvas,
.interaction-layer {
  position: absolute;
  inset: 0;
  width: var(--preview-width);
  height: var(--preview-height);
}

.preview-canvas {
  display: block;
  background: #101010;
}

.interaction-layer {
  pointer-events: none;
}

.crop-box {
  position: absolute;
  min-width: 12px;
  min-height: 12px;
  cursor: move;
  pointer-events: auto;
  touch-action: none;
}

.source-mode .crop-box {
  border: 2px solid rgba(248, 45, 45, 0.95);
  background: rgba(248, 45, 45, 0.045);
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.34), 0 0 24px rgba(248, 45, 45, 0.16);
}

.output-mode .crop-box {
  border: 1px solid rgba(103, 232, 249, 0.78);
  background: rgba(34, 211, 238, 0.05);
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.3), 0 0 24px rgba(34, 211, 238, 0.14);
}

.source-mode .crop-box.selected,
.output-mode .crop-box.selected {
  border-color: #67e8f9;
  background: rgba(34, 211, 238, 0.08);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.14), 0 0 28px rgba(34, 211, 238, 0.24);
}

.crop-label {
  position: absolute;
  left: 6px;
  top: 6px;
  max-width: calc(100% - 12px);
  overflow: hidden;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.68);
  color: #ecfeff;
  font-size: 10px;
  font-weight: 800;
  line-height: 1;
  padding: 5px 6px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resize-handle {
  position: absolute;
  width: 10px;
  height: 10px;
  border: 1px solid rgba(5, 5, 5, 0.85);
  border-radius: 50%;
  background: #67e8f9;
  box-shadow: 0 0 12px rgba(34, 211, 238, 0.42);
}

.handle-nw { left: -5px; top: -5px; cursor: nwse-resize; }
.handle-n { left: calc(50% - 5px); top: -5px; cursor: ns-resize; }
.handle-ne { right: -5px; top: -5px; cursor: nesw-resize; }
.handle-e { right: -5px; top: calc(50% - 5px); cursor: ew-resize; }
.handle-se { right: -5px; bottom: -5px; cursor: nwse-resize; }
.handle-s { left: calc(50% - 5px); bottom: -5px; cursor: ns-resize; }
.handle-sw { left: -5px; bottom: -5px; cursor: nesw-resize; }
.handle-w { left: -5px; top: calc(50% - 5px); cursor: ew-resize; }

.canvas-status {
  position: absolute;
  left: 50%;
  bottom: 18px;
  z-index: 200;
  transform: translateX(-50%);
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.72);
  color: #d4d4d8;
  font-size: 12px;
  font-weight: 750;
  padding: 8px 11px;
  pointer-events: none;
}

.canvas-status.error {
  color: #fecaca;
}
</style>
