<template>
  <section class="json-panel glass-panel">
    <div class="panel-title">
      <div>
        <span>Template JSON</span>
        <small>{{ template.layers?.length || 0 }} layers</small>
      </div>
      <div class="json-actions">
        <button type="button" @click="copyJson">{{ copyLabel }}</button>
        <button type="button" @click="downloadJson">Download</button>
      </div>
    </div>

    <pre>{{ jsonText }}</pre>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  template: {
    type: Object,
    required: true,
  },
})

const copyLabel = ref('Copy')
const jsonText = computed(() => JSON.stringify(props.template, null, 2))

async function copyJson() {
  try {
    await navigator.clipboard.writeText(jsonText.value)
    copyLabel.value = 'Copied'
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = jsonText.value
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    copyLabel.value = 'Copied'
  }

  window.setTimeout(() => {
    copyLabel.value = 'Copy'
  }, 1400)
}

function downloadJson() {
  const blob = new Blob([jsonText.value], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${props.template.id || 'template'}.json`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
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

.json-panel {
  min-width: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
  padding: 16px;
}

.panel-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.panel-title div:first-child {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.panel-title span {
  color: #f4f4f5;
  font-size: 13px;
  font-weight: 800;
}

.panel-title small {
  color: #71717a;
  font-size: 11px;
}

.json-actions {
  display: flex;
  gap: 8px;
}

button {
  border: 0;
  border-radius: 7px;
  background: rgba(103, 232, 249, 0.14);
  color: #cffafe;
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  font-weight: 800;
  padding: 8px 9px;
}

button:last-child {
  background: rgba(192, 132, 252, 0.16);
  color: #ede9fe;
}

pre {
  min-height: 0;
  overflow: auto;
  margin: 0;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.32);
  color: #d4d4d8;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 11px;
  line-height: 1.55;
  padding: 12px;
  white-space: pre;
}
</style>
