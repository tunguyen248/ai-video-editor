<template>
  <section class="preview-shell" aria-label="Vertical template preview">
    <div class="phone-frame" :style="frameStyle">
      <template v-if="sourceVideoUrl">
        <video class="preview-bg" :src="sourceVideoUrl" muted playsinline loop autoplay></video>
        <video class="preview-fg" :src="sourceVideoUrl" muted playsinline controls :style="foregroundStyle"></video>
      </template>
      <div v-else class="preview-placeholder">
        <strong>9:16 Preview</strong>
        <span>{{ template?.name || 'Select a template' }}</span>
      </div>
    </div>

    <div class="preview-meta">
      <span>{{ template?.game || 'Game' }}</span>
      <strong>{{ template?.name || 'No template selected' }}</strong>
      <small>{{ outputLabel }}</small>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  sourceVideoUrl: {
    type: String,
    default: '',
  },
  template: {
    type: Object,
    default: null,
  },
  params: {
    type: Object,
    default: () => ({}),
  },
})

const outputLabel = computed(() => {
  const output = props.template?.output
  if (!output) return '1080x1920 / 60 FPS / MP4'
  return `${output.width}x${output.height} / ${output.fps} FPS / ${String(output.format || 'mp4').toUpperCase()}`
})

const frameStyle = computed(() => ({
  '--preview-blur': `${Math.max(0, Number(props.params.backgroundBlur ?? 22))}px`,
}))

const foregroundStyle = computed(() => {
  const scale = Number(props.params.gameplayScale ?? 0.92)
  const x = Number(props.params.gameplayX ?? 0) / 9
  const y = Number(props.params.gameplayY ?? -40) / 9
  const fit = props.template?.sourceFit || 'width'
  const width = `${Math.max(5, scale * 100)}%`
  const height = fit === 'contain' ? `${Math.max(5, scale * 100)}%` : '100%'

  return {
    width,
    height,
    transform: `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`,
  }
})
</script>

<style scoped>
.preview-shell {
  display: grid;
  grid-template-columns: minmax(230px, 300px) minmax(180px, 1fr);
  align-items: center;
  justify-content: center;
  gap: 24px;
  width: min(780px, 100%);
  margin: 0 auto;
}

.phone-frame {
  position: relative;
  aspect-ratio: 9 / 16;
  width: min(300px, 100%);
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 8px;
  background: #050505;
  box-shadow: 0 28px 90px rgba(0, 0, 0, 0.58);
}

.preview-bg,
.preview-fg {
  position: absolute;
}

.preview-bg {
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  filter: blur(var(--preview-blur, 22px));
  transform: scale(1.08);
  opacity: 0.72;
}

.preview-fg {
  left: 50%;
  top: 50%;
  object-fit: contain;
  transform-origin: center center;
}

.preview-placeholder {
  height: 100%;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 6px;
  background:
    linear-gradient(rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.04) 1px, transparent 1px),
    #090a0b;
  background-size: 28px 28px;
  text-align: center;
}

.preview-placeholder strong {
  color: #f4f4f5;
}

.preview-placeholder span {
  color: #8a8f98;
  font-size: 12px;
}

.preview-meta {
  display: grid;
  gap: 7px;
}

.preview-meta span {
  color: #67e8f9;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.preview-meta strong {
  color: #f4f4f5;
  font-size: 28px;
  line-height: 1.05;
}

.preview-meta small {
  color: #a1a1aa;
  font-size: 13px;
}

@media (max-width: 760px) {
  .preview-shell {
    grid-template-columns: 1fr;
  }

  .phone-frame {
    justify-self: center;
  }
}
</style>
