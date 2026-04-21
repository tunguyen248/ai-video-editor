<template>
  <section class="video-editor">
    <h1>Local MVP Video Editor</h1>
    <p>Upload a video and trim it from 25s to 120s using the backend service.</p>

    <input
      type="file"
      accept="video/*"
      @change="handleFileChange"
      :disabled="status === 'processing'"
    />

    <button @click="processVideo" :disabled="!selectedFile || status === 'processing'">
      {{ status === 'processing' ? 'Processing...' : 'Process Video' }}
    </button>

    <div class="status-area">
      <p v-if="status === 'idle'">Status: Idle. Select a video to begin.</p>
      <p v-else-if="status === 'processing'">Status: Processing your video...</p>
      <p v-else-if="status === 'complete'" class="success">{{ statusMessage }}</p>
      <p v-else-if="status === 'error'" class="error">{{ statusMessage }}</p>

      <p v-if="downloadUrl">
        Download result:
        <a :href="downloadUrl" target="_blank" rel="noopener">{{ downloadUrl }}</a>
      </p>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'

const selectedFile = ref(null)
const status = ref('idle') // idle | processing | complete | error
const statusMessage = ref('')
const downloadUrl = ref('')

const handleFileChange = (event) => {
  const file = event.target.files?.[0] ?? null
  selectedFile.value = file
  status.value = 'idle'
  statusMessage.value = ''
  downloadUrl.value = ''
}

const processVideo = async () => {
  if (!selectedFile.value) {
    status.value = 'error'
    statusMessage.value = 'Please select a video file first.'
    return
  }

  status.value = 'processing'
  statusMessage.value = ''
  downloadUrl.value = ''

  const formData = new FormData()
  formData.append('video', selectedFile.value)

  try {
    const response = await fetch('http://localhost:5000/process_video', {
      method: 'POST',
      body: formData,
    })

    const payload = await response.json()

    if (!response.ok) {
      throw new Error(payload.error || 'Video processing failed.')
    }

    const backendPath = payload.trimmed_video_path
    const absoluteUrl = `http://localhost:5000${backendPath}`

    status.value = 'complete'
    statusMessage.value = 'Video processed successfully.'
    downloadUrl.value = absoluteUrl
  } catch (error) {
    status.value = 'error'
    statusMessage.value = error.message || 'Unexpected error during processing.'
  }
}
</script>

<style scoped>
.video-editor {
  max-width: 720px;
  margin: 2rem auto;
  padding: 1.25rem;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  font-family: Arial, sans-serif;
}

input,
button {
  display: block;
  margin-top: 1rem;
}

button {
  padding: 0.6rem 1rem;
  border: 0;
  border-radius: 8px;
  background: #2563eb;
  color: #ffffff;
  cursor: pointer;
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.status-area {
  margin-top: 1rem;
}

.success {
  color: #166534;
}

.error {
  color: #b91c1c;
}
</style>
