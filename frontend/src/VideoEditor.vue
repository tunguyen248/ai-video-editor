<template>
  <main class="shell">
    <section class="workspace">
      <header class="masthead">
        <div>
          <p class="eyebrow">AI Video Editor</p>
          <h1>Scene-to-hype reel studio</h1>
        </div>
        <div class="status-pill" :class="status">
          <span class="status-dot"></span>
          {{ statusLabel }}
        </div>
      </header>

      <section
        class="drop-zone"
        :class="{ active: selectedFile, working: isProcessing }"
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="handleFileDrop"
      >
        <input
          id="video-upload"
          type="file"
          accept="video/*"
          @change="handleFileChange"
          :disabled="isProcessing"
        />
        <label for="video-upload" class="upload-target" :class="{ dragging: isDragging }">
          <span class="upload-icon">+</span>
          <span>
            <strong>{{ selectedFile ? selectedFile.name : 'Drop a video or choose a file' }}</strong>
            <small>{{ selectedFileMeta }}</small>
          </span>
        </label>
      </section>

      <section class="controls">
        <div class="whisper-controls">
          <label class="device-select">
            <span>Whisper</span>
            <select v-model="whisperDevice" :disabled="isProcessing">
              <option value="cpu">CPU</option>
              <option value="gpu" :disabled="!gpuAvailable">{{ gpuOptionLabel }}</option>
            </select>
          </label>
          <label class="chunking-toggle" :class="{ disabled: isProcessing }">
            <input v-model="smartChunking" type="checkbox" :disabled="isProcessing" />
            <span>Smart Chunking</span>
          </label>
          <p class="device-hint" :class="{ warning: !gpuAvailable }">
            {{ deviceHint }}
          </p>
          <p class="chunking-hint">
            {{ chunkingHint }}
          </p>
        </div>

        <button @click="detectScenes" :disabled="!selectedFile || isProcessing">
          Detect Scenes
        </button>

        <button class="secondary" @click="generateHypeReel" :disabled="!canGenerate">
          Generate Hype Reel
        </button>

        <button class="tertiary" @click="generateCaptions" :disabled="!canGenerateCaptions">
          Generate Captions
        </button>

        <button class="quaternary" @click="detectKeyMoments" :disabled="!canGenerateCaptions">
          Key Moments
        </button>
      </section>

      <section class="progress-panel" :class="{ active: status !== 'idle' }">
        <div class="progress-copy">
          <div>
            <p class="eyebrow">Status</p>
            <h2>{{ progressTitle }}</h2>
          </div>
          <strong>{{ displayedProgress }}%</strong>
        </div>

        <div class="progress-track">
          <div class="progress-fill" :style="{ width: `${displayedProgress}%` }"></div>
          <span class="progress-glow" :style="{ left: `${displayedProgress}%` }"></span>
        </div>

        <div class="stage-strip">
          <span
            v-for="stage in stages"
            :key="stage.key"
            :class="{ current: currentStage === stage.key, done: stage.done }"
          >
            {{ stage.label }}
          </span>
        </div>

        <p v-if="status === 'error'" class="error">{{ statusMessage }}</p>
        <p v-else class="status-message">{{ statusMessage || 'Ready when you are.' }}</p>
      </section>

      <section v-if="scenes.length > 0" class="timeline-panel">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Detected Scenes</p>
            <h2>{{ scenes.length }} timestamp{{ scenes.length === 1 ? '' : 's' }}</h2>
          </div>
          <span>{{ totalSceneSeconds }}s scanned</span>
        </div>

        <div class="scene-rail">
          <span
            v-for="(scene, index) in timelineScenes"
            :key="`${scene.start}-${scene.end}-${index}`"
            class="scene-block"
            :style="sceneStyle(scene, index)"
            :title="`Scene ${index + 1}: ${formatSeconds(scene.start)}s to ${formatSeconds(scene.end)}s`"
          ></span>
        </div>

        <ol class="scene-list">
          <li v-for="(scene, index) in visibleScenes" :key="`row-${scene.start}-${scene.end}-${index}`">
            <span>Scene {{ index + 1 }}</span>
            <strong>{{ formatSeconds(scene.start) }}s -> {{ formatSeconds(scene.end) }}s</strong>
          </li>
        </ol>
        <p v-if="hiddenSceneCount > 0" class="scene-note">
          Showing the first {{ visibleScenes.length }} scenes. {{ hiddenSceneCount }} more are hidden to keep the editor responsive.
        </p>
      </section>

      <section v-if="downloadUrl" class="result-box">
        <div>
          <p class="eyebrow">Result</p>
          <h2>Hype reel ready</h2>
        </div>
        <a :href="downloadUrl" target="_blank" rel="noopener">Open result</a>
      </section>

      <section v-if="clipUrls.length > 0" class="result-box">
        <div>
          <p class="eyebrow">Clips</p>
          <h2>{{ clipUrls.length }} clip{{ clipUrls.length === 1 ? '' : 's' }} ready</h2>
        </div>
        <div class="result-actions">
          <a
            v-for="(clipUrl, index) in clipUrls"
            :key="clipUrl"
            :href="clipUrl"
            target="_blank"
            rel="noopener"
          >
            Open {{ index + 1 }}
          </a>
        </div>
      </section>

      <section v-if="captionedUrl" class="result-box">
        <div>
          <p class="eyebrow">Captions</p>
          <h2>Captioned video ready</h2>
        </div>
        <div class="result-actions">
          <a :href="captionedUrl" target="_blank" rel="noopener">Open video</a>
          <a v-if="srtUrl" class="quiet-link" :href="srtUrl" target="_blank" rel="noopener">Open SRT</a>
        </div>
      </section>

      <section v-if="keyMoments.length > 0" class="timeline-panel">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Key Moments</p>
            <h2>{{ keyMoments.length }} clip{{ keyMoments.length === 1 ? '' : 's' }}</h2>
          </div>
        </div>

        <ol class="scene-list">
          <li v-for="(moment, index) in keyMoments" :key="`moment-${moment.start}-${index}`">
            <span>{{ formatSeconds(moment.start) }}s -> {{ formatSeconds(moment.end) }}s</span>
            <a v-if="moment.clipUrl" :href="moment.clipUrl" target="_blank" rel="noopener">Open clip</a>
            <strong>{{ moment.score }} pts · {{ moment.reason }}</strong>
          </li>
        </ol>
      </section>
    </section>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const API_BASE = 'http://localhost:5000'

const selectedFile = ref(null)
const videoId = ref('')
const scenes = ref([])
const status = ref('idle') // idle | processing | complete | error
const statusMessage = ref('')
const downloadUrl = ref('')
const clipUrls = ref([])
const captionedUrl = ref('')
const srtUrl = ref('')
const captionSegments = ref([])
const keyMoments = ref([])
const whisperDevice = ref('cpu')
const smartChunking = ref(true)
const whisperCapabilities = ref(null)
const progress = ref(0)
const activeJobType = ref('')
const isDragging = ref(false)
const pollTimer = ref(null)

const isProcessing = computed(() => status.value === 'processing')
const canGenerate = computed(() => Boolean(videoId.value && scenes.value.length > 0 && !isProcessing.value))
const canGenerateCaptions = computed(() => Boolean(selectedFile.value && !isProcessing.value))
const displayedProgress = computed(() => Math.round(progress.value))
const gpuRuntime = computed(() => whisperCapabilities.value?.devices?.gpu ?? null)
const gpuAvailable = computed(() => Boolean(gpuRuntime.value?.available))
const gpuOptionLabel = computed(() => {
  if (!whisperCapabilities.value) return 'GPU (checking...)'
  return gpuAvailable.value ? 'GPU (CUDA)' : 'GPU unavailable'
})
const deviceHint = computed(() => {
  if (!whisperCapabilities.value) {
    return 'Checking whether CUDA acceleration is available on this machine.'
  }
  if (gpuAvailable.value) {
    const names = gpuRuntime.value.device_names || []
    return names.length > 0
      ? `CUDA ready: ${names.join(', ')}`
      : (gpuRuntime.value.reason || 'CUDA is available for Whisper.')
  }
  return gpuRuntime.value?.reason || 'GPU mode is not available right now.'
})
const chunkingHint = computed(() => (
  smartChunking.value
    ? 'Long Whisper runs will split the video into timed chunks for steadier progress updates.'
    : 'Whisper will process the full audio in one pass. This is simpler, but progress updates will be less detailed.'
))
const statusLabel = computed(() => {
  if (status.value === 'processing') return 'Processing'
  if (status.value === 'complete') return 'Complete'
  if (status.value === 'error') return 'Needs attention'
  return 'Idle'
})
const progressTitle = computed(() => {
  if (activeJobType.value === 'scene_analysis') return 'Analyzing scene cuts'
  if (activeJobType.value === 'smart_cut') return 'Building the hype reel'
  if (activeJobType.value === 'captions') return 'Generating burned-in captions'
  if (activeJobType.value === 'key_moments') return 'Detecting key moments'
  if (status.value === 'complete') return 'Ready'
  if (status.value === 'error') return 'Paused'
  return 'Waiting for a video'
})
const currentStage = computed(() => {
  if (status.value === 'error') return 'error'
  if (status.value === 'complete') return 'complete'
  if (activeJobType.value === 'key_moments') {
    if (progress.value >= 88) return 'score'
    if (progress.value >= 74) return 'visual'
    if (progress.value >= 58) return 'transcribe'
    if (progress.value >= 42) return 'model'
    if (progress.value >= 28) return 'peaks'
    return 'extract'
  }
  if (activeJobType.value === 'captions') {
    if (progress.value >= 86) return 'burn'
    if (progress.value >= 74) return 'srt'
    if (progress.value >= 42) return 'transcribe'
    if (progress.value >= 24) return 'model'
    return 'extract'
  }
  if (activeJobType.value === 'smart_cut') return progress.value >= 86 ? 'stitch' : 'render'
  if (activeJobType.value === 'scene_analysis') return progress.value >= 92 ? 'timeline' : 'scan'
  return 'upload'
})
const stages = computed(() => {
  if (activeJobType.value === 'key_moments') {
    const momentOrder = ['extract', 'peaks', 'model', 'transcribe', 'visual', 'score', 'complete']
    const momentIndex = momentOrder.indexOf(currentStage.value)
    return [
      { key: 'extract', label: 'Audio' },
      { key: 'peaks', label: 'Peaks' },
      { key: 'model', label: 'Model' },
      { key: 'transcribe', label: 'Whisper' },
      { key: 'visual', label: 'Scenes' },
      { key: 'score', label: 'Score' },
      { key: 'complete', label: 'Done' },
    ].map((stage, index) => ({
      ...stage,
      done: momentIndex > index || status.value === 'complete',
    }))
  }

  if (activeJobType.value === 'captions') {
    const captionOrder = ['extract', 'model', 'transcribe', 'srt', 'burn', 'complete']
    const captionIndex = captionOrder.indexOf(currentStage.value)
    return [
      { key: 'extract', label: 'Audio' },
      { key: 'model', label: 'Model' },
      { key: 'transcribe', label: 'Whisper' },
      { key: 'srt', label: 'SRT' },
      { key: 'burn', label: 'Burn' },
      { key: 'complete', label: 'Done' },
    ].map((stage, index) => ({
      ...stage,
      done: captionIndex > index || status.value === 'complete',
    }))
  }

  const stageOrder = ['upload', 'scan', 'timeline', 'render', 'stitch', 'complete']
  const activeIndex = stageOrder.indexOf(currentStage.value)
  return [
    { key: 'upload', label: 'Upload' },
    { key: 'scan', label: 'Scan' },
    { key: 'timeline', label: 'Timeline' },
    { key: 'render', label: 'Render' },
    { key: 'stitch', label: 'Stitch' },
    { key: 'complete', label: 'Done' },
  ].map((stage, index) => ({
    ...stage,
    done: activeIndex > index || status.value === 'complete',
  }))
})
const selectedFileMeta = computed(() => {
  if (!selectedFile.value) return 'MP4, MOV, MKV, AVI, WEBM, or M4V'
  return `${(selectedFile.value.size / 1024 / 1024).toFixed(1)} MB`
})
const totalSceneSeconds = computed(() => {
  const lastScene = scenes.value[scenes.value.length - 1]
  return lastScene ? formatSeconds(lastScene.end) : '0.000'
})
const visibleScenes = computed(() => scenes.value.slice(0, 240))
const timelineScenes = computed(() => scenes.value.slice(0, 360))
const hiddenSceneCount = computed(() => Math.max(0, scenes.value.length - visibleScenes.value.length))

onBeforeUnmount(() => clearPollTimer())

const clearPollTimer = () => {
  if (pollTimer.value) {
    window.clearTimeout(pollTimer.value)
    pollTimer.value = null
  }
}

const resetJobState = () => {
  clearPollTimer()
  progress.value = 0
  activeJobType.value = ''
  statusMessage.value = ''
}

const handleFileChange = (event) => {
  setSelectedFile(event.target.files?.[0] ?? null)
}

const handleFileDrop = (event) => {
  isDragging.value = false
  if (isProcessing.value) return
  setSelectedFile(event.dataTransfer.files?.[0] ?? null)
}

const setSelectedFile = (file) => {
  selectedFile.value = file
  videoId.value = ''
  scenes.value = []
  downloadUrl.value = ''
  clipUrls.value = []
  captionedUrl.value = ''
  srtUrl.value = ''
  captionSegments.value = []
  keyMoments.value = []
  status.value = 'idle'
  resetJobState()
}

const detectScenes = async () => {
  if (!selectedFile.value) {
    setError('Please select a video file first.')
    return
  }

  status.value = 'processing'
  activeJobType.value = 'scene_analysis'
  progress.value = 2
  statusMessage.value = 'Uploading video'
  downloadUrl.value = ''
  clipUrls.value = []
  scenes.value = []

  const formData = new FormData()
  formData.append('video', selectedFile.value)

  try {
    const payload = await startRequest('/analyze_scenes', {
      method: 'POST',
      body: formData,
    })

    await waitForJob(payload.job_id, (result) => {
      videoId.value = result.video_id
      scenes.value = Array.isArray(result.scenes) ? result.scenes : []
      status.value = 'complete'
      activeJobType.value = ''
      progress.value = 100
      statusMessage.value = `Detected ${scenes.value.length} scene(s).`
    })
  } catch (error) {
    setError(error.message || 'Unexpected error while detecting scenes.')
  }
}

const detectKeyMoments = async () => {
  if (!selectedFile.value) {
    setError('Please select a video file first.')
    return
  }

  status.value = 'processing'
  activeJobType.value = 'key_moments'
  progress.value = 4
  statusMessage.value = `Uploading video for key moment detection on ${whisperDevice.value.toUpperCase()}${smartChunking.value ? ' with smart chunking' : ''}`
  keyMoments.value = []
  clipUrls.value = []

  const formData = new FormData()
  formData.append('video', selectedFile.value)
  formData.append('device', whisperDevice.value)
  formData.append('use_chunking', String(smartChunking.value))

  try {
    const payload = await startRequest('/detect_key_moments', {
      method: 'POST',
      body: formData,
    })

    await waitForJob(payload.job_id, (result) => {
      keyMoments.value = Array.isArray(result.moments)
        ? result.moments.map((moment) => ({
            ...moment,
            clipUrl: moment.clip_path ? `${API_BASE}${moment.clip_path}` : '',
          }))
        : []
      clipUrls.value = Array.isArray(result.clip_paths)
        ? result.clip_paths.map((path) => `${API_BASE}${path}`)
        : keyMoments.value.map((moment) => moment.clipUrl).filter(Boolean)
      status.value = 'complete'
      activeJobType.value = ''
      progress.value = 100
      statusMessage.value = `Detected ${keyMoments.value.length} key moment(s) and generated ${clipUrls.value.length} clip(s).`
    })
  } catch (error) {
    setError(error.message || 'Unexpected error while detecting key moments.')
  }
}

const generateHypeReel = async () => {
  if (!videoId.value || scenes.value.length === 0) {
    setError('Detect scenes first before generating the hype reel.')
    return
  }

  status.value = 'processing'
  activeJobType.value = 'smart_cut'
  progress.value = 3
  statusMessage.value = 'Starting render'
  downloadUrl.value = ''
  clipUrls.value = []

  try {
    const payload = await startRequest('/smart_cut', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        video_id: videoId.value,
        scenes: scenes.value,
      }),
    })

    await waitForJob(payload.job_id, (result) => {
      clipUrls.value = Array.isArray(result.clip_paths)
        ? result.clip_paths.map((path) => `${API_BASE}${path}`)
        : []
      downloadUrl.value = result.hype_reel_path ? `${API_BASE}${result.hype_reel_path}` : ''
      status.value = 'complete'
      activeJobType.value = ''
      progress.value = 100
      statusMessage.value = `Generated ${clipUrls.value.length || 1} hype clip(s).`
    })
  } catch (error) {
    setError(error.message || 'Unexpected error while generating hype reel.')
  }
}

const generateCaptions = async () => {
  if (!selectedFile.value) {
    setError('Please select a video file first.')
    return
  }

  status.value = 'processing'
  activeJobType.value = 'captions'
  progress.value = 4
  statusMessage.value = `Uploading video for captions on ${whisperDevice.value.toUpperCase()}${smartChunking.value ? ' with smart chunking' : ''}`
  captionedUrl.value = ''
  srtUrl.value = ''
  captionSegments.value = []

  const formData = new FormData()
  formData.append('video', selectedFile.value)
  formData.append('device', whisperDevice.value)
  formData.append('use_chunking', String(smartChunking.value))

  try {
    const payload = await startRequest('/generate_captions', {
      method: 'POST',
      body: formData,
    })

    await waitForJob(payload.job_id, (result) => {
      captionedUrl.value = `${API_BASE}${result.captioned_video_path}`
      srtUrl.value = `${API_BASE}${result.srt_path}`
      captionSegments.value = Array.isArray(result.segments) ? result.segments : []
      status.value = 'complete'
      activeJobType.value = ''
      progress.value = 100
      statusMessage.value = `Generated ${captionSegments.value.length} caption segment(s).`
    })
  } catch (error) {
    setError(error.message || 'Unexpected error while generating captions.')
  }
}

const startRequest = async (path, options) => {
  const response = await fetch(`${API_BASE}${path}`, options)
  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload.error || 'Request failed.')
  }
  return payload
}

const loadWhisperCapabilities = async () => {
  try {
    const response = await fetch(`${API_BASE}/whisper_capabilities`)
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.error || 'Capability check failed.')
    whisperCapabilities.value = payload
    if (!payload.devices?.gpu?.available && whisperDevice.value === 'gpu') {
      whisperDevice.value = 'cpu'
    }
  } catch (error) {
    whisperCapabilities.value = {
      devices: {
        gpu: {
          available: false,
          reason: error.message || 'Unable to verify CUDA availability.',
          device_names: [],
        },
      },
    }
    whisperDevice.value = 'cpu'
  }
}

const waitForJob = (jobId, onComplete) => new Promise((resolve, reject) => {
  const poll = async () => {
    try {
      const response = await fetch(`${API_BASE}/job_status/${jobId}`)
      const job = await response.json()
      if (!response.ok) throw new Error(job.error || 'Could not read job status.')

      progress.value = Number(job.progress ?? progress.value)
      statusMessage.value = job.message || statusMessage.value

      if (job.state === 'complete') {
        clearPollTimer()
        onComplete(job.result || {})
        resolve(job.result || {})
        return
      }

      if (job.state === 'error') {
        clearPollTimer()
        reject(new Error(job.error || job.message || 'Processing failed.'))
        return
      }

      pollTimer.value = window.setTimeout(poll, 450)
    } catch (error) {
      clearPollTimer()
      reject(error)
    }
  }

  poll()
})

const setError = (message) => {
  status.value = 'error'
  activeJobType.value = ''
  progress.value = 100
  statusMessage.value = message
}

const sceneStyle = (scene, index) => {
  const total = Number(scenes.value[scenes.value.length - 1]?.end || 1)
  const start = Math.max(0, (Number(scene.start) / total) * 100)
  const width = Math.max(1.5, ((Number(scene.end) - Number(scene.start)) / total) * 100)
  return {
    left: `${start}%`,
    width: `${Math.min(width, 100 - start)}%`,
    animationDelay: `${index * 45}ms`,
  }
}

const formatSeconds = (value) => Number(value).toFixed(3)

onMounted(() => {
  loadWhisperCapabilities()
})
</script>

<style scoped>
:global(*) {
  box-sizing: border-box;
}

:global(body) {
  margin: 0;
  background: #0f172a;
  color: #e5e7eb;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.shell {
  min-height: 100vh;
  padding: 32px;
  background:
    radial-gradient(circle at top left, rgba(20, 184, 166, 0.18), transparent 34%),
    linear-gradient(135deg, #101828 0%, #111827 48%, #172033 100%);
}

.workspace {
  width: min(1040px, 100%);
  margin: 0 auto;
  display: grid;
  gap: 18px;
}

.masthead,
.controls,
.progress-panel,
.timeline-panel,
.result-box,
.drop-zone {
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: rgba(15, 23, 42, 0.74);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.24);
  backdrop-filter: blur(18px);
}

.masthead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 28px;
  border-radius: 8px;
}

.eyebrow {
  margin: 0 0 6px;
  color: #5eead4;
  font-size: 0.73rem;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}

h1,
h2 {
  margin: 0;
  letter-spacing: 0;
}

h1 {
  font-size: clamp(2rem, 7vw, 4.5rem);
  line-height: 0.98;
}

h2 {
  font-size: 1.25rem;
}

.status-pill {
  min-width: 128px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 10px 14px;
  border-radius: 999px;
  background: rgba(30, 41, 59, 0.95);
  color: #cbd5e1;
  font-weight: 800;
}

.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: #94a3b8;
}

.status-pill.processing .status-dot {
  background: #22c55e;
  box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.55);
  animation: pulse 1.1s infinite;
}

.status-pill.complete .status-dot {
  background: #5eead4;
}

.status-pill.error .status-dot {
  background: #fb7185;
}

.drop-zone {
  border-radius: 8px;
  padding: 16px;
  transition: transform 180ms ease, border-color 180ms ease;
}

.drop-zone.working {
  border-color: rgba(94, 234, 212, 0.55);
}

input[type="file"] {
  position: absolute;
  inline-size: 1px;
  block-size: 1px;
  opacity: 0;
  pointer-events: none;
}

.upload-target {
  min-height: 116px;
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 20px;
  border: 1px dashed rgba(148, 163, 184, 0.44);
  border-radius: 8px;
  cursor: pointer;
  transition: background 180ms ease, border-color 180ms ease, transform 180ms ease;
}

.upload-target.dragging,
.upload-target:hover {
  border-color: #5eead4;
  background: rgba(20, 184, 166, 0.08);
  transform: translateY(-1px);
}

.upload-icon {
  width: 52px;
  height: 52px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: #14b8a6;
  color: #052e2b;
  font-size: 2rem;
  font-weight: 800;
}

.upload-target strong,
.upload-target small {
  display: block;
}

.upload-target strong {
  max-width: 72vw;
  overflow-wrap: anywhere;
  font-size: 1rem;
}

.upload-target small {
  margin-top: 5px;
  color: #94a3b8;
}

.controls {
  display: flex;
  gap: 12px;
  padding: 16px;
  border-radius: 8px;
}

button,
.result-box a {
  min-height: 44px;
  padding: 0 18px;
  border: 0;
  border-radius: 8px;
  background: #2dd4bf;
  color: #042f2e;
  font: inherit;
  font-weight: 900;
  cursor: pointer;
  text-decoration: none;
  transition: transform 160ms ease, opacity 160ms ease, background 160ms ease;
}

button:hover,
.result-box a:hover {
  transform: translateY(-1px);
}

button.secondary {
  background: #f59e0b;
  color: #271806;
}

button.tertiary {
  background: #a3e635;
  color: #1a2e05;
}

button.quaternary {
  background: #38bdf8;
  color: #082f49;
}

.device-select {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  gap: 9px;
  padding: 0 12px;
  border-radius: 8px;
  background: rgba(30, 41, 59, 0.8);
  color: #cbd5e1;
  font-weight: 800;
}

.whisper-controls {
  display: grid;
  gap: 8px;
}

.chunking-toggle {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 0 12px;
  border-radius: 8px;
  background: rgba(30, 41, 59, 0.8);
  color: #cbd5e1;
  font-weight: 800;
}

.chunking-toggle.disabled {
  opacity: 0.6;
}

.chunking-toggle input {
  width: 16px;
  height: 16px;
  accent-color: #14b8a6;
}

.device-hint {
  margin: 0;
  color: #94a3b8;
  font-size: 0.82rem;
}

.chunking-hint {
  margin: 0;
  color: #94a3b8;
  font-size: 0.82rem;
}

.device-hint.warning {
  color: #fbbf24;
}

.device-select span {
  font-size: 0.78rem;
  text-transform: uppercase;
}

.device-select select {
  min-height: 30px;
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 6px;
  background: #0f172a;
  color: #f8fafc;
  font: inherit;
  font-weight: 800;
}

button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  transform: none;
}

.progress-panel,
.timeline-panel,
.result-box {
  padding: 22px;
  border-radius: 8px;
}

.progress-panel {
  position: relative;
  overflow: hidden;
}

.progress-panel.active::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(110deg, transparent 0%, rgba(94, 234, 212, 0.09) 48%, transparent 58%);
  transform: translateX(-100%);
  animation: sweep 2.2s infinite;
}

.progress-copy,
.section-heading,
.result-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.progress-copy {
  position: relative;
  z-index: 1;
}

.progress-copy strong {
  font-size: 2rem;
  color: #f8fafc;
}

.progress-track {
  position: relative;
  height: 14px;
  margin: 18px 0;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(51, 65, 85, 0.9);
}

.progress-fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #14b8a6, #a3e635, #f59e0b);
  transition: width 380ms ease;
}

.progress-glow {
  position: absolute;
  top: 50%;
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background: rgba(250, 204, 21, 0.68);
  filter: blur(10px);
  transform: translate(-50%, -50%);
  transition: left 380ms ease;
}

.stage-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
}

.stage-strip span {
  min-height: 34px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: rgba(30, 41, 59, 0.8);
  color: #94a3b8;
  font-size: 0.76rem;
  font-weight: 800;
}

.stage-strip span.current {
  background: rgba(20, 184, 166, 0.26);
  color: #ccfbf1;
}

.stage-strip span.done {
  background: rgba(132, 204, 22, 0.22);
  color: #ecfccb;
}

.status-message,
.error {
  margin: 14px 0 0;
  color: #cbd5e1;
}

.error {
  color: #fecdd3;
}

.section-heading span {
  color: #94a3b8;
  font-weight: 800;
}

.scene-rail {
  position: relative;
  height: 54px;
  margin: 20px 0;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.95);
  overflow: hidden;
}

.scene-block {
  position: absolute;
  top: 9px;
  bottom: 9px;
  border-radius: 6px;
  background: linear-gradient(135deg, #2dd4bf, #a3e635);
  box-shadow: 0 0 18px rgba(45, 212, 191, 0.25);
  animation: riseIn 420ms both ease;
}

.scene-list {
  max-height: 260px;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
  overflow: auto;
  list-style: none;
}

.scene-note {
  margin: 12px 0 0;
  color: #94a3b8;
  font-size: 0.9rem;
}

.scene-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 42px;
  padding: 0 12px;
  border-radius: 8px;
  background: rgba(30, 41, 59, 0.66);
}

.scene-list span {
  color: #94a3b8;
}

.scene-list strong {
  font-variant-numeric: tabular-nums;
}

.scene-list a {
  color: #5eead4;
  font-weight: 800;
  text-decoration: none;
}

.scene-list a:hover {
  color: #99f6e4;
}

.result-box a {
  display: inline-grid;
  place-items: center;
}

.result-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.result-actions .quiet-link {
  background: rgba(148, 163, 184, 0.18);
  color: #e5e7eb;
}

@keyframes pulse {
  70% {
    box-shadow: 0 0 0 12px rgba(34, 197, 94, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(34, 197, 94, 0);
  }
}

@keyframes sweep {
  to {
    transform: translateX(100%);
  }
}

@keyframes riseIn {
  from {
    opacity: 0;
    transform: translateY(14px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 720px) {
  .shell {
    padding: 14px;
  }

  .masthead,
  .controls,
  .progress-copy,
  .section-heading,
  .result-box {
    align-items: stretch;
    flex-direction: column;
  }

  .controls {
    display: grid;
  }

  .stage-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .scene-list li {
    align-items: flex-start;
    flex-direction: column;
    padding: 10px 12px;
  }
}
</style>
