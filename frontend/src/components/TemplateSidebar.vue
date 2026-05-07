<template>
  <aside class="asset-panel glass-panel">
    <section class="panel-block">
      <div class="panel-section-title">
        <span>Input</span>
        <small>Media source</small>
      </div>

      <label
        class="upload-zone"
        :class="{ 'has-file': Boolean(selectedFile) }"
        @dragover.prevent
        @drop.prevent="handleDrop"
      >
        <input type="file" accept="video/*" @change="handleFileInput" />
        <strong>{{ selectedFile?.name || 'Drop a video file' }}</strong>
        <small>{{ selectedFile ? 'Ready for detection' : 'or click to browse local files' }}</small>
      </label>

      <button class="primary-button wide" :disabled="!selectedFile || isProcessing" type="button" @click="$emit('detect-game')">
        {{ isDetecting ? 'Detecting...' : 'Detect Game' }}
      </button>
    </section>

    <section v-if="gameDetection" class="panel-block detected-block">
      <div class="panel-section-title">
        <span>Detected</span>
        <small>{{ confidenceLabel }}</small>
      </div>
      <div class="detected-summary">
        <strong>{{ gameDetection.gameName === 'Unknown' ? 'Generic' : gameDetection.gameName }}</strong>
        <span>{{ recommendedTemplateName }}</span>
      </div>
      <button class="secondary-button wide" type="button" @click="$emit('load-template', gameDetection.recommendedTemplateId)">
        Load Template
      </button>
    </section>

    <section class="panel-block">
      <div class="panel-section-title">
        <span>Templates</span>
        <small>{{ templates.length }}</small>
      </div>

      <div class="template-list">
        <button
          v-for="template in templates"
          :key="template.id"
          class="template-row"
          :class="{ active: template.id === selectedTemplateId }"
          type="button"
          @click="$emit('load-template', template.id)"
        >
          <span>
            <strong>{{ template.name }}</strong>
            <small>{{ template.game }} / {{ template.category }}</small>
          </span>
          <i>{{ template.aspectRatio }}</i>
        </button>
      </div>
    </section>

    <section class="panel-block">
      <div class="panel-section-title">
        <span>User Presets</span>
        <small>{{ presets.length }}</small>
      </div>

      <div v-if="presets.length" class="template-list">
        <button
          v-for="preset in presets"
          :key="preset.id"
          class="template-row preset-row"
          type="button"
          @click="$emit('load-preset', preset)"
        >
          <span>
            <strong>{{ preset.name }}</strong>
            <small>{{ preset.game }} / {{ preset.category }}</small>
          </span>
        </button>
      </div>
      <p v-else class="empty-copy">No presets saved yet.</p>
    </section>

    <section class="panel-block secondary-flow">
      <div class="panel-section-title">
        <span>AI Moment Graph</span>
        <small>{{ momentsCount }} clips</small>
      </div>
      <button class="ghost-button wide" :disabled="!selectedFile || isProcessing" type="button" @click="$emit('run-moments')">
        Run AI Moment Graph
      </button>
    </section>
  </aside>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  selectedFile: {
    type: Object,
    default: null,
  },
  templates: {
    type: Array,
    default: () => [],
  },
  presets: {
    type: Array,
    default: () => [],
  },
  selectedTemplateId: {
    type: String,
    default: '',
  },
  gameDetection: {
    type: Object,
    default: null,
  },
  isProcessing: {
    type: Boolean,
    default: false,
  },
  activeJobType: {
    type: String,
    default: '',
  },
  momentsCount: {
    type: Number,
    default: 0,
  },
})

const emit = defineEmits(['file-change', 'detect-game', 'load-template', 'load-preset', 'run-moments'])

const isDetecting = computed(() => props.isProcessing && props.activeJobType === 'detect_game')
const confidenceLabel = computed(() => `${Math.round(Number(props.gameDetection?.confidence || 0) * 100)}%`)
const recommendedTemplateName = computed(() => {
  const template = props.templates.find(item => item.id === props.gameDetection?.recommendedTemplateId)
  return template?.name || 'Generic Gaming 9:16'
})

const handleFileInput = event => {
  const file = event.target.files?.[0]
  if (file) emit('file-change', file)
}

const handleDrop = event => {
  const file = Array.from(event.dataTransfer?.files || []).find(item => item.type.startsWith('video/'))
  if (file) emit('file-change', file)
}
</script>

<style scoped>
.glass-panel {
  min-height: 0;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.075), rgba(255, 255, 255, 0.035));
  backdrop-filter: blur(30px);
  box-shadow: 0 20px 70px rgba(0, 0, 0, 0.48);
}

.asset-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  overflow: auto;
}

.panel-block {
  display: grid;
  gap: 10px;
}

.panel-section-title {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
}

.panel-section-title span {
  color: #f4f4f5;
  font-size: 13px;
  font-weight: 750;
}

.panel-section-title small {
  color: #71717a;
  font-size: 11px;
}

.upload-zone {
  min-height: 142px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 7px;
  overflow: hidden;
  border: 1px dashed rgba(255, 255, 255, 0.16);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.28);
  cursor: pointer;
  text-align: center;
}

.upload-zone input {
  display: none;
}

.upload-zone strong {
  max-width: 220px;
  color: #f4f4f5;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-zone small,
.empty-copy {
  color: #8a8f98;
  font-size: 12px;
}

.upload-zone.has-file {
  border-color: rgba(34, 211, 238, 0.45);
  background: rgba(34, 211, 238, 0.055);
}

.primary-button,
.secondary-button,
.ghost-button {
  border: 0;
  border-radius: 8px;
  cursor: pointer;
  font: inherit;
  font-weight: 750;
  padding: 10px 13px;
}

.wide {
  width: 100%;
}

.primary-button {
  color: #031214;
  background: #67e8f9;
  box-shadow: 0 0 24px rgba(34, 211, 238, 0.24);
}

.secondary-button {
  color: #e7fbff;
  background: rgba(34, 211, 238, 0.15);
}

.ghost-button {
  color: #d4d4d8;
  background: rgba(255, 255, 255, 0.08);
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.detected-summary {
  display: grid;
  gap: 3px;
  padding: 12px;
  border: 1px solid rgba(103, 232, 249, 0.18);
  border-radius: 8px;
  background: rgba(34, 211, 238, 0.07);
}

.detected-summary strong {
  color: #f4f4f5;
}

.detected-summary span {
  color: #a1a1aa;
  font-size: 12px;
}

.template-list {
  display: grid;
  gap: 8px;
}

.template-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  color: inherit;
  cursor: pointer;
  padding: 11px;
  text-align: left;
}

.template-row.active {
  border-color: rgba(34, 211, 238, 0.66);
  background: rgba(34, 211, 238, 0.12);
  box-shadow: 0 0 24px rgba(34, 211, 238, 0.16);
}

.template-row span {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.template-row strong {
  color: #f4f4f5;
  font-size: 13px;
}

.template-row small {
  color: #8a8f98;
  font-size: 11px;
}

.template-row i {
  color: #67e8f9;
  font-size: 11px;
  font-style: normal;
  font-weight: 800;
}

.preset-row {
  border-style: dashed;
}

.secondary-flow {
  margin-top: auto;
}
</style>
