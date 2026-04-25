<template>
  <section class="range-editor" v-if="clip">
    <div class="range-topbar">
      <div class="selection-meta">
        <span class="eyebrow">Trim Selection</span>
        <strong>{{ formatTime(startValue) }} - {{ formatTime(endValue) }}</strong>
      </div>

      <div class="timeline-tools">
        <span class="duration">{{ (endValue - startValue).toFixed(3) }}s</span>
        <div class="zoom-toggle">
          <button :class="{ active: precision === 'seconds' }" @click="setPrecision('seconds')">Seconds</button>
          <button :class="{ active: precision === 'milliseconds' }" @click="setPrecision('milliseconds')">Milliseconds</button>
        </div>
      </div>
    </div>

    <div ref="timelineViewport" class="timeline-viewport" @wheel.prevent="scrollTimeline">
      <div class="timeline-content" :style="{ width: `${timelineWidth}px` }">
        <div class="ruler">
          <span
            v-for="tick in ticks"
            :key="tick.key"
            class="tick"
            :class="{ major: tick.major }"
            :style="{ left: `${tick.left}px` }"
          >
            <em v-if="tick.major">{{ tick.label }}</em>
          </span>
        </div>

        <div class="track-lane">
          <div class="track-line"></div>
          <div class="selected-clip" :style="clipStyle" @pointerdown="startDrag($event, 'body')">
            <button class="trim-handle start" title="Start" @pointerdown.stop="startDrag($event, 'start')"></button>
            <div class="clip-fill">
              <span>{{ formatTime(startValue) }}</span>
              <span>{{ formatTime(endValue) }}</span>
            </div>
            <button class="trim-handle end" title="End" @pointerdown.stop="startDrag($event, 'end')"></button>
          </div>
        </div>
      </div>
    </div>

    <div class="range-fields">
      <label>
        <span>Start</span>
        <input type="number" min="0" :step="inputStep" v-model.number="startValue" @input="updateStart" />
      </label>
      <label>
        <span>End</span>
        <input type="number" min="0" :step="inputStep" v-model.number="endValue" @input="updateEnd" />
      </label>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  clip: { type: Object, default: null },
  duration: { type: Number, default: 1 },
})

const emit = defineEmits(['change', 'scrub'])
const timelineViewport = ref(null)
const startValue = ref(0)
const endValue = ref(1)
const precision = ref('seconds')
const dragState = ref(null)

const minGap = 0.05
const clampedDuration = computed(() => Math.max(1, Number(props.duration) || 1))
const pixelsPerSecond = computed(() => (precision.value === 'milliseconds' ? 180 : 46))
const inputStep = computed(() => (precision.value === 'milliseconds' ? 0.001 : 0.1))
const timelineWidth = computed(() => Math.max(920, Math.ceil(clampedDuration.value * pixelsPerSecond.value) + 160))

const clipStyle = computed(() => ({
  left: `${startValue.value * pixelsPerSecond.value}px`,
  width: `${Math.max(18, (endValue.value - startValue.value) * pixelsPerSecond.value)}px`,
}))

const ticks = computed(() => {
  const step = precision.value === 'milliseconds' ? 0.1 : 1
  const totalTicks = Math.ceil(clampedDuration.value / step)
  const items = []
  for (let i = 0; i <= totalTicks; i += 1) {
    const time = Number((i * step).toFixed(3))
    const wholeSecond = Math.abs(time - Math.round(time)) < 0.0001
    const major = precision.value === 'seconds' ? i % 5 === 0 : wholeSecond
    items.push({
      key: `${precision.value}-${i}`,
      left: time * pixelsPerSecond.value,
      major,
      label: formatTime(time, precision.value === 'milliseconds'),
    })
  }
  return items
})

const setPrecision = value => {
  precision.value = value
  nextTick(scrollSelectedIntoView)
}

const scrollTimeline = event => {
  if (!timelineViewport.value) return
  timelineViewport.value.scrollLeft += event.deltaY + event.deltaX
}

const syncFromClip = () => {
  if (!props.clip) return
  startValue.value = Number(props.clip.start || 0)
  endValue.value = Number(props.clip.end || startValue.value + 1)
  nextTick(scrollSelectedIntoView)
}

const scrollSelectedIntoView = () => {
  const viewport = timelineViewport.value
  if (!viewport) return
  const target = Math.max(0, startValue.value * pixelsPerSecond.value - viewport.clientWidth * 0.25)
  viewport.scrollTo({ left: target, behavior: 'smooth' })
}

const clamp = (value, min, max) => Math.max(min, Math.min(max, value))

const timeFromPointer = event => {
  const viewport = timelineViewport.value
  if (!viewport) return 0
  const rect = viewport.getBoundingClientRect()
  const x = event.clientX - rect.left + viewport.scrollLeft
  return clamp(x / pixelsPerSecond.value, 0, clampedDuration.value)
}

const commit = scrubTime => {
  if (!props.clip) return
  emit('change', {
    id: props.clip.id,
    start: Number(startValue.value.toFixed(3)),
    end: Number(endValue.value.toFixed(3)),
  })
  emit('scrub', Number(scrubTime.toFixed(3)))
}

const updateStart = () => {
  startValue.value = clamp(Number(startValue.value) || 0, 0, endValue.value - minGap)
  commit(startValue.value)
}

const updateEnd = () => {
  endValue.value = clamp(Number(endValue.value) || 0, startValue.value + minGap, clampedDuration.value)
  commit(endValue.value)
}

const startDrag = (event, mode) => {
  event.currentTarget.setPointerCapture?.(event.pointerId)
  dragState.value = {
    mode,
    pointerStart: timeFromPointer(event),
    baseStart: startValue.value,
    baseEnd: endValue.value,
  }
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', stopDrag, { once: true })
}

const onPointerMove = event => {
  if (!dragState.value) return
  const pointerTime = timeFromPointer(event)
  const { mode, pointerStart, baseStart, baseEnd } = dragState.value

  if (mode === 'start') {
    startValue.value = clamp(pointerTime, 0, endValue.value - minGap)
    commit(startValue.value)
    return
  }

  if (mode === 'end') {
    endValue.value = clamp(pointerTime, startValue.value + minGap, clampedDuration.value)
    commit(endValue.value)
    return
  }

  const clipLength = baseEnd - baseStart
  const delta = pointerTime - pointerStart
  startValue.value = clamp(baseStart + delta, 0, clampedDuration.value - clipLength)
  endValue.value = startValue.value + clipLength
  commit(startValue.value)
}

const stopDrag = () => {
  dragState.value = null
  window.removeEventListener('pointermove', onPointerMove)
}

const formatTime = (seconds, showMillis = true) => {
  const total = Math.max(0, Number(seconds) || 0)
  const minutes = Math.floor(total / 60)
  const wholeSeconds = Math.floor(total % 60)
  const millis = Math.round((total - Math.floor(total)) * 1000)
  return showMillis
    ? `${minutes}:${String(wholeSeconds).padStart(2, '0')}.${String(millis).padStart(3, '0')}`
    : `${minutes}:${String(wholeSeconds).padStart(2, '0')}`
}

watch(() => props.clip?.id, syncFromClip, { immediate: true })
watch(() => [props.clip?.start, props.clip?.end], syncFromClip)

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', onPointerMove)
})
</script>

<style scoped>
.range-editor {
  display: grid;
  grid-template-rows: auto minmax(118px, 1fr) auto;
  gap: 12px;
  max-height: 250px;
  min-height: 220px;
  padding: 12px 14px 14px;
  background: #171717;
  border-top: 1px solid #303034;
  color: #f3f0ea;
  overflow: hidden;
}

.range-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.selection-meta strong {
  display: block;
  margin-top: 3px;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 14px;
}

.eyebrow {
  color: #96928a;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 800;
}

.timeline-tools {
  display: flex;
  align-items: center;
  gap: 10px;
}

.duration {
  padding: 4px 8px;
  border-radius: 6px;
  background: #25252a;
  color: #e8ff47;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  font-weight: 800;
}

.zoom-toggle {
  display: grid;
  grid-template-columns: repeat(2, auto);
  border: 1px solid #34343a;
  border-radius: 7px;
  overflow: hidden;
  background: #222226;
}

.zoom-toggle button {
  border: 0;
  padding: 6px 9px;
  background: transparent;
  color: #a8a5a0;
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  font-weight: 800;
}

.zoom-toggle button.active {
  background: #00c9d8;
  color: #071315;
}

.timeline-viewport {
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
  border: 1px solid #2f2f34;
  border-radius: 8px;
  background:
    linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px) 0 0 / 46px 100%,
    #1f1f22;
  scrollbar-color: #56565f #242429;
  scrollbar-width: thin;
}

.timeline-viewport::-webkit-scrollbar {
  height: 10px;
}

.timeline-viewport::-webkit-scrollbar-track {
  background: #242429;
}

.timeline-viewport::-webkit-scrollbar-thumb {
  background: #56565f;
  border-radius: 999px;
}

.timeline-content {
  position: relative;
  height: 124px;
}

.ruler {
  position: relative;
  height: 34px;
  border-bottom: 1px solid #313137;
}

.tick {
  position: absolute;
  bottom: 0;
  width: 1px;
  height: 9px;
  background: #4a4a50;
}

.tick.major {
  height: 17px;
  background: #787882;
}

.tick em {
  position: absolute;
  left: 6px;
  top: -2px;
  color: #9c9ca5;
  font-style: normal;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11px;
  white-space: nowrap;
}

.track-lane {
  position: relative;
  height: 90px;
  padding: 24px 0;
}

.track-line {
  position: absolute;
  left: 0;
  right: 0;
  top: 44px;
  height: 1px;
  background: #323238;
}

.selected-clip {
  position: absolute;
  top: 20px;
  height: 56px;
  min-width: 18px;
  border: 2px solid #eef7f7;
  border-radius: 5px;
  background: #00666b;
  box-shadow: 0 0 0 1px rgba(0, 201, 216, 0.35), 0 10px 28px rgba(0, 0, 0, 0.32);
  cursor: grab;
  touch-action: none;
}

.selected-clip:active {
  cursor: grabbing;
}

.clip-fill {
  height: 100%;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 10px;
  color: #f4ffff;
  background:
    repeating-linear-gradient(90deg, rgba(255,255,255,0.16) 0 2px, transparent 2px 16px),
    linear-gradient(180deg, #0d7e84, #034f54);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  font-weight: 800;
  overflow: hidden;
}

.trim-handle {
  position: absolute;
  top: -2px;
  width: 13px;
  height: 56px;
  border: 0;
  background: #f4ffff;
  cursor: ew-resize;
  z-index: 2;
}

.trim-handle::after {
  content: '';
  position: absolute;
  inset: 18px 5px;
  border-left: 2px solid #0d6a70;
  border-right: 2px solid #0d6a70;
}

.trim-handle.start {
  left: -8px;
  border-radius: 5px 0 0 5px;
}

.trim-handle.end {
  right: -8px;
  border-radius: 0 5px 5px 0;
}

.range-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 150px));
  gap: 10px;
}

label {
  display: grid;
  gap: 5px;
  color: #aaa6a0;
  font-size: 11px;
  font-weight: 800;
}

label input {
  width: 100%;
  border: 1px solid #3a3a40;
  border-radius: 7px;
  padding: 7px 9px;
  background: #242429;
  color: #f4f1ea;
  font: inherit;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

@media (max-width: 700px) {
  .range-topbar,
  .timeline-tools {
    align-items: stretch;
    flex-direction: column;
  }

  .range-fields {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
