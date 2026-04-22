<template>
  <section class="video-editor">
    <h1>Phase 1: Time-Based MVP</h1>
    <p>Detect scene changes, review timestamps, then generate a hype reel.</p>

    <input
      type="file"
      accept="video/*"
      @change="handleFileChange"
      :disabled="status === 'processing'"
    />

    <div class="button-row">
      <button @click="detectScenes" :disabled="!selectedFile || status === 'processing'">
        Detect Scenes
      </button>

      <button @click="generateHypeReel" :disabled="!videoId || scenes.length === 0 || status === 'processing'">
        Generate Hype Reel
      </button>
    </div>

    <div class="status-area">
      <p v-if="status === 'idle'">Status: Idle</p>
      <p v-else-if="status === 'processing'">Status: Processing...</p>
      <p v-else-if="status === 'complete'" class="success">{{ statusMessage }}</p>
      <p v-else-if="status === 'error'" class="error">{{ statusMessage }}</p>
    </div>

    <div v-if="scenes.length > 0" class="scene-list">
      <h3>Detected Scene Timestamps</h3>
      <ul>
        <li v-for="(scene, index) in scenes" :key="`${scene.start}-${scene.end}-${index}`">
          Scene {{ index + 1 }}: {{ formatSeconds(scene.start) }}s → {{ formatSeconds(scene.end) }}s
        </li>
      </ul>
    </div>

    <div v-if="downloadUrl" class="result-box">
      <h3>Hype Reel Ready</h3>
      <a :href="downloadUrl" target="_blank" rel="noopener">Download / Open result</a>
    </div>
  </section>
</template>

<script setup>
import { ref } from 'vue'

const selectedFile = ref(null)
const videoId = ref('')
const scenes = ref([])
const status = ref('idle') // idle | processing | complete | error
const statusMessage = ref('')
const downloadUrl = ref('')

const handleFileChange = (event) => {
  const file = event.target.files?.[0] ?? null
  selectedFile.value = file
  videoId.value = ''
  scenes.value = []
  downloadUrl.value = ''
  status.value = 'idle'
  statusMessage.value = ''
}

const detectScenes = async () => {
  if (!selectedFile.value) {
    status.value = 'error'
    statusMessage.value = 'Please select a video file first.'
    return
  }

  status.value = 'processing'
  statusMessage.value = ''
  downloadUrl.value = ''
  scenes.value = []

  const formData = new FormData()
  formData.append('video', selectedFile.value)

  try {
    const response = await fetch('http://localhost:5000/analyze_scenes', {
      method: 'POST',
      body: formData,
    })

    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.error || 'Scene detection failed.')
    }

    videoId.value = payload.video_id
    scenes.value = Array.isArray(payload.scenes) ? payload.scenes : []
    status.value = 'complete'
    statusMessage.value = `Detected ${scenes.value.length} scene(s).`
  } catch (error) {
    status.value = 'error'
    statusMessage.value = error.message || 'Unexpected error while detecting scenes.'
  }
}

const generateHypeReel = async () => {
  if (!videoId.value || scenes.value.length === 0) {
    status.value = 'error'
    statusMessage.value = 'Detect scenes first before generating the hype reel.'
    return
  }

  status.value = 'processing'
  statusMessage.value = ''
  downloadUrl.value = ''

  try {
    const response = await fetch('http://localhost:5000/smart_cut', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        video_id: videoId.value,
        scenes: scenes.value,
      }),
    })

    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.error || 'Hype reel generation failed.')
    }

    downloadUrl.value = `http://localhost:5000${payload.hype_reel_path}`
    status.value = 'complete'
    statusMessage.value = 'Hype reel generated successfully.'
  } catch (error) {
    status.value = 'error'
    statusMessage.value = error.message || 'Unexpected error while generating hype reel.'
  }
}

const formatSeconds = (value) => Number(value).toFixed(3)
</script>

<style scoped>
.video-editor {
  max-width: 800px;
  margin: 2rem auto;
  padding: 1.25rem;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  font-family: Arial, sans-serif;
}

.button-row {
  margin-top: 1rem;
  display: flex;
  gap: 0.75rem;
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

.scene-list,
.result-box {
  margin-top: 1rem;
  padding: 0.75rem;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.success {
  color: #166534;
}

.error {
  color: #b91c1c;
}
</style>
