<template>
  <div class="template-builder-shell">
    <header class="builder-topbar">
      <div class="brand-stack">
        <a href="#/lab" class="brand-link" aria-label="Back to video lab">
          <span class="brand-mark">A</span>
          <span>
            <strong>Template Builder</strong>
            <small>9:16 Gaming Layouts</small>
          </span>
        </a>
      </div>

      <div class="template-meta">
        <label>
          <span>Name</span>
          <input v-model="template.name" spellcheck="false" />
        </label>
        <label>
          <span>ID</span>
          <input v-model="template.id" spellcheck="false" />
        </label>
      </div>

      <div class="topbar-actions">
        <button type="button" class="ghost-button" @click="resetTemplate">Reset</button>
        <button type="button" class="primary-button" @click="addLayer">Add Crop Layer</button>
      </div>
    </header>

    <main class="builder-layout">
      <LayerPanel
        :layers="template.layers"
        :selected-layer-id="selectedLayerId"
        @select="selectLayer"
        @add="addLayer"
        @duplicate="duplicateLayer"
        @delete="deleteLayer"
        @toggle-visible="toggleLayerVisibility"
        @move-layer="moveLayer"
      />

      <section class="stage-column">
        <div class="source-toolbar glass-panel">
          <label class="file-drop" @dragover.prevent @drop.prevent="handleVideoDrop">
            <input type="file" accept="video/*" @change="handleVideoFile" />
            <span>{{ selectedFileName || 'Load gameplay video' }}</span>
          </label>

          <label class="source-field">
            <span>Source URL</span>
            <input v-model="sourceInput" spellcheck="false" @change="applySourceUrl" />
          </label>

          <div class="mode-switch" aria-label="Canvas edit mode">
            <button
              type="button"
              :class="{ active: canvasMode === 'source' }"
              @click="canvasMode = 'source'"
            >
              Source Boxes
            </button>
            <button
              type="button"
              :class="{ active: canvasMode === 'output' }"
              @click="canvasMode = 'output'"
            >
              9:16 Output
            </button>
          </div>

          <label class="source-field compact">
            <span>Scale</span>
            <select v-model.number="previewScale">
              <option :value="0.5">50%</option>
              <option :value="0.65">65%</option>
              <option :value="0.75">75%</option>
              <option :value="0.9">90%</option>
              <option :value="1">100%</option>
            </select>
          </label>
        </div>

        <TemplateCanvas
          :template="generatedTemplate"
          :source-video-url="sourceVideoUrl"
          :selected-layer-id="selectedLayerId"
          :preview-scale="previewScale"
          :canvas-mode="canvasMode"
          @select-layer="selectLayer"
          @update-source="updateLayerSource"
          @update-destination="updateLayerDestination"
          @update-source-size="updateSourceSize"
        />
      </section>

      <aside class="right-stack">
        <LayerInspector
          :layer="selectedLayer"
          :output-size="template.output"
          :source-size="sourceSize"
          @update-layer="updateLayer"
        />

        <JsonPreview :template="generatedTemplate" />
      </aside>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import JsonPreview from './components/JsonPreview.vue'
import LayerInspector from './components/LayerInspector.vue'
import LayerPanel from './components/LayerPanel.vue'
import TemplateCanvas from './components/TemplateCanvas.vue'

const SAMPLE_VIDEO_SRC = '/videos/valorant.mp4'

const clone = value => JSON.parse(JSON.stringify(value))

const createLayer = ({
  id,
  name,
  sourceRect,
  destinationRect,
  zIndex,
  opacity = 1,
  visible = true,
}) => ({
  id,
  name,
  type: 'videoCrop',
  sourceId: 'main-video',
  sourceRect,
  destinationRect,
  zIndex,
  opacity,
  visible,
})

const createDefaultTemplate = () => ({
  id: 'valorant_custom_template',
  name: 'Valorant Custom Template',
  game: 'Valorant',
  gameId: 'valorant',
  category: 'Competitive FPS',
  layout: 'Custom HUD Relayout',
  aspectRatio: '9:16',
  output: {
    width: 1080,
    height: 1920,
    fps: 60,
    format: 'mp4',
    background: '#101010',
  },
  sources: [
    {
      id: 'main-video',
      type: 'video',
      src: SAMPLE_VIDEO_SRC,
      width: 1920,
      height: 1080,
    },
  ],
  layers: [
    createLayer({
      id: 'background-gameplay',
      name: 'Background Gameplay',
      sourceRect: { x: 0, y: 0, width: 1920, height: 1080 },
      destinationRect: { x: 0, y: 0, width: 1080, height: 1920 },
      zIndex: 0,
      opacity: 0.38,
    }),
    createLayer({
      id: 'main-gameplay-crop',
      name: 'Main Gameplay Crop',
      sourceRect: { x: 656, y: 0, width: 608, height: 1080 },
      destinationRect: { x: 0, y: 0, width: 1080, height: 1920 },
      zIndex: 5,
      opacity: 1,
    }),
    createLayer({
      id: 'minimap',
      name: 'Minimap',
      sourceRect: { x: 0, y: 0, width: 430, height: 330 },
      destinationRect: { x: 48, y: 72, width: 330, height: 254 },
      zIndex: 10,
      opacity: 1,
    }),
    createLayer({
      id: 'ally-team-bar',
      name: 'Ally Team Bar',
      sourceRect: { x: 480, y: 16, width: 388, height: 118 },
      destinationRect: { x: 420, y: 70, width: 560, height: 170 },
      zIndex: 11,
      opacity: 1,
    }),
    createLayer({
      id: 'enemy-team-bar',
      name: 'Enemy Team Bar',
      sourceRect: { x: 1060, y: 18, width: 396, height: 112 },
      destinationRect: { x: 420, y: 270, width: 560, height: 158 },
      zIndex: 12,
      opacity: 1,
    }),
    createLayer({
      id: 'kill-feed',
      name: 'Kill Feed',
      sourceRect: { x: 1575, y: 42, width: 330, height: 128 },
      destinationRect: { x: 420, y: 468, width: 560, height: 216 },
      zIndex: 13,
      opacity: 1,
    }),
  ],
})

const template = ref(createDefaultTemplate())
const selectedLayerId = ref('main-gameplay-crop')
const sourceInput = ref(SAMPLE_VIDEO_SRC)
const sourceVideoUrl = ref(SAMPLE_VIDEO_SRC)
const selectedFileName = ref('')
const localObjectUrl = ref('')
const previewScale = ref(0.75)
const canvasMode = ref('source')

const selectedLayer = computed(() => (
  template.value.layers.find(layer => layer.id === selectedLayerId.value) || null
))

const generatedTemplate = computed(() => ({
  ...clone(template.value),
  sources: template.value.sources.map(source => ({ ...source })),
  layers: template.value.layers
    .map(normalizeLayer)
    .sort((a, b) => Number(a.zIndex || 0) - Number(b.zIndex || 0)),
}))

const outputWidth = computed(() => Number(template.value.output.width || 1080))
const outputHeight = computed(() => Number(template.value.output.height || 1920))
const sourceWidth = computed(() => Number(template.value.sources.find(source => source.id === 'main-video')?.width || 1920))
const sourceHeight = computed(() => Number(template.value.sources.find(source => source.id === 'main-video')?.height || 1080))
const sourceSize = computed(() => ({ width: sourceWidth.value, height: sourceHeight.value }))

function normalizeNumber(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function normalizeRect(rect, fallback) {
  return {
    x: Math.round(normalizeNumber(rect?.x, fallback.x)),
    y: Math.round(normalizeNumber(rect?.y, fallback.y)),
    width: Math.round(normalizeNumber(rect?.width, fallback.width)),
    height: Math.round(normalizeNumber(rect?.height, fallback.height)),
  }
}

function normalizeLayer(layer) {
  return {
    id: String(layer.id || 'layer'),
    name: String(layer.name || layer.id || 'Layer'),
    type: 'videoCrop',
    sourceId: layer.sourceId || 'main-video',
    sourceRect: normalizeRect(layer.sourceRect, { x: 0, y: 0, width: 1920, height: 1080 }),
    destinationRect: normalizeRect(layer.destinationRect, { x: 0, y: 0, width: 1080, height: 1920 }),
    zIndex: Math.round(normalizeNumber(layer.zIndex, 0)),
    opacity: Math.max(0, Math.min(1, normalizeNumber(layer.opacity, 1))),
    visible: layer.visible !== false,
  }
}

function updateSourceInTemplate(src) {
  template.value.sources = template.value.sources.map(source => (
    source.id === 'main-video' ? { ...source, src } : source
  ))
}

function revokeLocalObjectUrl() {
  if (localObjectUrl.value) {
    URL.revokeObjectURL(localObjectUrl.value)
    localObjectUrl.value = ''
  }
}

function applySourceUrl() {
  revokeLocalObjectUrl()
  selectedFileName.value = ''
  const nextSource = sourceInput.value.trim() || SAMPLE_VIDEO_SRC
  sourceInput.value = nextSource
  sourceVideoUrl.value = nextSource
  updateSourceInTemplate(nextSource)
}

function handleVideoFile(event) {
  const file = event.target.files?.[0]
  if (file) loadLocalVideo(file)
}

function handleVideoDrop(event) {
  const file = Array.from(event.dataTransfer?.files || []).find(item => item.type.startsWith('video/'))
  if (file) loadLocalVideo(file)
}

function loadLocalVideo(file) {
  revokeLocalObjectUrl()
  localObjectUrl.value = URL.createObjectURL(file)
  sourceVideoUrl.value = localObjectUrl.value
  selectedFileName.value = file.name
  sourceInput.value = file.name
  updateSourceInTemplate(file.name)
}

function selectLayer(layerId) {
  selectedLayerId.value = layerId
}

function nextLayerZIndex() {
  return Math.max(0, ...template.value.layers.map(layer => Number(layer.zIndex || 0))) + 1
}

function addLayer() {
  const index = template.value.layers.length + 1
  const id = `crop-layer-${index}`
  template.value.layers.push(createLayer({
    id,
    name: `Crop Layer ${index}`,
    sourceRect: { x: 640, y: 220, width: 640, height: 360 },
    destinationRect: { x: 270, y: 760, width: 540, height: 304 },
    zIndex: nextLayerZIndex(),
    opacity: 1,
  }))
  selectedLayerId.value = id
}

function duplicateLayer(layerId) {
  const sourceLayer = template.value.layers.find(layer => layer.id === layerId)
  if (!sourceLayer) return
  const copy = clone(sourceLayer)
  const suffix = template.value.layers.length + 1
  copy.id = `${sourceLayer.id}-copy-${suffix}`
  copy.name = `${sourceLayer.name} Copy`
  copy.zIndex = nextLayerZIndex()
  copy.sourceRect.x = Math.max(0, Math.min(sourceWidth.value - copy.sourceRect.width, copy.sourceRect.x + 24))
  copy.sourceRect.y = Math.max(0, Math.min(sourceHeight.value - copy.sourceRect.height, copy.sourceRect.y + 24))
  copy.destinationRect.x = Math.max(0, Math.min(outputWidth.value - copy.destinationRect.width, copy.destinationRect.x + 36))
  copy.destinationRect.y = Math.max(0, Math.min(outputHeight.value - copy.destinationRect.height, copy.destinationRect.y + 36))
  template.value.layers.push(copy)
  selectedLayerId.value = copy.id
}

function deleteLayer(layerId) {
  const index = template.value.layers.findIndex(layer => layer.id === layerId)
  if (index === -1) return
  template.value.layers.splice(index, 1)
  if (selectedLayerId.value === layerId) {
    selectedLayerId.value = template.value.layers[index]?.id || template.value.layers[index - 1]?.id || ''
  }
}

function toggleLayerVisibility(layerId) {
  const layer = template.value.layers.find(item => item.id === layerId)
  if (layer) layer.visible = layer.visible === false
}

function moveLayer(layerId, direction) {
  const sorted = [...template.value.layers].sort((a, b) => Number(a.zIndex || 0) - Number(b.zIndex || 0))
  const index = sorted.findIndex(layer => layer.id === layerId)
  const targetIndex = direction === 'up' ? index + 1 : index - 1
  if (index < 0 || targetIndex < 0 || targetIndex >= sorted.length) return

  const currentZ = sorted[index].zIndex
  sorted[index].zIndex = sorted[targetIndex].zIndex
  sorted[targetIndex].zIndex = currentZ
}

function updateLayer(layerId, patch) {
  const index = template.value.layers.findIndex(layer => layer.id === layerId)
  if (index === -1) return

  const current = template.value.layers[index]
  const next = {
    ...current,
    ...patch,
    sourceRect: {
      ...current.sourceRect,
      ...(patch.sourceRect || {}),
    },
    destinationRect: {
      ...current.destinationRect,
      ...(patch.destinationRect || {}),
    },
  }

  template.value.layers[index] = normalizeLayer(next)
  if (patch.id && selectedLayerId.value === layerId) {
    selectedLayerId.value = template.value.layers[index].id
  }
}

function updateLayerDestination(layerId, destinationRect) {
  updateLayer(layerId, { destinationRect })
}

function updateLayerSource(layerId, sourceRect) {
  updateLayer(layerId, { sourceRect })
}

function updateSourceSize({ width, height }) {
  const nextWidth = Math.max(1, Math.round(Number(width) || 1920))
  const nextHeight = Math.max(1, Math.round(Number(height) || 1080))
  const previousWidth = sourceWidth.value
  const previousHeight = sourceHeight.value

  if (previousWidth !== nextWidth || previousHeight !== nextHeight) {
    const scaleX = nextWidth / Math.max(1, previousWidth)
    const scaleY = nextHeight / Math.max(1, previousHeight)

    template.value.layers = template.value.layers.map(layer => {
      const width = Math.min(nextWidth, Math.max(1, Math.round((layer.sourceRect?.width || nextWidth) * scaleX)))
      const height = Math.min(nextHeight, Math.max(1, Math.round((layer.sourceRect?.height || nextHeight) * scaleY)))
      return {
        ...layer,
        sourceRect: {
          x: Math.max(0, Math.min(nextWidth - width, Math.round((layer.sourceRect?.x || 0) * scaleX))),
          y: Math.max(0, Math.min(nextHeight - height, Math.round((layer.sourceRect?.y || 0) * scaleY))),
          width,
          height,
        },
      }
    })
  }

  template.value.sources = template.value.sources.map(source => (
    source.id === 'main-video'
      ? { ...source, width: nextWidth, height: nextHeight }
      : source
  ))
}

function resetTemplate() {
  template.value = createDefaultTemplate()
  selectedLayerId.value = 'main-gameplay-crop'
  sourceInput.value = SAMPLE_VIDEO_SRC
  sourceVideoUrl.value = SAMPLE_VIDEO_SRC
  selectedFileName.value = ''
  canvasMode.value = 'source'
  revokeLocalObjectUrl()
}

onBeforeUnmount(() => {
  revokeLocalObjectUrl()
})
</script>

<style scoped>
.template-builder-shell {
  min-height: 100vh;
  overflow: hidden;
  color: #f4f4f5;
  background:
    linear-gradient(rgba(255, 255, 255, 0.028) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.024) 1px, transparent 1px),
    radial-gradient(circle at 50% 0%, rgba(124, 58, 237, 0.14), transparent 36%),
    linear-gradient(180deg, #09090b 0%, #050505 100%);
  background-size: 38px 38px, 38px 38px, auto, auto;
  font-family: Geist, Inter, ui-sans-serif, system-ui, sans-serif;
  letter-spacing: 0;
}

.builder-topbar {
  height: 72px;
  display: grid;
  grid-template-columns: 300px minmax(360px, 1fr) 300px;
  align-items: center;
  gap: 16px;
  padding: 0 18px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(10, 10, 10, 0.74);
  backdrop-filter: blur(28px);
  box-shadow: 0 20px 70px rgba(0, 0, 0, 0.38);
}

.brand-stack,
.brand-link,
.topbar-actions,
.template-meta {
  display: flex;
  align-items: center;
}

.brand-link {
  gap: 10px;
  color: inherit;
  text-decoration: none;
}

.brand-link span:last-child {
  display: grid;
  gap: 1px;
}

.brand-link strong {
  font-size: 14px;
  font-weight: 750;
}

.brand-link small {
  color: #8a8f98;
  font-size: 11px;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 8px;
  color: #001317;
  background: #67e8f9;
  box-shadow: 0 0 28px rgba(34, 211, 238, 0.28);
  font-weight: 900;
}

.template-meta {
  justify-self: center;
  width: min(620px, 100%);
  gap: 10px;
}

.template-meta label,
.source-field {
  min-width: 0;
  display: grid;
  gap: 5px;
}

.template-meta label:first-child {
  flex: 1.1;
}

.template-meta label:last-child {
  flex: 1;
}

.template-meta span,
.source-field span {
  color: #71717a;
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}

input,
select {
  min-width: 0;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.055);
  color: #f4f4f5;
  font: inherit;
  font-size: 12px;
  padding: 9px 10px;
}

input:focus,
select:focus {
  outline: none;
  border-color: rgba(103, 232, 249, 0.5);
  box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.12);
}

.topbar-actions {
  justify-self: end;
  gap: 10px;
}

.primary-button,
.ghost-button {
  border: 0;
  border-radius: 8px;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 800;
  padding: 10px 13px;
}

.primary-button {
  color: #031214;
  background: #67e8f9;
  box-shadow: 0 0 24px rgba(34, 211, 238, 0.24);
}

.ghost-button {
  color: #d4d4d8;
  background: rgba(255, 255, 255, 0.08);
}

.builder-layout {
  height: calc(100vh - 72px);
  min-height: 0;
  display: grid;
  grid-template-columns: 300px minmax(420px, 1fr) 390px;
  gap: 16px;
  padding: 16px;
}

.stage-column {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 16px;
}

.glass-panel {
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.075), rgba(255, 255, 255, 0.035));
  backdrop-filter: blur(30px);
  box-shadow: 0 20px 70px rgba(0, 0, 0, 0.48);
}

.source-toolbar {
  display: grid;
  grid-template-columns: 180px minmax(220px, 1fr) auto 90px;
  align-items: end;
  gap: 10px;
  padding: 12px;
}

.file-drop {
  position: relative;
  display: grid;
  place-items: center;
  min-height: 50px;
  overflow: hidden;
  border: 1px dashed rgba(103, 232, 249, 0.34);
  border-radius: 8px;
  background: rgba(34, 211, 238, 0.055);
  color: #dffbff;
  cursor: pointer;
  font-size: 12px;
  font-weight: 750;
  text-align: center;
}

.file-drop input {
  display: none;
}

.file-drop span {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-field.compact {
  width: 90px;
}

.mode-switch {
  display: inline-flex;
  gap: 5px;
  align-self: end;
  padding: 5px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.24);
}

.mode-switch button {
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: #9ca3af;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 800;
  padding: 9px 11px;
  white-space: nowrap;
}

.mode-switch button.active {
  color: #031214;
  background: #67e8f9;
  box-shadow: 0 0 20px rgba(34, 211, 238, 0.18);
}

.right-stack {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(320px, 0.95fr) minmax(260px, 1.05fr);
  gap: 16px;
}

@media (max-width: 1220px) {
  .builder-topbar {
    grid-template-columns: 1fr auto;
    height: auto;
    min-height: 72px;
    padding: 12px 16px;
  }

  .template-meta {
    grid-column: 1 / -1;
    justify-self: stretch;
    order: 3;
  }

  .builder-layout {
    grid-template-columns: 280px minmax(420px, 1fr);
  }

  .right-stack {
    grid-column: 1 / -1;
    grid-template-columns: 1fr 1fr;
    grid-template-rows: minmax(320px, 1fr);
  }
}

@media (max-width: 860px) {
  .template-builder-shell {
    overflow: auto;
  }

  .builder-topbar,
  .builder-layout,
  .source-toolbar,
  .right-stack {
    display: block;
    height: auto;
  }

  .builder-topbar {
    padding: 14px;
  }

  .topbar-actions,
  .template-meta {
    margin-top: 12px;
    flex-wrap: wrap;
  }

  .builder-layout {
    padding: 12px;
  }

  .source-toolbar,
  .stage-column,
  .right-stack {
    margin-top: 12px;
  }

  .source-field,
  .source-field.compact {
    width: 100%;
    margin-top: 10px;
  }
}
</style>
