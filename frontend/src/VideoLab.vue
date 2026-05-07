<!-- Template-first workspace for Alcut Studio, with the DrewUI-style graph shell kept as the product frame. -->
<template>
  <div class="node-studio-shell">
    <header class="node-topbar">
      <div class="brand-stack">
        <a href="#/" class="brand-link" aria-label="Back to home">
          <span class="brand-mark">A</span>
          <span>
            <strong>Alcut Studio</strong>
            <small>Vertical Clip Formatter</small>
          </span>
        </a>
        <input v-model="projectName" class="project-input" spellcheck="false" />
      </div>

      <div class="graph-toolbar" aria-label="Editor mode">
        <button class="tool-chip active" type="button">Template</button>
        <button class="tool-chip" type="button">Preview</button>
        <button class="tool-chip" type="button">AI Moments</button>
      </div>

      <div class="topbar-actions">
        <span class="job-status" :class="store.status">{{ statusLabel }}</span>
        <button class="export-button" :disabled="!canRender || store.isProcessing" type="button" @click="store.renderVertical">
          {{ store.activeJobType === 'render_vertical' ? 'Rendering...' : 'Export 9:16' }}
        </button>
      </div>
    </header>

    <main class="node-layout">
      <TemplateSidebar
        :selected-file="store.selectedFile"
        :templates="store.templates"
        :presets="store.presets"
        :selected-template-id="store.selectedTemplateId"
        :game-detection="store.gameDetection"
        :is-processing="store.isProcessing"
        :active-job-type="store.activeJobType"
        :moments-count="store.moments.length"
        @file-change="handleFileChange"
        @detect-game="store.detectGame"
        @load-template="loadTemplate"
        @load-preset="store.loadPreset"
        @run-moments="store.detectKeyMoments"
      />

      <section class="graph-canvas-wrap">
        <div class="graph-canvas">
          <div class="pipeline-strip" aria-label="Template pipeline">
            <article
              v-for="node in pipelineNodes"
              :key="node.id"
              class="pipeline-node"
              :class="{ active: node.active, complete: node.complete }"
            >
              <small>{{ node.kicker }}</small>
              <strong>{{ node.title }}</strong>
              <span>{{ node.status }}</span>
            </article>
          </div>

          <div class="pipeline-lines" aria-hidden="true">
            <span></span>
            <span></span>
            <span></span>
          </div>

          <VerticalPreview
            :source-video-url="store.sourceVideoUrl"
            :template="store.selectedTemplate"
            :params="store.templateParams"
          />

          <section v-if="store.moments.length" class="moment-strip">
            <div>
              <strong>{{ store.moments.length }} AI moments</strong>
              <span>{{ store.exportUrl ? 'Timeline export ready' : 'Secondary timeline available' }}</span>
            </div>
            <a v-if="store.exportUrl" :href="store.exportUrl" target="_blank" rel="noreferrer">Open timeline export</a>
            <button v-else type="button" :disabled="store.isProcessing" @click="store.exportProject">Export selected moments</button>
          </section>
        </div>
      </section>

      <TemplateInspector
        :template="store.selectedTemplate"
        :params="store.templateParams"
        :is-processing="store.isProcessing"
        :active-job-type="store.activeJobType"
        :can-render="canRender"
        :output-url="store.verticalExportUrl"
        :progress="store.progress"
        :status="store.status"
        :status-message="store.statusMessage"
        @update-param="store.updateTemplateParam"
        @render="store.renderVertical"
        @save-preset="showSavePreset = true"
      />
    </main>

    <GameDetectedModal
      v-if="showGameModal && store.gameDetection"
      :detection="store.gameDetection"
      :template="recommendedTemplate"
      @close="showGameModal = false"
      @load="loadRecommendedTemplate"
    />

    <SavePresetModal
      v-if="showSavePreset && store.selectedTemplate"
      :template="store.selectedTemplate"
      @close="showSavePreset = false"
      @save="handleSavePreset"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import GameDetectedModal from './components/GameDetectedModal.vue'
import SavePresetModal from './components/SavePresetModal.vue'
import TemplateInspector from './components/TemplateInspector.vue'
import TemplateSidebar from './components/TemplateSidebar.vue'
import VerticalPreview from './components/VerticalPreview.vue'
import { useEditorStore } from './stores/editorStore'

const store = useEditorStore()
const projectName = ref('Gameplay vertical template')
const showGameModal = ref(false)
const showSavePreset = ref(false)

const canRender = computed(() => Boolean(store.videoId && store.selectedTemplateId))
const statusLabel = computed(() => store.statusMessage || (store.selectedFile ? 'Media loaded' : 'Ready'))
const recommendedTemplate = computed(() => (
  store.templates.find(template => template.id === store.gameDetection?.recommendedTemplateId) || null
))

const pipelineNodes = computed(() => [
  {
    id: 'source',
    kicker: 'INPUT',
    title: 'Source Video',
    status: store.selectedFile ? store.selectedFile.name : 'Waiting for media',
    active: Boolean(store.selectedFile),
    complete: Boolean(store.videoId),
  },
  {
    id: 'detection',
    kicker: 'DETECT',
    title: 'Game Detection',
    status: store.gameDetection?.gameName || 'Filename heuristic',
    active: Boolean(store.selectedFile),
    complete: Boolean(store.gameDetection),
  },
  {
    id: 'template',
    kicker: 'LAYOUT',
    title: '9:16 Template',
    status: store.selectedTemplate?.name || 'No template selected',
    active: Boolean(store.gameDetection || store.selectedTemplate),
    complete: Boolean(store.selectedTemplate),
  },
  {
    id: 'render',
    kicker: 'OUTPUT',
    title: 'Vertical Render',
    status: store.verticalExportUrl ? 'MP4 ready' : '1080x1920 MP4',
    active: Boolean(store.selectedTemplate),
    complete: Boolean(store.verticalExportUrl),
  },
])

const handleFileChange = file => {
  showGameModal.value = false
  store.setSelectedFile(file)
}

const loadTemplate = async templateId => {
  if (!templateId) return
  if (!store.templates.length) await store.loadTemplates()
  store.loadTemplate(templateId)
  showGameModal.value = false
}

const loadRecommendedTemplate = () => {
  loadTemplate(store.gameDetection?.recommendedTemplateId)
}

const handleSavePreset = async payload => {
  const preset = await store.savePreset(payload)
  if (preset) showSavePreset.value = false
}

watch(
  () => store.gameDetection,
  detection => {
    if (detection) showGameModal.value = true
  },
)

onMounted(() => {
  store.loadWhisperCapabilities()
  store.loadTemplates()
  store.loadPresets()
})
</script>

<style scoped>
.node-studio-shell {
  min-height: 100vh;
  overflow: hidden;
  color: #f4f4f5;
  background:
    radial-gradient(circle at 50% -10%, rgba(34, 211, 238, 0.1), transparent 32%),
    linear-gradient(180deg, #0a0a0a, #050505);
  font-family: Geist, Inter, ui-sans-serif, system-ui, sans-serif;
  letter-spacing: 0;
}

.node-topbar {
  height: 72px;
  display: grid;
  grid-template-columns: 340px 1fr 340px;
  align-items: center;
  gap: 18px;
  padding: 0 18px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(10, 10, 10, 0.76);
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

.brand-stack {
  gap: 16px;
  min-width: 0;
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
  font-weight: 700;
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

.project-input {
  min-width: 0;
  width: 170px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: #e4e7ec;
  padding: 8px 10px;
  font: inherit;
  font-size: 13px;
}

.project-input:focus {
  outline: none;
  border-color: rgba(34, 211, 238, 0.35);
  background: rgba(255, 255, 255, 0.045);
}

.graph-toolbar {
  justify-self: center;
  gap: 7px;
  padding: 7px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.045);
  backdrop-filter: blur(24px);
}

.tool-chip {
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #9ca3af;
  cursor: pointer;
  font: inherit;
  padding: 7px 11px;
}

.tool-chip.active,
.tool-chip:hover {
  color: #f4f4f5;
  background: rgba(255, 255, 255, 0.08);
}

.topbar-actions {
  justify-self: end;
  gap: 12px;
  min-width: 0;
}

.job-status {
  max-width: 190px;
  color: #8a8f98;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.job-status.error {
  color: #fca5a5;
}

.job-status.processing {
  color: #67e8f9;
}

.export-button {
  border: 0;
  border-radius: 8px;
  background: #67e8f9;
  color: #001317;
  cursor: pointer;
  font: inherit;
  font-weight: 800;
  padding: 10px 16px;
  box-shadow: 0 0 28px rgba(34, 211, 238, 0.24);
}

.export-button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.node-layout {
  height: calc(100vh - 72px);
  display: grid;
  grid-template-columns: 300px 1fr 340px;
  gap: 16px;
  padding: 16px;
}

.graph-canvas-wrap {
  position: relative;
  min-width: 0;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background:
    linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px),
    #070707;
  background-size: 36px 36px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04), inset 0 0 70px rgba(0, 0, 0, 0.72);
}

.graph-canvas {
  min-height: 100%;
  display: grid;
  grid-template-rows: auto 1fr auto;
  gap: 18px;
  padding: 18px;
}

.pipeline-strip {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(4, minmax(140px, 1fr));
  gap: 12px;
}

.pipeline-lines {
  display: none;
}

.pipeline-node {
  min-height: 104px;
  display: grid;
  align-content: start;
  gap: 6px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(14, 14, 15, 0.82);
  box-shadow: 0 18px 56px rgba(0, 0, 0, 0.38);
  padding: 13px;
}

.pipeline-node.active {
  border-color: rgba(34, 211, 238, 0.34);
}

.pipeline-node.complete {
  border-color: rgba(45, 212, 191, 0.5);
  background: rgba(20, 184, 166, 0.08);
}

.pipeline-node small {
  color: #67e8f9;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.12em;
}

.pipeline-node strong {
  color: #f4f4f5;
  font-size: 15px;
}

.pipeline-node span {
  max-width: 100%;
  color: #a1a1aa;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.moment-strip {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.3);
  padding: 13px;
}

.moment-strip div {
  display: grid;
  gap: 3px;
}

.moment-strip strong {
  color: #f4f4f5;
}

.moment-strip span {
  color: #8a8f98;
  font-size: 12px;
}

.moment-strip a,
.moment-strip button {
  border: 0;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.08);
  color: #d4d4d8;
  cursor: pointer;
  font: inherit;
  font-weight: 750;
  padding: 9px 12px;
  text-decoration: none;
}

.moment-strip button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

@media (max-width: 1180px) {
  .node-topbar {
    grid-template-columns: 1fr auto;
    height: auto;
    min-height: 72px;
  }

  .graph-toolbar {
    display: none;
  }

  .node-layout {
    grid-template-columns: 280px 1fr;
  }

  :deep(.properties-panel) {
    display: none;
  }
}

@media (max-width: 860px) {
  .node-studio-shell {
    overflow: auto;
  }

  .node-topbar,
  .node-layout {
    display: block;
    height: auto;
  }

  .node-topbar {
    padding: 14px;
  }

  .topbar-actions {
    margin-top: 12px;
    justify-content: space-between;
  }

  .node-layout {
    padding: 12px;
  }

  .graph-canvas-wrap {
    margin: 12px 0;
  }

  .pipeline-strip {
    grid-template-columns: 1fr;
  }
}
</style>
