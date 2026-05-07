<template>
  <section class="canvas-workspace glass-panel" aria-label="Template canvas">
    <div class="canvas-header">
      <div>
        <strong>1080x1920 Preview</strong>
        <span>{{ statusLabel }}</span>
      </div>
      <button type="button" class="play-button" :disabled="!sourceVideoUrl" @click="togglePlayback">
        {{ isPlaying ? 'Pause' : 'Play' }}
      </button>
    </div>

    <div class="canvas-stage">
      <div class="phone-frame" :style="frameStyle">
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
})

const emit = defineEmits(['select-layer', 'update-destination'])

const sourceVideo = ref(null)
const previewCanvas = ref(null)
const animationFrameId = ref(null)
const isPlaying = ref(false)
const videoReady = ref(false)
const videoError = ref(false)
const activeInteraction = ref(null)

const resizeHandles = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']

const outputWidth = computed(() => Number(props.template?.output?.width || 1080))
const outputHeight = computed(() => Number(props.template?.output?.height || 1920))
const scale = computed(() => Number(props.previewScale || 0.35))
const previewWidth = computed(() => Math.round(outputWidth.value * scale.value))
const previewHeight = computed(() => Math.round(outputHeight.value * scale.value))

const frameStyle = computed(() => ({
  '--preview-width': `${previewWidth.value}px`,
  '--preview-height': `${previewHeight.value}px`,
}))

const visibleLayers = computed(() => (
  [...(props.template?.layers || [])]
    .filter(layer => layer.type === 'videoCrop' && layer.visible !== false && !layer.hidden)
    .sort((a, b) => Number(a.zIndex || 0) - Number(b.zIndex || 0))
))

const statusLabel = computed(() => {
  if (!props.sourceVideoUrl) return 'Waiting for source'
  if (videoError.value) return 'Source failed to load'
  if (!videoReady.value) return 'Loading source'
  return `${visibleLayers.value.length} visible crop layers`
})

function safeNumber(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function layerRect(layer) {
  const rect = layer.destinationRect || {}
  return {
    x: safeNumber(rect.x, 0),
    y: safeNumber(rect.y, 0),
    width: Math.max(1, safeNumber(rect.width, outputWidth.value)),
    height: Math.max(1, safeNumber(rect.height, outputHeight.value)),
  }
}

function sourceRect(layer, video) {
  const rect = layer.sourceRect || {}
  return {
    x: safeNumber(rect.x, 0),
    y: safeNumber(rect.y, 0),
    width: Math.max(1, safeNumber(rect.width, video.videoWidth || 1920)),
    height: Math.max(1, safeNumber(rect.height, video.videoHeight || 1080)),
  }
}

function boxStyle(layer) {
  const rect = layerRect(layer)
  return {
    left: `${rect.x * scale.value}px`,
    top: `${rect.y * scale.value}px`,
    width: `${rect.width * scale.value}px`,
    height: `${rect.height * scale.value}px`,
    zIndex: 20 + Number(layer.zIndex || 0),
    opacity: layer.id === props.selectedLayerId ? 1 : 0.82,
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
  ctx.fillText('Load a gameplay video to preview crops', previewWidth.value / 2, previewHeight.value / 2)
  ctx.restore()
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

  for (const layer of visibleLayers.value) {
    const source = sourceRect(layer, video)
    const destination = layerRect(layer)

    ctx.save()
    ctx.globalAlpha = Math.max(0, Math.min(1, safeNumber(layer.opacity, 1)))

    try {
      ctx.drawImage(
        video,
        source.x,
        source.y,
        source.width,
        source.height,
        destination.x * scale.value,
        destination.y * scale.value,
        destination.width * scale.value,
        destination.height * scale.value,
      )
    } catch {
      ctx.fillStyle = 'rgba(239, 68, 68, 0.18)'
      ctx.fillRect(
        destination.x * scale.value,
        destination.y * scale.value,
        destination.width * scale.value,
        destination.height * scale.value,
      )
    }

    ctx.restore()
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
  videoReady.value = true
  videoError.value = false
  drawCurrentFrame()
}

function handleVideoError() {
  videoReady.value = false
  videoError.value = true
  stopRenderLoop()
}

function clampRect(rect) {
  const minSize = 24
  const width = Math.max(minSize, Math.min(outputWidth.value, rect.width))
  const height = Math.max(minSize, Math.min(outputHeight.value, rect.height))
  const x = Math.max(0, Math.min(outputWidth.value - width, rect.x))
  const y = Math.max(0, Math.min(outputHeight.value - height, rect.y))

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
    startRect: layerRect(layer),
  }

  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', stopInteraction, { once: true })
}

function handlePointerMove(event) {
  if (!activeInteraction.value) return

  const interaction = activeInteraction.value
  const dx = (event.clientX - interaction.startX) / scale.value
  const dy = (event.clientY - interaction.startY) / scale.value
  const nextRect = interaction.mode === 'move'
    ? clampRect({
      ...interaction.startRect,
      x: interaction.startRect.x + dx,
      y: interaction.startRect.y + dy,
    })
    : resizeRect(interaction.startRect, interaction.mode, dx, dy)

  emit('update-destination', interaction.layerId, nextRect)
}

function stopInteraction() {
  activeInteraction.value = null
  window.removeEventListener('pointermove', handlePointerMove)
}

watch(
  () => [props.template, props.previewScale],
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

.phone-frame {
  position: relative;
  width: var(--preview-width);
  height: var(--preview-height);
  overflow: hidden;
  border: 1px solid rgba(103, 232, 249, 0.24);
  border-radius: 14px;
  background: #050505;
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
  border: 1px solid rgba(103, 232, 249, 0.78);
  background: rgba(34, 211, 238, 0.05);
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.3), 0 0 24px rgba(34, 211, 238, 0.14);
  cursor: move;
  pointer-events: auto;
  touch-action: none;
}

.crop-box.selected {
  border-color: #c084fc;
  background: rgba(192, 132, 252, 0.08);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.12), 0 0 28px rgba(192, 132, 252, 0.22);
}

.crop-label {
  position: absolute;
  left: 6px;
  top: 6px;
  max-width: calc(100% - 12px);
  overflow: hidden;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.66);
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
  background: #c084fc;
  box-shadow: 0 0 12px rgba(192, 132, 252, 0.42);
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
