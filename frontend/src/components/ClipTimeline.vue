<template>
  <aside class="timeline-panel">
    <div class="panel-head">
      <span class="eyebrow">AI Moments</span>
      <strong>{{ clips.length }} detected</strong>
    </div>
    <ol class="clip-list">
      <li v-for="(clip, index) in clips" :key="clip.id">
        <button
          class="clip-item"
          :class="{ active: clip.id === selectedId }"
          @click="$emit('select', clip)"
        >
          <span class="clip-index">{{ String(index + 1).padStart(2, '0') }}</span>
          <span class="clip-copy">
            <span class="clip-time">{{ formatTime(clip.start) }} - {{ formatTime(clip.end) }}</span>
            <span class="clip-reason">{{ clip.reason }}</span>
          </span>
          <span class="clip-score">{{ clip.score.toFixed(1) }}</span>
        </button>
      </li>
    </ol>
  </aside>
</template>

<script setup>
defineProps({
  clips: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' },
})

defineEmits(['select'])

const formatTime = seconds => {
  const total = Math.max(0, Number(seconds) || 0)
  const minutes = Math.floor(total / 60)
  const wholeSeconds = Math.floor(total % 60)
  const millis = Math.round((total - Math.floor(total)) * 1000)
  return `${minutes}:${String(wholeSeconds).padStart(2, '0')}.${String(millis).padStart(3, '0')}`
}
</script>

<style scoped>
.timeline-panel {
  display: flex;
  flex-direction: column;
  min-width: 280px;
  min-height: 0;
  height: 100%;
  background: #171717;
  border-left: 1px solid #2a2a2a;
  overflow: hidden;
}

.panel-head {
  flex: 0 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  padding: 18px;
  border-bottom: 1px solid #2a2a2a;
  color: #f7f7f2;
}

.eyebrow {
  color: #a5a29a;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 700;
}

.clip-list {
  flex: 1 1 auto;
  min-height: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-color: #55545a #202024;
  scrollbar-width: thin;
}

.clip-list::-webkit-scrollbar {
  width: 10px;
}

.clip-list::-webkit-scrollbar-track {
  background: #202024;
}

.clip-list::-webkit-scrollbar-thumb {
  background: #55545a;
  border-radius: 999px;
  border: 2px solid #202024;
}

.clip-item {
  width: 100%;
  display: grid;
  grid-template-columns: 32px 1fr auto;
  align-items: start;
  gap: 10px;
  padding: 11px 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: #dedbd4;
  text-align: left;
  cursor: pointer;
  font: inherit;
}

.clip-item:hover,
.clip-item.active {
  background: #232323;
  border-color: #383838;
}

.clip-item.active {
  box-shadow: inset 3px 0 0 #e8ff47;
}

.clip-index,
.clip-time {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.clip-index {
  color: #737068;
  font-size: 12px;
}

.clip-copy {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.clip-time {
  font-size: 12px;
  color: #f7f7f2;
}

.clip-reason {
  color: #aaa69d;
  font-size: 12px;
  line-height: 1.35;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.clip-score {
  padding: 2px 7px;
  border-radius: 999px;
  background: #e8ff47;
  color: #151515;
  font-size: 11px;
  font-weight: 700;
}
</style>
