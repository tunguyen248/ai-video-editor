<template>
  <div class="studio">
    <main class="workspace">
      <header class="toolbar">
        <label class="file-picker" :class="{ disabled: store.isProcessing }">
          <input type="file" accept="video/*" :disabled="store.isProcessing" @change="handleFileChange" />
          <span>{{ store.selectedFile ? store.selectedFile.name : 'Choose video' }}</span>
        </label>

        <div class="toolbar-controls">
          <div class="segmented">
            <button :class="{ active: store.whisperDevice === 'cpu' }" :disabled="store.isProcessing" @click="store.whisperDevice = 'cpu'">CPU</button>
            <button :class="{ active: store.whisperDevice === 'gpu' }" :disabled="store.isProcessing || !store.gpuAvailable" @click="store.whisperDevice = 'gpu'">GPU</button>
          </div>
          <label class="toggle">
            <input type="checkbox" v-model="store.smartChunking" :disabled="store.isProcessing" />
            <span></span>
          </label>
          <button class="tool-btn primary" :disabled="!store.selectedFile || store.isProcessing" @click="store.detectKeyMoments">Detect Moments</button>
          <button class="tool-btn accent" :disabled="!store.videoId || !store.moments.length || store.isProcessing" @click="store.exportProject">Export</button>
        </div>
      </header>

      <section class="status-strip" v-if="store.status !== 'idle'">
        <div>
          <span class="status" :class="store.status">{{ statusLabel }}</span>
          <strong>{{ store.statusMessage }}</strong>
        </div>
        <div class="progress">
          <span :style="{ width: `${store.progress}%` }"></span>
        </div>
      </section>

      <section class="editor-shell">
        <div class="stage">
          <VideoPlayer ref="playerRef" :source="store.sourceVideoUrl" :type="store.sourceMimeType" />
          <DualRangeSlider
            :clip="store.selectedClip"
            :duration="store.durationEstimate"
            @change="handleRangeChange"
            @scrub="scrubTo"
          />
          <div class="empty-state" v-if="!store.sourceVideoUrl">
            <strong>No video loaded</strong>
          </div>
        </div>

        <ClipTimeline
          :clips="store.moments"
          :selected-id="store.selectedClipId"
          @select="selectClip"
        />
      </section>

      <section class="export-result" v-if="store.exportUrl">
        <div>
          <span class="eyebrow">Final Export</span>
          <strong>{{ exportFileName }}</strong>
        </div>
        <button class="tool-btn" @click="playExport">Play Export</button>
        <a class="tool-btn link" :href="store.exportUrl" target="_blank">Open File</a>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import ClipTimeline from './components/ClipTimeline.vue'
import DualRangeSlider from './components/DualRangeSlider.vue'
import VideoPlayer from './components/VideoPlayer.vue'
import { useEditorStore } from './stores/editorStore'

const store = useEditorStore()
const playerRef = ref(null)

const statusLabel = computed(() => ({
  processing: store.activeJobType === 'export_project' ? 'Exporting' : 'Processing',
  complete: 'Complete',
  error: 'Error',
}[store.status] || 'Ready'))

const exportFileName = computed(() => store.exportUrl.split('/').pop() || 'project_export.mp4')

const handleFileChange = event => {
  store.setSelectedFile(event.target.files?.[0] || null)
}

const selectClip = clip => {
  store.selectClip(clip.id)
  playerRef.value?.playFrom(clip.start)
}

const handleRangeChange = ({ id, start, end }) => {
  store.updateClipRange(id, start, end)
}

const scrubTo = time => {
  playerRef.value?.seekTo(time)
}

const playExport = () => {
  store.sourceVideoUrl = store.exportUrl
  store.sourceMimeType = 'video/mp4'
  playerRef.value?.playFrom(0)
}

onMounted(store.loadWhisperCapabilities)
</script>

<style scoped>
:global(*) {
  box-sizing: border-box;
}

:global(body) {
  margin: 0;
  background: #f4f1ea;
  color: #161616;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.studio {
  height: 100vh;
  padding-top: 56px;
  overflow: hidden;
}

.workspace {
  height: calc(100vh - 56px);
  min-height: 0;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  padding: 14px 18px;
  background: #fff;
  border-bottom: 1px solid #dfdbd2;
}

.file-picker {
  min-width: 220px;
  max-width: 420px;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border: 1px solid #d8d3c9;
  border-radius: 8px;
  background: #faf9f5;
  cursor: pointer;
}

.file-picker input {
  display: none;
}

.file-picker span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 700;
}

.file-picker.disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.toolbar-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.segmented {
  display: inline-grid;
  grid-template-columns: repeat(2, 44px);
  border: 1px solid #d8d3c9;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}

.segmented button,
.tool-btn {
  border: 0;
  font: inherit;
  cursor: pointer;
}

.segmented button {
  padding: 8px 0;
  background: transparent;
  color: #777167;
  font-size: 12px;
  font-weight: 800;
}

.segmented button.active {
  background: #161616;
  color: #fff;
}

.segmented button:disabled,
.tool-btn:disabled {
  opacity: 0.38;
  cursor: not-allowed;
}

.toggle {
  display: inline-flex;
  align-items: center;
  padding: 5px;
}

.toggle input {
  display: none;
}

.toggle span {
  width: 34px;
  height: 20px;
  position: relative;
  border-radius: 999px;
  background: #d8d3c9;
}

.toggle span::after {
  content: '';
  position: absolute;
  width: 16px;
  height: 16px;
  left: 2px;
  top: 2px;
  border-radius: 50%;
  background: #fff;
  transition: transform 160ms ease;
}

.toggle input:checked + span {
  background: #34746b;
}

.toggle input:checked + span::after {
  transform: translateX(14px);
}

.tool-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 36px;
  padding: 8px 13px;
  border-radius: 8px;
  border: 1px solid #d8d3c9;
  background: #fff;
  color: #161616;
  text-decoration: none;
  font-size: 13px;
  font-weight: 800;
}

.tool-btn.primary {
  background: #161616;
  border-color: #161616;
  color: #fff;
}

.tool-btn.accent {
  background: #e8ff47;
  border-color: #c8df24;
}

.tool-btn.link {
  background: #faf9f5;
}

.status-strip {
  display: grid;
  gap: 10px;
  padding: 12px 18px;
  background: #fff8e2;
  border-bottom: 1px solid #eadca9;
}

.status-strip > div:first-child {
  display: flex;
  gap: 10px;
  align-items: center;
}

.status {
  padding: 3px 8px;
  border-radius: 999px;
  background: #161616;
  color: #fff;
  font-size: 11px;
  font-weight: 800;
}

.status.complete {
  background: #34746b;
}

.status.error {
  background: #b3261e;
}

.progress {
  height: 5px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(22, 22, 22, 0.12);
}

.progress span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #161616;
  transition: width 240ms ease;
}

.editor-shell {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  background: #202020;
  overflow: hidden;
}

.stage {
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  height: 100%;
  min-height: 0;
  position: relative;
  min-width: 0;
  background: #f4f1ea;
  overflow: hidden;
}

.empty-state {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  min-height: 320px;
  color: #fff;
  background: #202020;
}

.export-result {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 18px;
  border-top: 1px solid #dfdbd2;
  background: #fff;
}

.export-result div {
  margin-right: auto;
  display: grid;
  gap: 2px;
}

.eyebrow {
  color: #8b867c;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 800;
}

@media (max-width: 980px) {
  .toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .toolbar-controls {
    justify-content: flex-start;
  }

  .editor-shell {
    grid-template-columns: 1fr;
  }
}
</style>
