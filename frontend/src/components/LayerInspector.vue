<template>
  <aside class="inspector-panel glass-panel">
    <div class="panel-title">
      <span>Inspector</span>
      <small>{{ layer?.name || 'No layer selected' }}</small>
    </div>

    <section v-if="layer" class="inspector-content">
      <div class="identity-grid">
        <label>
          <span>ID</span>
          <input :value="layer.id" spellcheck="false" @input="updateRoot('id', $event.target.value)" />
        </label>
        <label>
          <span>Name</span>
          <input :value="layer.name" spellcheck="false" @input="updateRoot('name', $event.target.value)" />
        </label>
      </div>

      <div class="toggle-row">
        <label>
          <input type="checkbox" :checked="layer.visible !== false" @change="updateRoot('visible', $event.target.checked)" />
          <span>Visible</span>
        </label>
        <strong>{{ layer.type }}</strong>
      </div>

      <fieldset>
        <legend>Source Box</legend>
        <div class="rect-grid">
          <label v-for="field in rectFields" :key="`source-${field}`">
            <span>{{ field }}</span>
            <input
              type="number"
              step="1"
              :min="field === 'x' || field === 'y' ? 0 : 1"
              :max="sourceMax(field)"
              :value="layer.sourceRect?.[field]"
              @input="updateRect('sourceRect', field, $event.target.value)"
            />
          </label>
        </div>
      </fieldset>

      <fieldset>
        <legend>Destination Rect</legend>
        <div class="rect-grid">
          <label v-for="field in rectFields" :key="`destination-${field}`">
            <span>{{ field }}</span>
            <input
              type="number"
              step="1"
              :min="field === 'x' || field === 'y' ? 0 : 1"
              :max="destinationMax(field)"
              :value="layer.destinationRect?.[field]"
              @input="updateRect('destinationRect', field, $event.target.value)"
            />
          </label>
        </div>
      </fieldset>

      <div class="property-grid">
        <label>
          <span>Z Index</span>
          <input type="number" step="1" :value="layer.zIndex" @input="updateRoot('zIndex', Number($event.target.value))" />
        </label>
        <label>
          <span>Opacity</span>
          <input type="number" min="0" max="1" step="0.05" :value="layer.opacity" @input="updateRoot('opacity', Number($event.target.value))" />
        </label>
      </div>

      <label class="opacity-slider">
        <span>Opacity</span>
        <input type="range" min="0" max="1" step="0.01" :value="layer.opacity" @input="updateRoot('opacity', Number($event.target.value))" />
      </label>
    </section>

    <section v-else class="empty-state">
      <strong>Select a crop layer</strong>
      <span>Layer properties will appear here.</span>
    </section>
  </aside>
</template>

<script setup>
const props = defineProps({
  layer: {
    type: Object,
    default: null,
  },
  outputSize: {
    type: Object,
    default: () => ({ width: 1080, height: 1920 }),
  },
  sourceSize: {
    type: Object,
    default: () => ({ width: 1920, height: 1080 }),
  },
})

const emit = defineEmits(['update-layer'])

const rectFields = ['x', 'y', 'width', 'height']

function updateRoot(field, value) {
  if (!props.layer) return
  emit('update-layer', props.layer.id, { [field]: value })
}

function updateRect(rectName, field, value) {
  if (!props.layer) return
  emit('update-layer', props.layer.id, {
    [rectName]: {
      [field]: Number(value),
    },
  })
}

function destinationMax(field) {
  if (field === 'x' || field === 'width') return props.outputSize?.width || 1080
  return props.outputSize?.height || 1920
}

function sourceMax(field) {
  if (field === 'x' || field === 'width') return props.sourceSize?.width || 1920
  return props.sourceSize?.height || 1080
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

.inspector-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
  padding: 16px;
}

.panel-title {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
}

.panel-title span {
  color: #f4f4f5;
  font-size: 13px;
  font-weight: 800;
}

.panel-title small {
  max-width: 180px;
  overflow: hidden;
  color: #71717a;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inspector-content {
  min-height: 0;
  display: grid;
  gap: 12px;
  overflow: auto;
  padding-right: 2px;
}

.identity-grid,
.property-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 9px;
}

label {
  min-width: 0;
  display: grid;
  gap: 5px;
}

label span,
legend {
  color: #8a8f98;
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}

input {
  min-width: 0;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.055);
  color: #f4f4f5;
  font: inherit;
  font-size: 12px;
  padding: 9px 10px;
}

input:focus {
  outline: none;
  border-color: rgba(103, 232, 249, 0.5);
  box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.12);
}

.toggle-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.22);
  padding: 10px;
}

.toggle-row label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.toggle-row input {
  width: 16px;
  height: 16px;
  accent-color: #22d3ee;
}

.toggle-row strong {
  color: #c4b5fd;
  font-size: 11px;
  font-weight: 800;
}

fieldset {
  display: grid;
  gap: 10px;
  margin: 0;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.22);
  padding: 12px;
}

legend {
  padding: 0 5px;
}

.rect-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.opacity-slider input {
  padding: 0;
  accent-color: #c084fc;
}

.empty-state {
  min-height: 180px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 6px;
  border: 1px dashed rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.18);
  text-align: center;
}

.empty-state strong {
  color: #f4f4f5;
  font-size: 13px;
}

.empty-state span {
  color: #8a8f98;
  font-size: 12px;
}
</style>
