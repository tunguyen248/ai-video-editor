<template>
  <aside class="layer-panel glass-panel">
    <div class="panel-title">
      <span>Layers</span>
      <button type="button" @click="$emit('add')">Add</button>
    </div>

    <div class="layer-list">
      <article
        v-for="(layer, index) in displayLayers"
        :key="layer.id"
        class="layer-row"
        :class="{ active: layer.id === selectedLayerId, muted: layer.visible === false }"
        @click="$emit('select', layer.id)"
      >
        <button
          type="button"
          class="visibility-button"
          :aria-label="layer.visible === false ? 'Show layer' : 'Hide layer'"
          @click.stop="$emit('toggle-visible', layer.id)"
        >
          {{ layer.visible === false ? 'Off' : 'On' }}
        </button>

        <div class="layer-copy">
          <strong>{{ layer.name || layer.id }}</strong>
          <span>{{ layer.id }} / z{{ layer.zIndex }}</span>
        </div>

        <div class="row-actions">
          <button
            type="button"
            :disabled="index === 0"
            @click.stop="$emit('move-layer', layer.id, 'up')"
          >
            Up
          </button>
          <button
            type="button"
            :disabled="index === displayLayers.length - 1"
            @click.stop="$emit('move-layer', layer.id, 'down')"
          >
            Down
          </button>
          <button type="button" @click.stop="$emit('duplicate', layer.id)">Copy</button>
          <button type="button" class="danger" @click.stop="$emit('delete', layer.id)">Del</button>
        </div>
      </article>
    </div>
  </aside>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  layers: {
    type: Array,
    default: () => [],
  },
  selectedLayerId: {
    type: String,
    default: '',
  },
})

defineEmits(['select', 'add', 'duplicate', 'delete', 'toggle-visible', 'move-layer'])

const displayLayers = computed(() => (
  [...props.layers].sort((a, b) => Number(b.zIndex || 0) - Number(a.zIndex || 0))
))
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

.layer-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  overflow: hidden;
}

.panel-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.panel-title span {
  color: #f4f4f5;
  font-size: 13px;
  font-weight: 800;
}

button {
  border: 0;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.08);
  color: #d4d4d8;
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  font-weight: 800;
  padding: 7px 8px;
}

button:hover:not(:disabled) {
  background: rgba(103, 232, 249, 0.16);
  color: #ecfeff;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.36;
}

.panel-title button,
.visibility-button {
  color: #031214;
  background: #67e8f9;
}

.layer-list {
  min-height: 0;
  display: grid;
  gap: 9px;
  overflow: auto;
  padding-right: 2px;
}

.layer-row {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 9px;
  align-items: start;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.22);
  cursor: pointer;
  padding: 10px;
}

.layer-row.active {
  border-color: rgba(192, 132, 252, 0.58);
  background: rgba(124, 58, 237, 0.12);
  box-shadow: 0 0 24px rgba(124, 58, 237, 0.12);
}

.layer-row.muted {
  opacity: 0.55;
}

.layer-copy {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.layer-copy strong {
  overflow: hidden;
  color: #f4f4f5;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.layer-copy span {
  overflow: hidden;
  color: #8a8f98;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-actions {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
}

.danger {
  color: #fecaca;
  background: rgba(239, 68, 68, 0.14);
}
</style>
