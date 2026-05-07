<template>
  <div class="modal-backdrop" role="presentation" @click.self="$emit('close')">
    <section class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="game-detected-title">
      <div class="modal-kicker">{{ isFallback ? 'Fallback Template' : 'Game Detected' }}</div>
      <h2 id="game-detected-title">{{ isFallback ? 'No game template detected.' : 'Game Detected!' }}</h2>
      <p>
        {{ isFallback
          ? 'You can still use the Generic Gaming 9:16 template.'
          : `We noticed this looks like ${detection.gameName} gameplay.` }}
      </p>

      <div class="recommendation">
        <span>Recommended Template</span>
        <strong>{{ template?.name || 'Generic Gaming 9:16' }}</strong>
        <small v-if="!isFallback">Confidence: {{ confidencePercent }}%</small>
      </div>

      <div class="modal-actions">
        <button class="ghost-button" type="button" @click="$emit('close')">No Thanks</button>
        <button class="primary-button" type="button" @click="$emit('load')">
          {{ isFallback ? 'Use Generic Template' : 'Load Template' }}
        </button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  detection: {
    type: Object,
    required: true,
  },
  template: {
    type: Object,
    default: null,
  },
})

defineEmits(['close', 'load'])

const isFallback = computed(() => props.detection?.gameName === 'Unknown' || props.detection?.gameId === 'generic')
const confidencePercent = computed(() => Math.round(Number(props.detection?.confidence || 0) * 100))
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(0, 0, 0, 0.68);
  backdrop-filter: blur(18px);
}

.modal-panel {
  width: min(420px, 100%);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 8px;
  background: #101113;
  box-shadow: 0 24px 90px rgba(0, 0, 0, 0.62);
  padding: 22px;
}

.modal-kicker {
  color: #67e8f9;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h2 {
  margin: 8px 0 8px;
  font-size: 24px;
}

p {
  margin: 0;
  color: #a1a1aa;
  line-height: 1.55;
}

.recommendation {
  display: grid;
  gap: 5px;
  margin: 18px 0;
  padding: 14px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.045);
}

.recommendation span,
.recommendation small {
  color: #71717a;
  font-size: 12px;
}

.recommendation strong {
  color: #f4f4f5;
  font-size: 16px;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

button {
  border: 0;
  border-radius: 8px;
  cursor: pointer;
  font: inherit;
  font-weight: 750;
  padding: 10px 14px;
}

.ghost-button {
  color: #d4d4d8;
  background: rgba(255, 255, 255, 0.08);
}

.primary-button {
  color: #031214;
  background: #67e8f9;
  box-shadow: 0 0 24px rgba(34, 211, 238, 0.24);
}
</style>
