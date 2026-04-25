<template>
  <div class="app">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-logo">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
          <rect width="28" height="28" rx="8" fill="#E8FF47"/>
          <path d="M8 10l6 4-6 4V10z" fill="#0A0A0A"/>
          <rect x="16" y="10" width="4" height="8" rx="1" fill="#0A0A0A"/>
        </svg>
        <span class="logo-text">Reel</span>
      </div>

      <nav class="sidebar-nav">
        <button
          v-for="tool in tools"
          :key="tool.id"
          class="nav-item"
          :class="{ active: activeTool === tool.id }"
          @click="activeTool = tool.id"
          :title="tool.label"
        >
          <span class="nav-icon" v-html="tool.icon"></span>
          <span class="nav-label">{{ tool.label }}</span>
        </button>
      </nav>

      <div class="sidebar-bottom">
        <div class="whisper-section">
          <p class="section-label">Whisper</p>
          <div class="toggle-row">
            <button
              class="device-btn"
              :class="{ active: whisperDevice === 'cpu' }"
              @click="whisperDevice = 'cpu'"
              :disabled="isProcessing"
            >CPU</button>
            <button
              class="device-btn"
              :class="{ active: whisperDevice === 'gpu', unavailable: !gpuAvailable }"
              @click="gpuAvailable && (whisperDevice = 'gpu')"
              :disabled="isProcessing || !gpuAvailable"
            >GPU</button>
          </div>
          <label class="chunk-toggle">
            <input type="checkbox" v-model="smartChunking" :disabled="isProcessing" />
            <span class="toggle-track"><span class="toggle-thumb"></span></span>
            <span>Smart chunks</span>
          </label>
          <p class="hint-text" :class="{ warn: !gpuAvailable && whisperDevice === 'gpu' }">
            {{ gpuAvailable ? 'CUDA ready' : 'CPU only' }}
          </p>
        </div>
      </div>
    </aside>

    <!-- Main -->
    <main class="main">
      <!-- Top bar -->
      <header class="topbar">
        <div class="topbar-left">
          <span class="breadcrumb">
            {{ selectedFile ? selectedFile.name : 'No file selected' }}
          </span>
          <span class="status-badge" :class="status">
            <span class="badge-dot"></span>
            {{ statusLabel }}
          </span>
        </div>
        <div class="topbar-actions">
          <button class="action-btn primary" @click="detectScenes" :disabled="!selectedFile || isProcessing">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 7h10M7 2l5 5-5 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            Detect Scenes
          </button>
          <button class="action-btn" @click="generateHypeReel" :disabled="!canGenerate">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M4 2l8 5-8 5V2z" fill="currentColor"/></svg>
            Hype Reel
          </button>
          <button class="action-btn" @click="generateCaptions" :disabled="!canGenerateCaptions">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="1" y="4" width="12" height="6" rx="1.5" stroke="currentColor" stroke-width="1.5"/><path d="M4 7h2M7 7h3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
            Captions
          </button>
          <button class="action-btn accent" @click="detectKeyMoments" :disabled="!canGenerateCaptions">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1l1.5 4H13l-3.5 2.5 1.5 4L7 9l-4 2.5 1.5-4L1 5h4.5z" fill="currentColor"/></svg>
            Key Moments
          </button>
        </div>
      </header>

      <div class="canvas">
        <!-- Upload zone -->
        <div
          class="upload-zone"
          :class="{ 'has-file': selectedFile, dragging: isDragging, processing: isProcessing }"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="handleFileDrop"
        >
          <input id="video-upload" type="file" accept="video/*" @change="handleFileChange" :disabled="isProcessing" />
          <label for="video-upload" class="upload-inner">
            <div class="upload-graphic">
              <div class="upload-ring">
                <svg v-if="!selectedFile" width="32" height="32" viewBox="0 0 32 32" fill="none">
                  <path d="M16 6v14M10 14l6-8 6 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                  <path d="M6 24h20" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
                <svg v-else width="32" height="32" viewBox="0 0 32 32" fill="none">
                  <path d="M10 16l4 4 8-8" stroke="#E8FF47" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </div>
            </div>
            <div class="upload-copy">
              <p class="upload-title">{{ selectedFile ? selectedFile.name : 'Drop your video here' }}</p>
              <p class="upload-sub">{{ selectedFile ? formatFileSize(selectedFile.size) : 'MP4, MOV, MKV, AVI, WEBM up to 2GB' }}</p>
            </div>
          </label>
        </div>

        <!-- Progress -->
        <div class="progress-card" :class="{ visible: status !== 'idle' }">
          <div class="progress-header">
            <div>
              <p class="card-label">{{ progressTitle }}</p>
              <p class="progress-message">{{ statusMessage || 'Waiting…' }}</p>
            </div>
            <span class="progress-pct">{{ displayedProgress }}<em>%</em></span>
          </div>
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: displayedProgress + '%' }"></div>
          </div>
          <div class="stage-pills">
            <span
              v-for="stage in stages"
              :key="stage.key"
              class="pill"
              :class="{ current: currentStage === stage.key, done: stage.done }"
            >{{ stage.label }}</span>
          </div>
          <p v-if="status === 'error'" class="error-msg">{{ statusMessage }}</p>
        </div>

        <!-- Two-column results -->
        <div class="results-grid">
          <!-- Video preview -->
          <div class="result-card player-card" v-if="activeVideoUrl">
            <div class="card-head">
              <span class="card-label">Preview</span>
              <span class="card-title">{{ activeVideoTitle }}</span>
            </div>
            <video :key="activeVideoUrl" :src="activeVideoUrl" controls autoplay playsinline class="video-el"></video>
          </div>

          <!-- Scenes timeline -->
          <div class="result-card" v-if="scenes.length > 0">
            <div class="card-head">
              <span class="card-label">Detected Scenes</span>
              <span class="card-title">{{ scenes.length }} cuts · {{ totalSceneSeconds }}s</span>
            </div>
            <div class="timeline-bar">
              <span
                v-for="(scene, i) in timelineScenes"
                :key="i"
                class="timeline-seg"
                :style="sceneStyle(scene, i)"
                :title="`${formatSeconds(scene.start)}s → ${formatSeconds(scene.end)}s`"
              ></span>
            </div>
            <ol class="scene-list">
              <li v-for="(scene, i) in visibleScenes" :key="i">
                <span class="scene-num">{{ String(i + 1).padStart(2, '0') }}</span>
                <span class="scene-range">{{ formatSeconds(scene.start) }}s → {{ formatSeconds(scene.end) }}s</span>
                <span class="scene-dur">{{ (scene.end - scene.start).toFixed(1) }}s</span>
              </li>
            </ol>
            <p v-if="hiddenSceneCount > 0" class="overflow-note">+{{ hiddenSceneCount }} more scenes not shown</p>
          </div>

          <!-- Hype reel result -->
          <div class="result-card output-card" v-if="downloadUrl || clipUrls.length > 0">
            <div class="card-head">
              <span class="card-label">Output</span>
              <span class="card-title">{{ clipUrls.length > 1 ? `${clipUrls.length} clips` : 'Hype reel' }}</span>
            </div>
            <div class="output-actions">
              <button v-if="downloadUrl" class="out-btn" @click="playVideo(downloadUrl, 'Hype reel')">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M3 2l7 4-7 4V2z" fill="currentColor"/></svg>
                Play reel
              </button>
              <button
                v-for="(url, i) in clipUrls.slice(0, 8)"
                :key="url"
                class="out-btn secondary"
                @click="playVideo(url, `Clip ${i + 1}`)"
              >Clip {{ i + 1 }}</button>
            </div>
          </div>

          <!-- Captions result -->
          <div class="result-card output-card" v-if="captionedUrl">
            <div class="card-head">
              <span class="card-label">Captions</span>
              <span class="card-title">{{ captionSegments.length }} segments</span>
            </div>
            <div class="output-actions">
              <button class="out-btn" @click="playVideo(captionedUrl, 'Captioned video')">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M3 2l7 4-7 4V2z" fill="currentColor"/></svg>
                Play captioned
              </button>
              <a v-if="srtUrl" class="out-btn secondary" :href="srtUrl" target="_blank">Download SRT</a>
            </div>
          </div>

          <!-- Key moments -->
          <div class="result-card moments-card" v-if="keyMoments.length > 0">
            <div class="card-head">
              <span class="card-label">Key Moments</span>
              <span class="card-title">{{ keyMoments.length }} detected</span>
            </div>
            <ol class="moments-list">
              <li v-for="(m, i) in keyMoments" :key="i">
                <div class="moment-meta">
                  <span class="moment-time">{{ formatSeconds(m.start) }}s – {{ formatSeconds(m.end) }}s</span>
                  <span class="moment-score">{{ m.score }} pts</span>
                </div>
                <p class="moment-reason">{{ m.reason }}</p>
                <button v-if="m.clipUrl" class="out-btn small" @click="playVideo(m.clipUrl, `Moment ${i+1}`)">Watch clip</button>
              </li>
            </ol>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const API_BASE = 'http://localhost:5000'

const selectedFile = ref(null)
const videoId = ref('')
const scenes = ref([])
const status = ref('idle')
const statusMessage = ref('')
const downloadUrl = ref('')
const clipUrls = ref([])
const activeVideoUrl = ref('')
const activeVideoTitle = ref('Preview')
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
const activeTool = ref('scenes')

const tools = [
  {
    id: 'scenes',
    label: 'Scenes',
    icon: '<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><rect x="1" y="4" width="16" height="10" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M6 4v10" stroke="currentColor" stroke-width="1.5"/><path d="M12 4v10" stroke="currentColor" stroke-width="1.5"/></svg>'
  },
  {
    id: 'moments',
    label: 'Moments',
    icon: '<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M9 2l1.8 5H16l-4 2.9 1.6 5L9 11.5l-4.6 3.4 1.6-5L2 7h5.2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>'
  },
  {
    id: 'captions',
    label: 'Captions',
    icon: '<svg width="18" height="18" viewBox="0 0 18 18" fill="none"><rect x="2" y="5" width="14" height="8" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M5 9h4M5 11.5h8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>'
  }
]

const isProcessing = computed(() => status.value === 'processing')
const canGenerate = computed(() => Boolean(videoId.value && scenes.value.length > 0 && !isProcessing.value))
const canGenerateCaptions = computed(() => Boolean(selectedFile.value && !isProcessing.value))
const displayedProgress = computed(() => Math.round(progress.value))
const gpuAvailable = computed(() => Boolean(whisperCapabilities.value?.devices?.gpu?.available))

const statusLabel = computed(() => ({
  processing: 'Processing',
  complete: 'Complete',
  error: 'Error',
  idle: 'Ready'
}[status.value] || 'Ready'))

const progressTitle = computed(() => {
  const map = {
    scene_analysis: 'Analyzing scene cuts',
    smart_cut: 'Building hype reel',
    captions: 'Generating captions',
    key_moments: 'Detecting key moments'
  }
  return map[activeJobType.value] || (status.value === 'complete' ? 'Complete' : 'Idle')
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
    const order = ['extract','peaks','model','transcribe','visual','score','complete']
    const idx = order.indexOf(currentStage.value)
    return [
      { key: 'extract', label: 'Audio' },
      { key: 'peaks', label: 'Peaks' },
      { key: 'model', label: 'Model' },
      { key: 'transcribe', label: 'Whisper' },
      { key: 'visual', label: 'Scenes' },
      { key: 'score', label: 'Score' },
      { key: 'complete', label: 'Done' },
    ].map((s, i) => ({ ...s, done: idx > i || status.value === 'complete' }))
  }
  if (activeJobType.value === 'captions') {
    const order = ['extract','model','transcribe','srt','burn','complete']
    const idx = order.indexOf(currentStage.value)
    return [
      { key: 'extract', label: 'Audio' },
      { key: 'model', label: 'Model' },
      { key: 'transcribe', label: 'Whisper' },
      { key: 'srt', label: 'SRT' },
      { key: 'burn', label: 'Burn' },
      { key: 'complete', label: 'Done' },
    ].map((s, i) => ({ ...s, done: idx > i || status.value === 'complete' }))
  }
  const order = ['upload','scan','timeline','render','stitch','complete']
  const idx = order.indexOf(currentStage.value)
  return [
    { key: 'upload', label: 'Upload' },
    { key: 'scan', label: 'Scan' },
    { key: 'timeline', label: 'Timeline' },
    { key: 'render', label: 'Render' },
    { key: 'stitch', label: 'Stitch' },
    { key: 'complete', label: 'Done' },
  ].map((s, i) => ({ ...s, done: idx > i || status.value === 'complete' }))
})

const totalSceneSeconds = computed(() => {
  const last = scenes.value[scenes.value.length - 1]
  return last ? formatSeconds(last.end) : '0.000'
})
const visibleScenes = computed(() => scenes.value.slice(0, 200))
const timelineScenes = computed(() => scenes.value.slice(0, 360))
const hiddenSceneCount = computed(() => Math.max(0, scenes.value.length - visibleScenes.value.length))

const formatSeconds = v => Number(v).toFixed(3)
const formatFileSize = bytes => {
  if (bytes >= 1024 * 1024 * 1024) return (bytes / 1024 / 1024 / 1024).toFixed(1) + ' GB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

onBeforeUnmount(() => clearPollTimer())

const clearPollTimer = () => {
  if (pollTimer.value) { window.clearTimeout(pollTimer.value); pollTimer.value = null }
}
const resetJobState = () => { clearPollTimer(); progress.value = 0; activeJobType.value = ''; statusMessage.value = '' }

const handleFileChange = e => setSelectedFile(e.target.files?.[0] ?? null)
const handleFileDrop = e => { isDragging.value = false; if (!isProcessing.value) setSelectedFile(e.dataTransfer.files?.[0] ?? null) }

const setSelectedFile = file => {
  selectedFile.value = file
  videoId.value = ''; scenes.value = []; downloadUrl.value = ''; clipUrls.value = []
  activeVideoUrl.value = ''; activeVideoTitle.value = 'Preview'; captionedUrl.value = ''
  srtUrl.value = ''; captionSegments.value = []; keyMoments.value = []
  status.value = 'idle'; resetJobState()
}

const detectScenes = async () => {
  if (!selectedFile.value) return setError('Select a video first.')
  status.value = 'processing'; activeJobType.value = 'scene_analysis'; progress.value = 2
  statusMessage.value = 'Uploading video'; scenes.value = []
  const fd = new FormData(); fd.append('video', selectedFile.value)
  try {
    const payload = await startRequest('/analyze_scenes', { method: 'POST', body: fd })
    await waitForJob(payload.job_id, result => {
      videoId.value = result.video_id
      scenes.value = Array.isArray(result.scenes) ? result.scenes : []
      status.value = 'complete'; activeJobType.value = ''; progress.value = 100
      statusMessage.value = `Detected ${scenes.value.length} scene(s).`
    })
  } catch (e) { setError(e.message || 'Scene detection failed.') }
}

const generateHypeReel = async () => {
  if (!videoId.value || !scenes.value.length) return setError('Detect scenes first.')
  status.value = 'processing'; activeJobType.value = 'smart_cut'; progress.value = 3
  statusMessage.value = 'Starting render'; downloadUrl.value = ''; clipUrls.value = []
  try {
    const payload = await startRequest('/smart_cut', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ video_id: videoId.value, scenes: scenes.value }) })
    await waitForJob(payload.job_id, result => {
      clipUrls.value = Array.isArray(result.clip_paths) ? result.clip_paths.map(p => `${API_BASE}${p}`) : []
      downloadUrl.value = result.hype_reel_path ? `${API_BASE}${result.hype_reel_path}` : ''
      status.value = 'complete'; activeJobType.value = ''; progress.value = 100
      statusMessage.value = `Generated ${clipUrls.value.length || 1} clip(s).`
    })
  } catch (e) { setError(e.message || 'Hype reel failed.') }
}

const generateCaptions = async () => {
  if (!selectedFile.value) return setError('Select a video first.')
  status.value = 'processing'; activeJobType.value = 'captions'; progress.value = 4
  statusMessage.value = 'Uploading for captions'; captionedUrl.value = ''; srtUrl.value = ''; captionSegments.value = []
  const fd = new FormData(); fd.append('video', selectedFile.value); fd.append('device', whisperDevice.value); fd.append('use_chunking', String(smartChunking.value))
  try {
    const payload = await startRequest('/generate_captions', { method: 'POST', body: fd })
    await waitForJob(payload.job_id, result => {
      captionedUrl.value = `${API_BASE}${result.captioned_video_path}`
      srtUrl.value = `${API_BASE}${result.srt_path}`
      captionSegments.value = Array.isArray(result.segments) ? result.segments : []
      status.value = 'complete'; activeJobType.value = ''; progress.value = 100
      statusMessage.value = `Generated ${captionSegments.value.length} segment(s).`
    })
  } catch (e) { setError(e.message || 'Caption generation failed.') }
}

const detectKeyMoments = async () => {
  if (!selectedFile.value) return setError('Select a video first.')
  status.value = 'processing'; activeJobType.value = 'key_moments'; progress.value = 4
  statusMessage.value = 'Uploading for key moment detection'; keyMoments.value = []; clipUrls.value = []
  const fd = new FormData(); fd.append('video', selectedFile.value); fd.append('device', whisperDevice.value); fd.append('use_chunking', String(smartChunking.value))
  try {
    const payload = await startRequest('/detect_key_moments', { method: 'POST', body: fd })
    await waitForJob(payload.job_id, result => {
      keyMoments.value = Array.isArray(result.moments) ? result.moments.map(m => ({ ...m, clipUrl: m.clip_path ? `${API_BASE}${m.clip_path}` : '' })) : []
      clipUrls.value = Array.isArray(result.clip_paths) ? result.clip_paths.map(p => `${API_BASE}${p}`) : keyMoments.value.map(m => m.clipUrl).filter(Boolean)
      status.value = 'complete'; activeJobType.value = ''; progress.value = 100
      statusMessage.value = `Detected ${keyMoments.value.length} moment(s).`
    })
  } catch (e) { setError(e.message || 'Key moment detection failed.') }
}

const startRequest = async (path, opts) => {
  const res = await fetch(`${API_BASE}${path}`, opts)
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || 'Request failed.')
  return data
}

const playVideo = (url, title = 'Preview') => { if (url) { activeVideoUrl.value = url; activeVideoTitle.value = title } }

const loadWhisperCapabilities = async () => {
  try {
    const res = await fetch(`${API_BASE}/whisper_capabilities`)
    const data = await res.json()
    whisperCapabilities.value = data
    if (!data.devices?.gpu?.available && whisperDevice.value === 'gpu') whisperDevice.value = 'cpu'
  } catch {
    whisperCapabilities.value = { devices: { gpu: { available: false } } }
  }
}

const waitForJob = (jobId, onComplete) => new Promise((resolve, reject) => {
  const poll = async () => {
    try {
      const res = await fetch(`${API_BASE}/job_status/${jobId}`)
      const job = await res.json()
      if (!res.ok) throw new Error(job.error || 'Status check failed.')
      progress.value = Number(job.progress ?? progress.value)
      statusMessage.value = job.message || statusMessage.value
      if (job.state === 'complete') { clearPollTimer(); onComplete(job.result || {}); resolve(job.result || {}); return }
      if (job.state === 'error') { clearPollTimer(); reject(new Error(job.error || job.message || 'Processing failed.')); return }
      pollTimer.value = window.setTimeout(poll, 450)
    } catch (e) { clearPollTimer(); reject(e) }
  }
  poll()
})

const setError = msg => { status.value = 'error'; activeJobType.value = ''; progress.value = 100; statusMessage.value = msg }

const sceneStyle = (scene, i) => {
  const total = Number(scenes.value[scenes.value.length - 1]?.end || 1)
  const start = Math.max(0, (Number(scene.start) / total) * 100)
  const width = Math.max(0.5, ((Number(scene.end) - Number(scene.start)) / total) * 100)
  return { left: `${start}%`, width: `${Math.min(width, 100 - start)}%`, animationDelay: `${i * 20}ms` }
}

onMounted(loadWhisperCapabilities)
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,300&family=DM+Mono:wght@400;500&display=swap');

:global(*) { box-sizing: border-box; margin: 0; padding: 0; }

:global(body) {
  background: #F5F4F0;
  color: #1A1A1A;
  font-family: 'DM Sans', sans-serif;
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

/* ── Layout ── */
.app {
  display: flex;
  min-height: 100vh;
}

/* ── Sidebar ── */
.sidebar {
  width: 200px;
  flex-shrink: 0;
  background: #1A1A1A;
  display: flex;
  flex-direction: column;
  padding: 20px 0;
  position: sticky;
  top: 0;
  height: 100vh;
}

.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 20px 24px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}

.logo-text {
  font-size: 18px;
  font-weight: 600;
  color: #FFFFFF;
  letter-spacing: -0.3px;
}

.sidebar-nav {
  flex: 1;
  padding: 16px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: none;
  background: transparent;
  color: rgba(255,255,255,0.45);
  border-radius: 8px;
  cursor: pointer;
  text-align: left;
  width: 100%;
  font-family: inherit;
  font-size: 13.5px;
  font-weight: 500;
  transition: background 150ms, color 150ms;
}

.nav-item:hover { background: rgba(255,255,255,0.07); color: rgba(255,255,255,0.75); }
.nav-item.active { background: rgba(232,255,71,0.15); color: #E8FF47; }
.nav-icon { flex-shrink: 0; opacity: 0.8; }
.nav-item.active .nav-icon { opacity: 1; }

.sidebar-bottom {
  padding: 16px;
  border-top: 1px solid rgba(255,255,255,0.08);
}

.section-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(255,255,255,0.3);
  margin-bottom: 10px;
}

.toggle-row {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
}

.device-btn {
  flex: 1;
  padding: 6px 0;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.12);
  background: transparent;
  color: rgba(255,255,255,0.45);
  font-family: 'DM Mono', monospace;
  font-size: 11px;
  cursor: pointer;
  transition: all 150ms;
}

.device-btn.active {
  background: #E8FF47;
  color: #1A1A1A;
  border-color: #E8FF47;
  font-weight: 600;
}

.device-btn:disabled { opacity: 0.3; cursor: not-allowed; }

.chunk-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: rgba(255,255,255,0.5);
  font-size: 12px;
  margin-bottom: 8px;
}

.chunk-toggle input { display: none; }

.toggle-track {
  width: 30px;
  height: 17px;
  background: rgba(255,255,255,0.1);
  border-radius: 999px;
  position: relative;
  flex-shrink: 0;
  transition: background 200ms;
}

.toggle-thumb {
  position: absolute;
  width: 13px;
  height: 13px;
  background: white;
  border-radius: 999px;
  top: 2px;
  left: 2px;
  transition: left 200ms;
}

.chunk-toggle input:checked + .toggle-track { background: #E8FF47; }
.chunk-toggle input:checked + .toggle-track .toggle-thumb { left: 15px; background: #1A1A1A; }

.hint-text {
  font-size: 11px;
  color: rgba(255,255,255,0.25);
}

.hint-text.warn { color: #FF8A50; }

/* ── Main ── */
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* ── Topbar ── */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 24px;
  background: #FFFFFF;
  border-bottom: 1px solid #E8E6E1;
  position: sticky;
  top: 0;
  z-index: 10;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.breadcrumb {
  font-size: 13px;
  color: #6B6860;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 260px;
  font-family: 'DM Mono', monospace;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  background: #F0EEE8;
  color: #6B6860;
  flex-shrink: 0;
}

.badge-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: #C4C0B8;
}

.status-badge.processing { background: #FFF8E8; color: #92600A; }
.status-badge.processing .badge-dot { background: #F5A623; animation: pulse 1.2s infinite; }
.status-badge.complete { background: #EDFAF3; color: #1A7A47; }
.status-badge.complete .badge-dot { background: #2ECC72; }
.status-badge.error { background: #FEF0F0; color: #B91C1C; }
.status-badge.error .badge-dot { background: #EF4444; }

.topbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid #E0DDD6;
  background: #FFFFFF;
  color: #1A1A1A;
  font-family: inherit;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 150ms;
  white-space: nowrap;
}

.action-btn:hover { background: #F5F4F0; border-color: #C4C0B8; }
.action-btn:disabled { opacity: 0.35; cursor: not-allowed; transform: none; }

.action-btn.primary {
  background: #1A1A1A;
  color: #FFFFFF;
  border-color: #1A1A1A;
}
.action-btn.primary:hover:not(:disabled) { background: #333; border-color: #333; }

.action-btn.accent {
  background: #E8FF47;
  color: #1A1A1A;
  border-color: #D4EB00;
}
.action-btn.accent:hover:not(:disabled) { background: #DEFF00; }

/* ── Canvas ── */
.canvas {
  flex: 1;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── Upload zone ── */
.upload-zone {
  background: #FFFFFF;
  border: 1.5px dashed #D4D1C8;
  border-radius: 12px;
  transition: border-color 200ms, background 200ms;
}

.upload-zone.has-file { border-style: solid; border-color: #1A1A1A; }
.upload-zone.dragging { border-color: #E8FF47; background: #FFFFEE; }
.upload-zone.processing { opacity: 0.6; pointer-events: none; }

#video-upload { display: none; }

.upload-inner {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 24px 28px;
  cursor: pointer;
}

.upload-ring {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: #F5F4F0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: #6B6860;
}

.upload-zone.has-file .upload-ring {
  background: #1A1A1A;
  color: white;
}

.upload-title {
  font-size: 15px;
  font-weight: 500;
  color: #1A1A1A;
  margin-bottom: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 480px;
}

.upload-sub {
  font-size: 12.5px;
  color: #9B978E;
}

/* ── Progress card ── */
.progress-card {
  background: #FFFFFF;
  border: 1px solid #E8E6E1;
  border-radius: 12px;
  padding: 20px 24px;
  display: none;
}

.progress-card.visible { display: block; }

.progress-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 14px;
}

.card-label {
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: #9B978E;
  margin-bottom: 3px;
}

.progress-message {
  font-size: 14px;
  color: #1A1A1A;
  font-weight: 500;
}

.progress-pct {
  font-size: 36px;
  font-weight: 300;
  color: #1A1A1A;
  font-family: 'DM Sans', sans-serif;
  line-height: 1;
}

.progress-pct em {
  font-size: 16px;
  font-style: normal;
  color: #9B978E;
  margin-left: 2px;
}

.progress-bar {
  height: 4px;
  background: #F0EEE8;
  border-radius: 999px;
  overflow: hidden;
  margin-bottom: 14px;
}

.progress-fill {
  height: 100%;
  background: #1A1A1A;
  border-radius: 999px;
  transition: width 350ms ease;
}

.stage-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.pill {
  padding: 3px 10px;
  border-radius: 999px;
  background: #F5F4F0;
  color: #9B978E;
  font-size: 11.5px;
  font-weight: 500;
}

.pill.current {
  background: #1A1A1A;
  color: #FFFFFF;
}

.pill.done {
  background: #EDFAF3;
  color: #1A7A47;
}

.error-msg {
  margin-top: 12px;
  font-size: 13px;
  color: #B91C1C;
  padding: 10px 12px;
  background: #FEF0F0;
  border-radius: 8px;
}

/* ── Results grid ── */
.results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(440px, 1fr));
  gap: 16px;
}

.result-card {
  background: #FFFFFF;
  border: 1px solid #E8E6E1;
  border-radius: 12px;
  padding: 20px 24px;
}

.card-head {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 16px;
}

.card-title {
  font-size: 17px;
  font-weight: 600;
  color: #1A1A1A;
  letter-spacing: -0.2px;
}

/* Timeline */
.timeline-bar {
  position: relative;
  height: 40px;
  background: #F5F4F0;
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 14px;
}

.timeline-seg {
  position: absolute;
  top: 6px;
  bottom: 6px;
  background: #1A1A1A;
  border-radius: 3px;
  opacity: 0;
  animation: fadeIn 300ms both ease;
}

.scene-list {
  max-height: 220px;
  overflow-y: auto;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.scene-list li {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 13px;
}

.scene-list li:hover { background: #F5F4F0; }

.scene-num {
  font-family: 'DM Mono', monospace;
  font-size: 11px;
  color: #C4C0B8;
  min-width: 24px;
}

.scene-range {
  flex: 1;
  font-family: 'DM Mono', monospace;
  font-size: 12px;
  color: #4A4740;
}

.scene-dur {
  font-size: 12px;
  color: #9B978E;
  font-family: 'DM Mono', monospace;
}

.overflow-note {
  margin-top: 8px;
  font-size: 12px;
  color: #9B978E;
  font-style: italic;
}

/* Output card */
.output-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.out-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid #E0DDD6;
  background: #1A1A1A;
  color: #FFFFFF;
  font-family: inherit;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  text-decoration: none;
  transition: all 150ms;
}

.out-btn:hover { background: #333; }
.out-btn.secondary { background: transparent; color: #1A1A1A; }
.out-btn.secondary:hover { background: #F5F4F0; }
.out-btn.small { padding: 5px 10px; font-size: 12px; }

/* Player */
.player-card { grid-column: 1 / -1; }

.video-el {
  width: 100%;
  max-height: 420px;
  border-radius: 8px;
  background: #0A0A0A;
  display: block;
}

/* Key moments */
.moments-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 320px;
  overflow-y: auto;
}

.moments-list li {
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #F0EEE8;
  transition: border-color 150ms;
}

.moments-list li:hover { border-color: #D4D1C8; }

.moment-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.moment-time {
  font-family: 'DM Mono', monospace;
  font-size: 12px;
  color: #4A4740;
}

.moment-score {
  font-size: 12px;
  font-weight: 600;
  color: #1A1A1A;
  background: #E8FF47;
  padding: 2px 8px;
  border-radius: 999px;
}

.moment-reason {
  font-size: 12.5px;
  color: #6B6860;
  margin-bottom: 8px;
  line-height: 1.4;
}

/* Animations */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 0.85; transform: none; }
}

/* Scrollbar */
.scene-list::-webkit-scrollbar,
.moments-list::-webkit-scrollbar { width: 4px; }
.scene-list::-webkit-scrollbar-track,
.moments-list::-webkit-scrollbar-track { background: transparent; }
.scene-list::-webkit-scrollbar-thumb,
.moments-list::-webkit-scrollbar-thumb { background: #D4D1C8; border-radius: 2px; }

/* Responsive */
@media (max-width: 900px) {
  .sidebar { width: 56px; }
  .logo-text, .nav-label, .sidebar-bottom { display: none; }
  .sidebar-logo { padding: 0 14px 16px; justify-content: center; }
  .nav-item { justify-content: center; padding: 10px; }
  .topbar { flex-direction: column; align-items: stretch; gap: 10px; }
  .topbar-actions { flex-wrap: wrap; }
  .results-grid { grid-template-columns: 1fr; }
  .player-card { grid-column: 1; }
}
</style>