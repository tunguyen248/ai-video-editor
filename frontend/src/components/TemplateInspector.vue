<template>
  <aside class="properties-panel glass-panel">
    <div class="panel-section-title">
      <span>Inspector</span>
      <small>{{ template?.name || 'No template selected' }}</small>
    </div>

    <section v-if="template" class="inspector-card">
      <div class="template-heading">
        <div>
          <strong>{{ template.name }}</strong>
          <span>{{ template.game }} / {{ template.category }}</span>
        </div>
        <i>{{ template.aspectRatio }}</i>
      </div>
    </section>

    <section v-if="template" class="inspector-card controls-card">
      <div class="card-title">
        <strong>Template Controls</strong>
      </div>

      <label v-for="control in template.controls" :key="control.id" class="range-control">
        <span>
          <b>{{ control.label }}</b>
          <em>{{ displayValue(control) }}</em>
        </span>
        <input
          type="range"
          :min="control.min"
          :max="control.max"
          :step="control.step"
          :value="controlValue(control)"
          @input="$emit('update-param', control.id, $event.target.value)"
        />
        <input
          type="number"
          :min="control.min"
          :max="control.max"
          :step="control.step"
          :value="controlValue(control)"
          @input="$emit('update-param', control.id, $event.target.value)"
        />
      </label>
    </section>

    <section class="inspector-card output-card">
      <div class="card-title">
        <strong>Output</strong>
      </div>
      <dl>
        <div>
          <dt>Size</dt>
          <dd>{{ output.width }}x{{ output.height }}</dd>
        </div>
        <div>
          <dt>FPS</dt>
          <dd>{{ output.fps }}</dd>
        </div>
        <div>
          <dt>Format</dt>
          <dd>{{ output.format }}</dd>
        </div>
      </dl>
    </section>

    <section class="inspector-card action-card">
      <button class="ghost-button" :disabled="!template" type="button" @click="$emit('save-preset')">Save Preset</button>
      <button class="primary-button" :disabled="!canRender || isProcessing" type="button" @click="$emit('render')">
        {{ isRendering ? 'Rendering...' : 'Export 9:16' }}
      </button>
      <a v-if="outputUrl" class="download-link" :href="outputUrl" target="_blank" rel="noreferrer">Open Vertical MP4</a>
    </section>

    <section class="inspector-card progress-card">
      <div class="progress-topline">
        <strong>Render Progress</strong>
        <span>{{ Math.round(progress) }}%</span>
      </div>
      <div class="progress-track"><i :style="{ width: `${progress}%` }"></i></div>
      <p :class="status">{{ statusMessage || 'Ready for a template export.' }}</p>
    </section>
  </aside>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  template: {
    type: Object,
    default: null,
  },
  params: {
    type: Object,
    default: () => ({}),
  },
  isProcessing: {
    type: Boolean,
    default: false,
  },
  activeJobType: {
    type: String,
    default: '',
  },
  canRender: {
    type: Boolean,
    default: false,
  },
  outputUrl: {
    type: String,
    default: '',
  },
  progress: {
    type: Number,
    default: 0,
  },
  status: {
    type: String,
    default: 'idle',
  },
  statusMessage: {
    type: String,
    default: '',
  },
})

defineEmits(['update-param', 'render', 'save-preset'])

const output = computed(() => ({
  width: props.template?.output?.width || 1080,
  height: props.template?.output?.height || 1920,
  fps: props.template?.output?.fps || 60,
  format: props.template?.output?.format || 'mp4',
}))

const isRendering = computed(() => props.isProcessing && props.activeJobType === 'render_vertical')

const controlValue = control => props.params[control.id] ?? control.default
const displayValue = control => Number(controlValue(control)).toFixed(Number(control.step) < 1 ? 2 : 0)
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

.properties-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  overflow: auto;
}

.panel-section-title,
.progress-topline,
.template-heading,
.card-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.panel-section-title span,
.card-title strong,
.progress-topline strong {
  color: #f4f4f5;
  font-size: 13px;
  font-weight: 750;
}

.panel-section-title small {
  color: #71717a;
  font-size: 11px;
}

.inspector-card {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.22);
}

.template-heading strong {
  display: block;
  color: #f4f4f5;
}

.template-heading span {
  color: #8a8f98;
  font-size: 12px;
}

.template-heading i {
  color: #67e8f9;
  font-size: 12px;
  font-style: normal;
  font-weight: 800;
}

.range-control {
  display: grid;
  grid-template-columns: 1fr 72px;
  gap: 8px 10px;
  color: #a1a1aa;
  font-size: 12px;
}

.range-control span {
  grid-column: 1 / -1;
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.range-control b {
  color: #d4d4d8;
  font-weight: 650;
}

.range-control em {
  color: #67e8f9;
  font-style: normal;
}

.range-control input[type='range'] {
  width: 100%;
  accent-color: #22d3ee;
}

.range-control input[type='number'] {
  width: 72px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.055);
  color: #f4f4f5;
  padding: 8px;
}

dl {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin: 0;
}

dl div {
  display: grid;
  gap: 3px;
}

dt {
  color: #71717a;
  font-size: 11px;
}

dd {
  margin: 0;
  color: #f4f4f5;
  font-size: 13px;
  font-weight: 700;
}

.action-card {
  grid-template-columns: 1fr 1fr;
}

.ghost-button,
.primary-button,
.download-link {
  display: inline-flex;
  justify-content: center;
  align-items: center;
  border: 0;
  border-radius: 8px;
  cursor: pointer;
  font: inherit;
  font-weight: 750;
  padding: 10px 13px;
  text-decoration: none;
}

.ghost-button {
  color: #d4d4d8;
  background: rgba(255, 255, 255, 0.08);
}

.primary-button,
.download-link {
  color: #031214;
  background: #67e8f9;
  box-shadow: 0 0 24px rgba(34, 211, 238, 0.24);
}

.download-link {
  grid-column: 1 / -1;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.progress-track {
  height: 8px;
  overflow: hidden;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.075);
}

.progress-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #22d3ee, #2dd4bf);
}

.progress-card p {
  margin: 0;
  color: #a1a1aa;
  font-size: 12px;
  line-height: 1.5;
}

.progress-card p.error {
  color: #fca5a5;
}

.progress-card p.processing {
  color: #67e8f9;
}
</style>
