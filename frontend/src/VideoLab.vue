<!-- Node-based editing workspace for Alcut Studio. Designed as a DrewUI/Linear-style graph canvas. -->
<template>
  <div class="node-studio-shell">
    <header class="node-topbar">
      <div class="brand-stack">
        <a href="#/" class="brand-link" aria-label="Back to home">
          <span class="brand-mark">A</span>
          <span>
            <strong>Alcut Studio</strong>
            <small>Node Video Graph</small>
          </span>
        </a>
        <input v-model="projectName" class="project-input" spellcheck="false" />
      </div>

      <div class="graph-toolbar" aria-label="Editor tools">
        <button class="tool-chip active">Select</button>
        <button class="tool-chip">Connect</button>
        <button class="tool-chip">Comment</button>
        <span class="toolbar-divider"></span>
        <button class="icon-control" @click="zoom = Math.max(70, zoom - 10)">−</button>
        <span class="zoom-readout">{{ zoom }}%</span>
        <button class="icon-control" @click="zoom = Math.min(140, zoom + 10)">+</button>
      </div>

      <div class="topbar-actions">
        <span class="job-status" :class="store.status">{{ statusLabel }}</span>
        <button class="export-button" :disabled="store.isProcessing || !canExport" @click="store.exportProject">
          Export
        </button>
      </div>
    </header>

    <main class="node-layout">
      <aside class="asset-panel glass-panel">
        <div class="panel-section-title">
          <span>Input</span>
          <small>Media source</small>
        </div>

        <label
          class="upload-zone"
          :class="{ 'has-file': Boolean(store.selectedFile) }"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="handleDrop"
        >
          <input type="file" accept="video/*" @change="handleFileInput" />
          <span class="upload-orb"></span>
          <strong>{{ store.selectedFile?.name || 'Drop a video file' }}</strong>
          <small>{{ store.selectedFile ? 'Ready for analysis' : 'or click to browse local files' }}</small>
        </label>

        <div class="node-palette">
          <div class="panel-section-title compact">
            <span>Node Palette</span>
            <small>Building blocks</small>
          </div>

          <button v-for="node in paletteNodes" :key="node.label" class="palette-card" @click="highlightNode(node.target)">
            <span class="palette-icon" :class="node.accent"></span>
            <span>
              <strong>{{ node.label }}</strong>
              <small>{{ node.copy }}</small>
            </span>
          </button>
        </div>

        <button class="analysis-button" :disabled="!store.selectedFile || store.isProcessing" @click="store.detectKeyMoments">
          {{ store.isProcessing ? 'Analyzing…' : 'Run AI Moment Graph' }}
        </button>
      </aside>

      <section
        class="graph-canvas-wrap"
        :class="{ 'is-panning': dragState?.type === 'canvas' }"
        :style="canvasBackgroundStyle"
        @pointerdown="startCanvasPan"
        @wheel.prevent="handleCanvasWheel"
      >
        <div class="canvas-glow cyan"></div>
        <div class="canvas-glow violet"></div>

        <div class="graph-canvas" :style="canvasTransformStyle">
          <svg class="connection-layer" viewBox="0 0 1200 720" preserveAspectRatio="none" aria-hidden="true">
            <path v-for="edge in graphEdges" :key="edge.id" class="edge-path" :class="edge.active ? 'active' : ''" :d="edge.d" />
          </svg>

          <article
            v-for="node in graphNodes"
            :key="node.id"
            class="graph-node"
            :class="[node.kind, { selected: selectedNodeId === node.id, dragging: dragState?.type === 'node' && dragState.nodeId === node.id }]"
            :style="{ left: `${node.x}px`, top: `${node.y}px`, width: `${node.width}px` }"
            @pointerdown.stop="startNodeDrag($event, node.id)"
            @click="selectedNodeId = node.id"
          >
            <div class="node-head">
              <span class="node-port input"></span>
              <div>
                <small>{{ node.kicker }}</small>
                <strong>{{ node.title }}</strong>
              </div>
              <span class="node-port output"></span>
            </div>

            <div class="node-body">
              <p>{{ node.description }}</p>

              <div v-if="node.id === 'source'" class="video-preview-card">
                <video v-if="store.sourceVideoUrl" :src="store.sourceVideoUrl" muted controls></video>
                <div v-else class="preview-placeholder">Import video</div>
              </div>

              <div v-if="node.id === 'analysis'" class="signal-stack">
                <span v-for="metric in signalMetrics" :key="metric.label">
                  <i :style="{ width: `${metric.value}%` }"></i>
                  <em>{{ metric.label }}</em>
                </span>
              </div>

              <div v-if="node.id === 'clips'" class="clip-node-list">
                <button
                  v-for="clip in visibleClips"
                  :key="clip.id"
                  :class="{ active: clip.id === store.selectedClipId }"
                  @click.stop="selectClip(clip.id)"
                >
                  <span>{{ formatTime(clip.start) }} → {{ formatTime(clip.end) }}</span>
                  <strong>{{ clip.score.toFixed(1) }}</strong>
                </button>
                <div v-if="!visibleClips.length" class="empty-node-copy">Run analysis to generate clip nodes.</div>
              </div>

              <div v-if="node.id === 'export'" class="export-node-body">
                <div class="export-stat">
                  <strong>{{ store.moments.length }}</strong>
                  <span>clips queued</span>
                </div>
                <a v-if="store.exportUrl" class="download-link" :href="store.exportUrl" target="_blank" rel="noreferrer">Open export</a>
                <button v-else class="node-action" :disabled="!canExport || store.isProcessing" @click.stop="store.exportProject">Render timeline</button>
              </div>
            </div>
          </article>
        </div>
      </section>

      <aside class="properties-panel glass-panel">
        <div class="panel-section-title">
          <span>Inspector</span>
          <small>{{ selectedNode?.title || 'No node selected' }}</small>
        </div>

        <section class="inspector-card">
          <label>
            <span>Whisper device</span>
            <select v-model="store.whisperDevice">
              <option value="cpu">CPU</option>
              <option value="gpu" :disabled="!store.gpuAvailable">GPU</option>
            </select>
          </label>
          <label class="switch-row">
            <span>Smart chunking</span>
            <input type="checkbox" v-model="store.smartChunking" />
          </label>
        </section>

        <section v-if="selectedClip" class="inspector-card clip-inspector">
          <div class="clip-inspector-head">
            <strong>Selected Clip</strong>
            <span>{{ selectedClip.score.toFixed(1) }}</span>
          </div>
          <p>{{ selectedClip.reason }}</p>
          <div class="trim-fields">
            <label>
              <span>Start</span>
              <input type="number" step="0.1" :value="selectedClip.start" @input="updateClip('start', $event.target.value)" />
            </label>
            <label>
              <span>End</span>
              <input type="number" step="0.1" :value="selectedClip.end" @input="updateClip('end', $event.target.value)" />
            </label>
          </div>
        </section>

        <section class="inspector-card progress-card">
          <div class="progress-topline">
            <strong>Pipeline</strong>
            <span>{{ Math.round(store.progress) }}%</span>
          </div>
          <div class="progress-track"><i :style="{ width: `${store.progress}%` }"></i></div>
          <p>{{ store.statusMessage || 'Import a video, run detection, then export selected moments.' }}</p>
        </section>
      </aside>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useEditorStore } from './stores/editorStore'

const store = useEditorStore()
const MIN_ZOOM = 70
const MAX_ZOOM = 140
const projectName = ref('Untitled highlight graph')
const zoom = ref(100)
const selectedNodeId = ref('source')
const isDragging = ref(false)
const canvasPan = reactive({ x: 0, y: 0 })
const dragState = ref(null)

const nodePositions = reactive({
  source: { x: 70, y: 120 },
  analysis: { x: 470, y: 70 },
  clips: { x: 500, y: 380 },
  export: { x: 930, y: 230 },
})

const paletteNodes = [
  { label: 'Source', copy: 'Raw media input', accent: 'cyan', target: 'source' },
  { label: 'Analyze', copy: 'Whisper + signal pass', accent: 'violet', target: 'analysis' },
  { label: 'Clip Stack', copy: 'Detected highlights', accent: 'teal', target: 'clips' },
  { label: 'Export', copy: 'Render edit list', accent: 'amber', target: 'export' },
]

const graphNodes = computed(() => [
  {
    id: 'source',
    kind: 'source-node',
    kicker: 'INPUT',
    title: 'Source Video',
    description: store.selectedFile ? store.selectedFile.name : 'Attach the raw clip that feeds the editing graph.',
    ...nodePositions.source,
    width: 300,
  },
  {
    id: 'analysis',
    kind: 'analysis-node',
    kicker: 'AI PASS',
    title: 'Moment Detector',
    description: 'Scores transcript density, audio peaks, pitch spikes, and scene changes.',
    ...nodePositions.analysis,
    width: 330,
  },
  {
    id: 'clips',
    kind: 'clips-node',
    kicker: 'EDIT DECISIONS',
    title: 'Clip Stack',
    description: `${store.moments.length} detected clips are available for review and trim edits.`,
    ...nodePositions.clips,
    width: 360,
  },
  {
    id: 'export',
    kind: 'export-node',
    kicker: 'OUTPUT',
    title: 'Export Renderer',
    description: 'Sends the current edit decision list to the backend render pipeline.',
    ...nodePositions.export,
    width: 290,
  },
])

const getGraphNode = id => graphNodes.value.find(node => node.id === id)

const nodeAnchor = (node, side) => ({
  x: node.x + (side === 'right' ? node.width : 0),
  y: node.y + 96,
})

const edgePath = (fromId, toId) => {
  const from = getGraphNode(fromId)
  const to = getGraphNode(toId)
  if (!from || !to) return ''
  const start = nodeAnchor(from, 'right')
  const end = nodeAnchor(to, 'left')
  const tension = Math.max(80, Math.abs(end.x - start.x) * 0.45)
  return `M ${start.x} ${start.y} C ${start.x + tension} ${start.y}, ${end.x - tension} ${end.y}, ${end.x} ${end.y}`
}

const graphEdges = computed(() => [
  { id: 'source-analysis', active: Boolean(store.selectedFile), d: edgePath('source', 'analysis') },
  { id: 'analysis-clips', active: store.moments.length > 0, d: edgePath('analysis', 'clips') },
  { id: 'clips-export', active: store.moments.length > 0, d: edgePath('clips', 'export') },
])

const signalMetrics = computed(() => [
  { label: 'Audio peaks', value: Math.min(100, store.audioPeaks.length * 16) || 14 },
  { label: 'Scene cuts', value: Math.min(100, store.sceneChanges.length * 12) || 22 },
  { label: 'Speech rate', value: Math.min(100, store.speechRateSpikes.length * 18) || 31 },
])

const visibleClips = computed(() => store.moments.slice(0, 5))
const selectedNode = computed(() => graphNodes.value.find(node => node.id === selectedNodeId.value))
const selectedClip = computed(() => store.selectedClip)
const canExport = computed(() => Boolean(store.videoId && store.moments.length))
const statusLabel = computed(() => store.statusMessage || (store.selectedFile ? 'Media loaded' : 'Ready'))
const zoomScale = computed(() => zoom.value / 100)
const canvasTransformStyle = computed(() => ({
  transform: `translate(${canvasPan.x}px, ${canvasPan.y}px) scale(${zoomScale.value})`,
}))
const canvasBackgroundStyle = computed(() => ({
  backgroundPosition: `${canvasPan.x}px ${canvasPan.y}px, ${canvasPan.x}px ${canvasPan.y}px, center, center`,
}))

const handleFileInput = event => {
  const file = event.target.files?.[0]
  if (file) store.setSelectedFile(file)
}

const handleDrop = event => {
  isDragging.value = false
  const file = Array.from(event.dataTransfer?.files || []).find(item => item.type.startsWith('video/'))
  if (file) store.setSelectedFile(file)
}

const highlightNode = id => {
  selectedNodeId.value = id
}

const selectClip = id => {
  store.selectClip(id)
  selectedNodeId.value = 'clips'
}

const updateClip = (field, value) => {
  if (!selectedClip.value) return
  const nextStart = field === 'start' ? Number(value) : selectedClip.value.start
  const nextEnd = field === 'end' ? Number(value) : selectedClip.value.end
  store.updateClipRange(selectedClip.value.id, nextStart, nextEnd)
}

const formatTime = seconds => {
  const total = Math.max(0, Number(seconds) || 0)
  const minutes = Math.floor(total / 60)
  const wholeSeconds = Math.floor(total % 60)
  return `${minutes}:${String(wholeSeconds).padStart(2, '0')}`
}

const isInteractiveTarget = target => Boolean(target.closest('button, input, select, textarea, a, video, label'))

const clampZoom = value => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(value)))

const zoomAroundPoint = (nextZoom, clientX, clientY, canvasElement) => {
  const previousScale = zoomScale.value
  const nextScale = clampZoom(nextZoom) / 100
  if (previousScale === nextScale) return

  const rect = canvasElement.getBoundingClientRect()
  const pointerX = clientX - rect.left
  const pointerY = clientY - rect.top
  const graphX = (pointerX - canvasPan.x) / previousScale
  const graphY = (pointerY - canvasPan.y) / previousScale

  zoom.value = Math.round(nextScale * 100)
  canvasPan.x = pointerX - graphX * nextScale
  canvasPan.y = pointerY - graphY * nextScale
}

const handleCanvasWheel = event => {
  const direction = event.deltaY > 0 ? -1 : 1
  zoomAroundPoint(zoom.value + direction * 8, event.clientX, event.clientY, event.currentTarget)
}

const startNodeDrag = (event, nodeId) => {
  if (event.button !== 0 || isInteractiveTarget(event.target)) return
  selectedNodeId.value = nodeId
  const nodePosition = nodePositions[nodeId]
  dragState.value = {
    type: 'node',
    nodeId,
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    originX: nodePosition.x,
    originY: nodePosition.y,
  }
  event.currentTarget.setPointerCapture(event.pointerId)
  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', stopDrag)
  window.addEventListener('pointercancel', stopDrag)
}

const startCanvasPan = event => {
  if (event.button !== 0 || event.target.closest('.graph-node') || isInteractiveTarget(event.target)) return
  dragState.value = {
    type: 'canvas',
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    originX: canvasPan.x,
    originY: canvasPan.y,
  }
  event.currentTarget.setPointerCapture(event.pointerId)
  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', stopDrag)
  window.addEventListener('pointercancel', stopDrag)
}

const handlePointerMove = event => {
  const drag = dragState.value
  if (!drag || event.pointerId !== drag.pointerId) return
  const deltaX = event.clientX - drag.startX
  const deltaY = event.clientY - drag.startY

  if (drag.type === 'canvas') {
    canvasPan.x = drag.originX + deltaX
    canvasPan.y = drag.originY + deltaY
    return
  }

  const nodePosition = nodePositions[drag.nodeId]
  nodePosition.x = Math.round(drag.originX + deltaX / zoomScale.value)
  nodePosition.y = Math.round(drag.originY + deltaY / zoomScale.value)
}

const stopDrag = event => {
  const drag = dragState.value
  if (!drag || event.pointerId !== drag.pointerId) return
  dragState.value = null
  window.removeEventListener('pointermove', handlePointerMove)
  window.removeEventListener('pointerup', stopDrag)
  window.removeEventListener('pointercancel', stopDrag)
}

const stopActiveDrag = () => {
  dragState.value = null
  window.removeEventListener('pointermove', handlePointerMove)
  window.removeEventListener('pointerup', stopDrag)
  window.removeEventListener('pointercancel', stopDrag)
}

onMounted(() => {
  store.loadWhisperCapabilities()
})

onBeforeUnmount(stopActiveDrag)
</script>

<style scoped>
.node-studio-shell {
  min-height: 100vh;
  overflow: hidden;
  color: #f4f7fa;
  background:
    radial-gradient(circle at 50% -10%, rgba(34, 211, 238, 0.12), transparent 32%),
    radial-gradient(circle at 90% 10%, rgba(124, 58, 237, 0.12), transparent 28%),
    #050505;
  font-family: Geist, Inter, ui-sans-serif, system-ui, sans-serif;
  letter-spacing: -0.015em;
}

.node-topbar {
  height: 72px;
  display: grid;
  grid-template-columns: 340px 1fr 340px;
  align-items: center;
  gap: 18px;
  padding: 0 18px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(10, 10, 10, 0.72);
  backdrop-filter: blur(28px);
  box-shadow: 0 20px 70px rgba(0, 0, 0, 0.38);
}

.brand-stack,
.brand-link,
.topbar-actions,
.graph-toolbar {
  display: flex;
  align-items: center;
}

.brand-stack { gap: 16px; min-width: 0; }
.brand-link { gap: 10px; color: inherit; text-decoration: none; }
.brand-link span:last-child { display: grid; gap: 1px; }
.brand-link strong { font-size: 14px; font-weight: 700; }
.brand-link small { color: #8a8f98; font-size: 11px; }

.brand-mark {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 12px;
  color: #001317;
  background: linear-gradient(135deg, #67e8f9, #2dd4bf);
  box-shadow: 0 0 28px rgba(34, 211, 238, 0.38);
  font-weight: 900;
}

.project-input {
  min-width: 0;
  width: 150px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  color: #e4e7ec;
  padding: 8px 10px;
  font: inherit;
  font-size: 13px;
}
.project-input:focus { outline: none; border-color: rgba(34, 211, 238, 0.35); background: rgba(255, 255, 255, 0.045); }

.graph-toolbar {
  justify-self: center;
  gap: 7px;
  padding: 7px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.045);
  backdrop-filter: blur(24px);
}

.tool-chip,
.icon-control,
.export-button,
.analysis-button,
.node-action,
.download-link {
  border: 0;
  cursor: pointer;
  font: inherit;
}

.tool-chip,
.icon-control {
  border-radius: 999px;
  background: transparent;
  color: #9ca3af;
  padding: 7px 11px;
  transition: 160ms ease;
}
.tool-chip.active,
.tool-chip:hover,
.icon-control:hover {
  color: #f4f7fa;
  background: rgba(255, 255, 255, 0.08);
}
.toolbar-divider { width: 1px; height: 20px; background: rgba(255, 255, 255, 0.1); }
.zoom-readout { min-width: 46px; color: #a1a1aa; text-align: center; font-size: 12px; }
.topbar-actions { justify-self: end; gap: 12px; min-width: 0; }
.job-status { max-width: 190px; color: #8a8f98; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.job-status.error { color: #fca5a5; }
.job-status.processing { color: #67e8f9; }

.export-button,
.analysis-button,
.node-action,
.download-link {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  border-radius: 13px;
  background: rgba(34, 211, 238, 0.92);
  color: #001317;
  font-weight: 750;
  letter-spacing: -0.025em;
  box-shadow: 0 0 28px rgba(34, 211, 238, 0.28);
  transition: 180ms ease;
}
.export-button { padding: 10px 16px; }
.export-button:hover,
.analysis-button:hover,
.node-action:hover,
.download-link:hover { transform: translateY(-1px); background: #67e8f9; box-shadow: 0 0 46px rgba(34, 211, 238, 0.38); }
.export-button:disabled,
.analysis-button:disabled,
.node-action:disabled { cursor: not-allowed; opacity: 0.45; transform: none; }

.node-layout {
  height: calc(100vh - 72px);
  display: grid;
  grid-template-columns: 292px 1fr 320px;
  gap: 16px;
  padding: 16px;
}

.glass-panel {
  min-height: 0;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 24px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.075), rgba(255, 255, 255, 0.035));
  backdrop-filter: blur(30px);
  box-shadow: 0 20px 70px rgba(0, 0, 0, 0.48);
}
.asset-panel,
.properties-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  overflow: auto;
}

.panel-section-title { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
.panel-section-title span { font-size: 13px; font-weight: 750; color: #f4f7fa; }
.panel-section-title small { color: #71717a; font-size: 11px; }
.panel-section-title.compact { margin-top: 6px; }

.upload-zone {
  position: relative;
  min-height: 158px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 7px;
  overflow: hidden;
  border: 1px dashed rgba(255, 255, 255, 0.14);
  border-radius: 22px;
  background: rgba(0, 0, 0, 0.28);
  cursor: pointer;
  text-align: center;
}
.upload-zone input { display: none; }
.upload-zone strong { max-width: 210px; color: #f4f7fa; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.upload-zone small { color: #8a8f98; font-size: 12px; }
.upload-zone.has-file { border-color: rgba(34, 211, 238, 0.42); box-shadow: inset 0 0 30px rgba(34, 211, 238, 0.06); }
.upload-orb {
  width: 44px;
  height: 44px;
  border-radius: 18px;
  background: radial-gradient(circle, rgba(103, 232, 249, 0.88), rgba(34, 211, 238, 0.18) 60%, transparent);
  box-shadow: 0 0 44px rgba(34, 211, 238, 0.32);
}

.node-palette { display: grid; gap: 9px; }
.palette-card {
  display: flex;
  gap: 11px;
  align-items: center;
  width: 100%;
  padding: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.04);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: 160ms ease;
}
.palette-card:hover { border-color: rgba(34, 211, 238, 0.28); background: rgba(255, 255, 255, 0.065); transform: translateY(-1px); }
.palette-card span:last-child { display: grid; gap: 2px; }
.palette-card strong { font-size: 13px; }
.palette-card small { color: #8a8f98; font-size: 11px; }
.palette-icon { width: 12px; height: 30px; border-radius: 999px; box-shadow: 0 0 24px currentColor; }
.palette-icon.cyan { color: #22d3ee; background: #22d3ee; }
.palette-icon.violet { color: #8b5cf6; background: #8b5cf6; }
.palette-icon.teal { color: #2dd4bf; background: #2dd4bf; }
.palette-icon.amber { color: #fbbf24; background: #fbbf24; }
.analysis-button { width: 100%; margin-top: auto; padding: 12px 14px; }

.graph-canvas-wrap {
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 28px;
  background:
    linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px),
    radial-gradient(circle at center, rgba(34, 211, 238, 0.045), transparent 48%),
    #070707;
  background-size: 36px 36px, 36px 36px, auto, auto;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.04), inset 0 0 70px rgba(0,0,0,0.72);
  cursor: grab;
  touch-action: none;
  user-select: none;
}
.graph-canvas-wrap.is-panning { cursor: grabbing; }
.graph-canvas-wrap.is-panning .graph-canvas { transition: none; }
.canvas-glow { position: absolute; width: 280px; height: 280px; border-radius: 999px; filter: blur(60px); opacity: 0.18; pointer-events: none; }
.canvas-glow.cyan { left: 10%; top: 8%; background: #22d3ee; }
.canvas-glow.violet { right: 8%; bottom: 12%; background: #8b5cf6; }
.graph-canvas {
  position: relative;
  width: 1240px;
  height: 720px;
  transform-origin: top left;
  transition: transform 160ms ease;
}
.connection-layer { position: absolute; inset: 0; width: 1240px; height: 720px; pointer-events: none; }
.edge-path { fill: none; stroke: rgba(255, 255, 255, 0.16); stroke-width: 2; stroke-dasharray: 7 8; }
.edge-path.active { stroke: rgba(34, 211, 238, 0.76); filter: drop-shadow(0 0 10px rgba(34, 211, 238, 0.42)); stroke-dasharray: none; }

.graph-node {
  position: absolute;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 22px;
  background: rgba(14, 14, 15, 0.82);
  backdrop-filter: blur(28px);
  box-shadow: 0 24px 80px rgba(0,0,0,0.55);
  cursor: grab;
  touch-action: none;
  transition: border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease;
}
.graph-node:active { cursor: grabbing; }
.graph-node:hover,
.graph-node.selected { border-color: rgba(34, 211, 238, 0.52); box-shadow: 0 24px 80px rgba(0,0,0,0.55), 0 0 34px rgba(34, 211, 238, 0.22); transform: translateY(-2px); }
.graph-node.dragging,
.graph-node.dragging:hover {
  z-index: 3;
  cursor: grabbing;
  transform: none;
  transition: none;
}
.node-head {
  position: relative;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  padding: 14px 15px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: linear-gradient(180deg, rgba(255,255,255,0.07), rgba(255,255,255,0.025));
}
.node-head div { display: grid; gap: 2px; }
.node-head small { color: #67e8f9; font-size: 10px; font-weight: 800; letter-spacing: 0.12em; }
.node-head strong { font-size: 15px; }
.node-port { width: 12px; height: 12px; border: 2px solid #050505; border-radius: 999px; background: #22d3ee; box-shadow: 0 0 16px rgba(34, 211, 238, 0.65); }
.node-port.input { margin-left: -21px; }
.node-port.output { margin-right: -21px; }
.node-body { padding: 14px 15px 16px; }
.node-body p { margin: 0 0 12px; color: #a1a1aa; font-size: 12px; line-height: 1.5; }

.video-preview-card {
  overflow: hidden;
  height: 145px;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 16px;
  background: #050505;
}
.video-preview-card video { width: 100%; height: 100%; object-fit: cover; }
.preview-placeholder { height: 100%; display: grid; place-items: center; color: #71717a; font-size: 12px; background: radial-gradient(circle, rgba(34,211,238,0.08), transparent 55%); }

.signal-stack { display: grid; gap: 8px; }
.signal-stack span { position: relative; height: 28px; overflow: hidden; border-radius: 999px; background: rgba(255,255,255,0.055); }
.signal-stack i { position: absolute; inset: 0 auto 0 0; border-radius: inherit; background: linear-gradient(90deg, rgba(34,211,238,0.38), rgba(45,212,191,0.82)); box-shadow: 0 0 18px rgba(34,211,238,0.3); }
.signal-stack em { position: relative; z-index: 1; display: flex; align-items: center; height: 100%; padding-left: 11px; color: #e4e7ec; font-size: 11px; font-style: normal; }

.clip-node-list { display: grid; gap: 7px; }
.clip-node-list button {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 13px;
  background: rgba(255,255,255,0.045);
  color: #e4e7ec;
  padding: 10px 11px;
  font: inherit;
  cursor: pointer;
}
.clip-node-list button.active { border-color: rgba(34,211,238,0.66); background: rgba(34,211,238,0.12); box-shadow: 0 0 24px rgba(34,211,238,0.22); }
.clip-node-list span { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 11px; }
.clip-node-list strong { color: #67e8f9; font-size: 12px; }
.empty-node-copy { color: #71717a; font-size: 12px; }

.export-node-body { display: grid; gap: 12px; }
.export-stat { display: flex; align-items: baseline; gap: 8px; }
.export-stat strong { font-size: 36px; line-height: 1; color: #67e8f9; text-shadow: 0 0 22px rgba(34,211,238,0.4); }
.export-stat span { color: #8a8f98; font-size: 12px; }
.node-action,
.download-link { padding: 10px 13px; text-decoration: none; }

.inspector-card {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  background: rgba(0, 0, 0, 0.22);
}
.inspector-card label { display: grid; gap: 7px; color: #8a8f98; font-size: 12px; }
.inspector-card select,
.inspector-card input[type='number'] {
  width: 100%;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 12px;
  background: rgba(255,255,255,0.055);
  color: #f4f7fa;
  padding: 10px;
}
.switch-row { grid-template-columns: 1fr auto; align-items: center; }
.switch-row input { accent-color: #22d3ee; }
.clip-inspector-head,
.progress-topline { display: flex; justify-content: space-between; align-items: center; }
.clip-inspector-head span { color: #001317; background: #67e8f9; border-radius: 999px; padding: 3px 8px; font-size: 11px; font-weight: 800; }
.clip-inspector p,
.progress-card p { margin: 0; color: #a1a1aa; font-size: 12px; line-height: 1.5; }
.trim-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.progress-track { height: 8px; overflow: hidden; border-radius: 999px; background: rgba(255,255,255,0.075); }
.progress-track i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, #22d3ee, #2dd4bf); box-shadow: 0 0 20px rgba(34,211,238,0.34); }

@media (max-width: 1100px) {
  .node-topbar { grid-template-columns: 1fr auto; height: auto; min-height: 72px; }
  .graph-toolbar { display: none; }
  .node-layout { grid-template-columns: 260px 1fr; }
  .properties-panel { display: none; }
}
</style>
