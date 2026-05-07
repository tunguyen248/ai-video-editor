<template>
  <div class="modal-backdrop" role="presentation" @click.self="$emit('close')">
    <form class="modal-panel" role="dialog" aria-modal="true" aria-labelledby="save-preset-title" @submit.prevent="submit">
      <div class="modal-kicker">Layout Preset</div>
      <h2 id="save-preset-title">Save Preset</h2>

      <label>
        <span>Preset Name</span>
        <input v-model.trim="name" required maxlength="80" />
      </label>

      <label>
        <span>Game Category</span>
        <input :value="categoryLabel" disabled />
      </label>

      <label>
        <span>Description</span>
        <textarea v-model.trim="description" rows="3" maxlength="240"></textarea>
      </label>

      <div class="modal-actions">
        <button class="ghost-button" type="button" @click="$emit('close')">Cancel</button>
        <button class="primary-button" type="submit">Save Preset</button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  template: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['close', 'save'])
const name = ref('')
const description = ref('')

const categoryLabel = computed(() => {
  if (!props.template) return ''
  return `${props.template.game} / ${props.template.category}`
})

watch(
  () => props.template,
  template => {
    name.value = template ? `My ${template.game} Layout` : ''
    description.value = ''
  },
  { immediate: true },
)

const submit = () => {
  emit('save', {
    name: name.value,
    description: description.value,
  })
}
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
  width: min(460px, 100%);
  display: grid;
  gap: 14px;
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
  margin: 0;
  font-size: 24px;
}

label {
  display: grid;
  gap: 7px;
  color: #a1a1aa;
  font-size: 12px;
}

input,
textarea {
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.055);
  color: #f4f4f5;
  font: inherit;
  padding: 10px;
}

input:disabled {
  color: #8a8f98;
}

textarea {
  resize: vertical;
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
