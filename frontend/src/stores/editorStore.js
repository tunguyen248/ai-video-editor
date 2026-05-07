// Central client-side state for AI detection, source playback, trim edits, and export jobs.
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export const API_BASE = (import.meta.env.VITE_API_BASE || import.meta.env.API_BASE || 'http://localhost:5000').replace(/\/$/, '')

const normalizeMoment = (moment, index) => ({
  id: moment.id || `moment-${index + 1}`,
  start: Number(moment.start || 0),
  end: Number(moment.end || 0),
  score: Number(moment.score || 0),
  peak_score: Number(moment.peak_score || moment.score || 0),
  reason: String(moment.reason || 'Detected highlight'),
})

const normalizeInterval = item => ({
  start: Number(item?.start || 0),
  end: Number(item?.end ?? item?.start ?? 0),
})

export const useEditorStore = defineStore('editor', () => {
  // Job state is kept here so toolbar controls, AI panels, and export views stay synchronized.
  const selectedFile = ref(null)
  const localSourceUrl = ref('')
  const sourceVideoUrl = ref('')
  const sourceMimeType = ref('video/mp4')
  const videoId = ref('')
  const moments = ref([])
  const transcriptSegments = ref([])
  const audioPeaks = ref([])
  const pitchSpikes = ref([])
  const speechRateSpikes = ref([])
  const sceneChanges = ref([])
  const semanticDiagnostics = ref({})
  const selectedClipId = ref('')
  const whisperDevice = ref('cpu')
  const smartChunking = ref(true)
  const whisperCapabilities = ref(null)
  const status = ref('idle')
  const statusMessage = ref('')
  const progress = ref(0)
  const activeJobType = ref('')
  const exportUrl = ref('')
  const verticalExportUrl = ref('')
  const templates = ref([])
  const presets = ref([])
  const selectedTemplateId = ref('')
  const templateParams = ref({})
  const gameDetection = ref(null)
  const pollTimer = ref(null)

  const isProcessing = computed(() => status.value === 'processing')
  const gpuAvailable = computed(() => Boolean(whisperCapabilities.value?.devices?.gpu?.available))
  const selectedClip = computed(() => moments.value.find(moment => moment.id === selectedClipId.value) || moments.value[0] || null)
  const selectedTemplate = computed(() => templates.value.find(template => template.id === selectedTemplateId.value) || null)
  const durationEstimate = computed(() => Math.max(1, ...moments.value.map(moment => moment.end), ...transcriptSegments.value.map(segment => Number(segment.end || 0))))

  const clearPollTimer = () => {
    // Only one backend job poll loop should be active for the current project.
    if (pollTimer.value) {
      window.clearTimeout(pollTimer.value)
      pollTimer.value = null
    }
  }

  const setSelectedFile = file => {
    // Reset derived editor state whenever the source asset changes.
    if (localSourceUrl.value) URL.revokeObjectURL(localSourceUrl.value)
    clearPollTimer()
    selectedFile.value = file
    localSourceUrl.value = file ? URL.createObjectURL(file) : ''
    sourceVideoUrl.value = localSourceUrl.value
    sourceMimeType.value = file?.type || 'video/mp4'
    videoId.value = ''
    moments.value = []
    transcriptSegments.value = []
    audioPeaks.value = []
    pitchSpikes.value = []
    speechRateSpikes.value = []
    sceneChanges.value = []
    semanticDiagnostics.value = {}
    selectedClipId.value = ''
    exportUrl.value = ''
    verticalExportUrl.value = ''
    selectedTemplateId.value = ''
    templateParams.value = {}
    gameDetection.value = null
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
    // Backend routes return JSON for both success and error responses.
    const res = await fetch(`${API_BASE}${path}`, opts)
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || data.error || 'Request failed.')
    return data
  }

  const waitForJob = (jobId, onComplete) => new Promise((resolve, reject) => {
    // Polling keeps the UI independent from WebSocket availability in local dev.
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

  const loadTemplates = async () => {
    try {
      const res = await fetch(`${API_BASE}/templates`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || data.error || 'Template load failed.')
      templates.value = Array.isArray(data) ? data : []
    } catch (error) {
      setError(error.message || 'Template load failed.')
    }
  }

  const loadPresets = async () => {
    try {
      const res = await fetch(`${API_BASE}/presets`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || data.error || 'Preset load failed.')
      presets.value = Array.isArray(data) ? data : []
    } catch {
      presets.value = []
    }
  }

  const getTemplateDefaults = template => Object.fromEntries(
    (template?.controls || []).map(control => [control.id, control.default])
  )

  const loadTemplate = templateId => {
    const template = templates.value.find(item => item.id === templateId)
    if (!template) return
    selectedTemplateId.value = template.id
    templateParams.value = getTemplateDefaults(template)
  }

  const loadPreset = preset => {
    const selectedPreset = typeof preset === 'string'
      ? presets.value.find(item => item.id === preset)
      : preset
    if (!selectedPreset) return
    loadTemplate(selectedPreset.baseTemplateId)
    templateParams.value = {
      ...templateParams.value,
      ...(selectedPreset.params || {}),
    }
  }

  const updateTemplateParam = (key, value) => {
    templateParams.value = {
      ...templateParams.value,
      [key]: Number(value),
    }
  }

  const detectGame = async () => {
    if (!selectedFile.value) return setError('Select a video first.')

    clearPollTimer()
    activeJobType.value = 'detect_game'
    gameDetection.value = null
    verticalExportUrl.value = ''
    setStatus('processing', 'Uploading clip for game detection', 8)

    const fd = new FormData()
    fd.append('video', selectedFile.value)

    try {
      const result = await startRequest('/detect_game', {
        method: 'POST',
        body: fd,
      })

      gameDetection.value = result
      videoId.value = result.videoId || ''
      sourceVideoUrl.value = result.sourceVideoPath
        ? `${API_BASE}${result.sourceVideoPath}`
        : localSourceUrl.value
      sourceMimeType.value = selectedFile.value?.type || 'video/mp4'
      status.value = 'complete'
      statusMessage.value = result.gameName === 'Unknown'
        ? 'No game detected. Generic template recommended.'
        : `Detected ${result.gameName}.`
      progress.value = 100
      activeJobType.value = ''
    } catch (error) {
      setError(error.message || 'Game detection failed.')
    }
  }

  const renderVertical = async () => {
    if (!videoId.value) return setError('Detect game before rendering.')
    if (!selectedTemplateId.value) return setError('Select a template first.')

    clearPollTimer()
    activeJobType.value = 'render_vertical'
    verticalExportUrl.value = ''
    setStatus('processing', 'Submitting vertical render', 5)

    try {
      const payload = await startRequest('/render_vertical', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          videoId: videoId.value,
          templateId: selectedTemplateId.value,
          params: templateParams.value,
        }),
      })
      await waitForJob(payload.job_id, result => {
        verticalExportUrl.value = result.export_path ? `${API_BASE}${result.export_path}` : ''
        status.value = 'complete'
        statusMessage.value = 'Vertical export complete.'
        progress.value = 100
        activeJobType.value = ''
      })
    } catch (error) {
      setError(error.message || 'Vertical render failed.')
    }
  }

  const savePreset = async ({ name, description = '' }) => {
    if (!selectedTemplate.value) return setError('Select a template before saving a preset.')
    const template = selectedTemplate.value

    try {
      const preset = await startRequest('/presets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          baseTemplateId: template.id,
          name,
          game: template.game,
          gameId: template.gameId,
          category: template.category,
          description,
          params: templateParams.value,
        }),
      })
      presets.value = [
        preset,
        ...presets.value.filter(item => item.id !== preset.id),
      ]
      status.value = 'complete'
      statusMessage.value = `Saved preset "${preset.name}".`
      progress.value = 100
      return preset
    } catch (error) {
      setError(error.message || 'Preset save failed.')
      return null
    }
  }

  const detectKeyMoments = async () => {
    // Upload the current file, then hydrate the editable timeline from job results.
    if (!selectedFile.value) return setError('Select a video first.')
    clearPollTimer()
    activeJobType.value = 'key_moments'
    exportUrl.value = ''
    verticalExportUrl.value = ''
    moments.value = []
    transcriptSegments.value = []
    audioPeaks.value = []
    pitchSpikes.value = []
    speechRateSpikes.value = []
    sceneChanges.value = []
    semanticDiagnostics.value = {}
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
        audioPeaks.value = Array.isArray(result.audio_peaks) ? result.audio_peaks.map(normalizeInterval) : []
        pitchSpikes.value = Array.isArray(result.pitch_spikes) ? result.pitch_spikes.map(normalizeInterval) : []
        speechRateSpikes.value = Array.isArray(result.speech_rate_spikes) ? result.speech_rate_spikes.map(normalizeInterval) : []
        sceneChanges.value = Array.isArray(result.scene_changes) ? result.scene_changes.map(Number).filter(Number.isFinite) : []
        semanticDiagnostics.value = result.semantic_diagnostics || {}
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
    // Send the current edit decision list back to the backend for FFmpeg rendering.
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
    audioPeaks,
    pitchSpikes,
    speechRateSpikes,
    sceneChanges,
    semanticDiagnostics,
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
    verticalExportUrl,
    templates,
    presets,
    selectedTemplateId,
    selectedTemplate,
    templateParams,
    gameDetection,
    isProcessing,
    gpuAvailable,
    durationEstimate,
    setSelectedFile,
    loadWhisperCapabilities,
    loadTemplates,
    loadPresets,
    loadTemplate,
    loadPreset,
    updateTemplateParam,
    detectGame,
    renderVertical,
    savePreset,
    detectKeyMoments,
    selectClip,
    updateClipRange,
    exportProject,
  }
})
