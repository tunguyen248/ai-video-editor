import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export const API_BASE = 'http://localhost:5000'

const normalizeMoment = (moment, index) => ({
  id: moment.id || `moment-${index + 1}`,
  start: Number(moment.start || 0),
  end: Number(moment.end || 0),
  score: Number(moment.score || 0),
  peak_score: Number(moment.peak_score || moment.score || 0),
  reason: String(moment.reason || 'Detected highlight'),
})

export const useEditorStore = defineStore('editor', () => {
  const selectedFile = ref(null)
  const localSourceUrl = ref('')
  const sourceVideoUrl = ref('')
  const sourceMimeType = ref('video/mp4')
  const videoId = ref('')
  const moments = ref([])
  const transcriptSegments = ref([])
  const selectedClipId = ref('')
  const whisperDevice = ref('cpu')
  const smartChunking = ref(true)
  const whisperCapabilities = ref(null)
  const status = ref('idle')
  const statusMessage = ref('')
  const progress = ref(0)
  const activeJobType = ref('')
  const exportUrl = ref('')
  const pollTimer = ref(null)

  const isProcessing = computed(() => status.value === 'processing')
  const gpuAvailable = computed(() => Boolean(whisperCapabilities.value?.devices?.gpu?.available))
  const selectedClip = computed(() => moments.value.find(moment => moment.id === selectedClipId.value) || moments.value[0] || null)
  const durationEstimate = computed(() => Math.max(1, ...moments.value.map(moment => moment.end), ...transcriptSegments.value.map(segment => Number(segment.end || 0))))

  const clearPollTimer = () => {
    if (pollTimer.value) {
      window.clearTimeout(pollTimer.value)
      pollTimer.value = null
    }
  }

  const setSelectedFile = file => {
    if (localSourceUrl.value) URL.revokeObjectURL(localSourceUrl.value)
    clearPollTimer()
    selectedFile.value = file
    localSourceUrl.value = file ? URL.createObjectURL(file) : ''
    sourceVideoUrl.value = localSourceUrl.value
    sourceMimeType.value = file?.type || 'video/mp4'
    videoId.value = ''
    moments.value = []
    transcriptSegments.value = []
    selectedClipId.value = ''
    exportUrl.value = ''
    status.value = 'idle'
    statusMessage.value = ''
    progress.value = 0
    activeJobType.value = ''
  }

  const setStatus = (state, message, nextProgress = progress.value) => {
    status.value = state
    statusMessage.value = message
    progress.value = Number(nextProgress)
  }

  const setError = message => {
    clearPollTimer()
    status.value = 'error'
    statusMessage.value = message
    progress.value = 100
    activeJobType.value = ''
  }

  const startRequest = async (path, opts) => {
    const res = await fetch(`${API_BASE}${path}`, opts)
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || data.error || 'Request failed.')
    return data
  }

  const waitForJob = (jobId, onComplete) => new Promise((resolve, reject) => {
    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/job_status/${jobId}`)
        const job = await res.json()
        if (!res.ok) throw new Error(job.detail || job.error || 'Status check failed.')
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
        pollTimer.value = window.setTimeout(poll, 500)
      } catch (error) {
        clearPollTimer()
        reject(error)
      }
    }
    poll()
  })

  const loadWhisperCapabilities = async () => {
    try {
      const res = await fetch(`${API_BASE}/whisper_capabilities`)
      whisperCapabilities.value = await res.json()
      if (!gpuAvailable.value && whisperDevice.value === 'gpu') whisperDevice.value = 'cpu'
    } catch {
      whisperCapabilities.value = { devices: { gpu: { available: false } } }
    }
  }

  const detectKeyMoments = async () => {
    if (!selectedFile.value) return setError('Select a video first.')
    clearPollTimer()
    activeJobType.value = 'key_moments'
    exportUrl.value = ''
    moments.value = []
    transcriptSegments.value = []
    setStatus('processing', 'Uploading for key moment detection', 4)

    const fd = new FormData()
    fd.append('video', selectedFile.value)
    fd.append('device', whisperDevice.value)
    fd.append('use_chunking', String(smartChunking.value))

    try {
      const payload = await startRequest('/detect_key_moments', { method: 'POST', body: fd })
      await waitForJob(payload.job_id, result => {
        videoId.value = result.video_id || ''
        sourceVideoUrl.value = result.source_video_path ? `${API_BASE}${result.source_video_path}` : localSourceUrl.value
        sourceMimeType.value = selectedFile.value?.type || 'video/mp4'
        transcriptSegments.value = Array.isArray(result.transcript_segments) ? result.transcript_segments : []
        moments.value = Array.isArray(result.moments) ? result.moments.map(normalizeMoment) : []
        selectedClipId.value = moments.value[0]?.id || ''
        status.value = 'complete'
        statusMessage.value = `Detected ${moments.value.length} editable moment(s).`
        progress.value = 100
        activeJobType.value = ''
      })
    } catch (error) {
      setError(error.message || 'Key moment detection failed.')
    }
  }

  const selectClip = clipId => {
    selectedClipId.value = clipId
  }

  const updateClipRange = (clipId, start, end) => {
    const index = moments.value.findIndex(moment => moment.id === clipId)
    if (index === -1) return
    moments.value[index] = {
      ...moments.value[index],
      start: Number(start),
      end: Number(end),
    }
  }

  const exportProject = async () => {
    if (!videoId.value || !moments.value.length) return setError('Detect key moments before exporting.')
    clearPollTimer()
    activeJobType.value = 'export_project'
    exportUrl.value = ''
    setStatus('processing', 'Submitting edit decision list', 3)

    const clips = moments.value.map(({ id, start, end, score, reason }) => ({ id, start, end, score, reason }))
    try {
      const payload = await startRequest('/export_project', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_id: videoId.value, clips }),
      })
      await waitForJob(payload.job_id, result => {
        exportUrl.value = result.export_path ? `${API_BASE}${result.export_path}` : ''
        status.value = 'complete'
        statusMessage.value = `Exported ${Array.isArray(result.clips) ? result.clips.length : clips.length} clip(s).`
        progress.value = 100
        activeJobType.value = ''
      })
    } catch (error) {
      setError(error.message || 'Project export failed.')
    }
  }

  return {
    selectedFile,
    sourceVideoUrl,
    sourceMimeType,
    videoId,
    moments,
    transcriptSegments,
    selectedClipId,
    selectedClip,
    whisperDevice,
    smartChunking,
    whisperCapabilities,
    status,
    statusMessage,
    progress,
    activeJobType,
    exportUrl,
    isProcessing,
    gpuAvailable,
    durationEstimate,
    setSelectedFile,
    loadWhisperCapabilities,
    detectKeyMoments,
    selectClip,
    updateClipRange,
    exportProject,
  }
})
