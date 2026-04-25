<template>
  <div class="capcut-shell">
    <header class="topbar">
      <div class="top-left">
        <div class="brand">
          <span class="brand-mark"></span>
          <span>AIcut Studio</span>
        </div>
        <input v-model="projectName" class="project-name" spellcheck="false" />
      </div>

      <div class="top-center">
        <button class="icon-btn" title="Undo" @click="undo">↶</button>
        <button class="icon-btn" title="Redo" @click="redo">↷</button>
        <span class="divider"></span>
        <button class="icon-btn" :class="{ active: snapEnabled }" title="Snap" @click="snapEnabled = !snapEnabled">⌁</button>
        <button class="ratio-chip" @click="cycleRatio">{{ aspectRatio }}</button>
      </div>

      <div class="top-right">
        <span class="autosave">{{ store.statusMessage || 'Ready' }}</span>
        <button class="export-btn" :disabled="store.isProcessing || !canExport" @click="exportCurrentProject">
          Export
        </button>
      </div>
    </header>

    <main class="editor-body">
      <aside class="left-panel">
        <nav class="left-tabs">
          <button
            v-for="tab in leftTabs"
            :key="tab.id"
            class="left-tab"
            :class="{ active: activeLeftTab === tab.id }"
            @click="activeLeftTab = tab.id"
            :title="tab.label"
          >
            <span class="tab-icon" v-html="tab.icon"></span>
            <span>{{ tab.label }}</span>
          </button>
        </nav>

        <section class="left-content">
          <div v-if="activeLeftTab === 'media'" class="panel-page">
            <div class="panel-head">
              <strong>Media</strong>
              <label class="mini-action">
                Import
                <input type="file" accept="video/*,audio/*,image/*" multiple @change="handleFileImport" />
              </label>
            </div>

            <div
              class="media-drop"
              :class="{ over: mediaDragOver }"
              @dragover.prevent="mediaDragOver = true"
              @dragleave.prevent="mediaDragOver = false"
              @drop.prevent="handleMediaFileDrop"
            >
              <span>Drop files here</span>
            </div>

            <div class="media-grid">
              <button
                v-for="item in mediaItems"
                :key="item.id"
                class="media-card"
                draggable="true"
                @dragstart="onMediaDragStart($event, item)"
                @dblclick="addToTimeline(item)"
              >
                <span class="media-thumb" :style="{ background: item.color }">
                  <span class="media-type">{{ item.type }}</span>
                  <span v-if="item.duration" class="media-duration">{{ formatTime(item.duration, false) }}</span>
                </span>
                <span class="media-name">{{ item.name }}</span>
              </button>

              <div v-if="mediaItems.length === 0" class="empty-panel">
                <strong>No media imported</strong>
                <p>Import video, audio, or images to begin editing.</p>
              </div>
            </div>
          </div>

          <div v-if="activeLeftTab === 'text'" class="panel-page">
            <div class="panel-head"><strong>Text</strong></div>
            <button v-for="preset in textPresets" :key="preset.id" class="preset-card" @click="addText(preset)">
              <span :style="{ fontFamily: preset.font, fontWeight: preset.weight, color: preset.color }">{{ preset.label }}</span>
              <small>{{ preset.name }}</small>
            </button>
          </div>

          <div v-if="activeLeftTab === 'audio'" class="panel-page">
            <div class="panel-head"><strong>Audio</strong></div>
            <button v-for="audio in stockAudio" :key="audio.id" class="audio-row" @click="addStockAudio(audio)">
              <span class="mini-wave">
                <i v-for="n in 18" :key="n" :style="{ height: `${waveHeight(audio.id, n, 24)}px` }"></i>
              </span>
              <span>
                <strong>{{ audio.name }}</strong>
                <small>{{ audio.genre }} · {{ audio.durationLabel }}</small>
              </span>
            </button>
          </div>

          <div v-if="activeLeftTab === 'effects'" class="panel-page">
            <div class="panel-head"><strong>Effects</strong></div>
            <div class="tile-grid">
              <button v-for="fx in effects" :key="fx.id" class="fx-tile" :class="{ active: activeEffect === fx.id }" @click="activeEffect = fx.id">
                <span :style="{ background: fx.preview }"></span>
                <strong>{{ fx.name }}</strong>
              </button>
            </div>
          </div>

          <div v-if="activeLeftTab === 'transitions'" class="panel-page">
            <div class="panel-head"><strong>Transitions</strong></div>
            <div class="tile-grid">
              <button v-for="transition in transitions" :key="transition.id" class="fx-tile" :class="{ active: activeTransition === transition.id }" @click="activeTransition = transition.id">
                <span :style="{ background: transition.preview }">→</span>
                <strong>{{ transition.name }}</strong>
              </button>
            </div>
          </div>

          <div v-if="activeLeftTab === 'stickers'" class="panel-page">
            <div class="panel-head"><strong>Stickers</strong></div>
            <div class="sticker-grid">
              <button v-for="sticker in stickers" :key="sticker" class="sticker" @click="addSticker(sticker)">
                {{ sticker }}
              </button>
            </div>
          </div>
        </section>
      </aside>

      <section class="preview-area">
        <div class="preview-toolbar">
          <button class="tool-btn" @click="fitPreview">Fit</button>
          <div class="zoom-control">
            <button @click="previewZoom = Math.max(25, previewZoom - 25)">-</button>
            <span>{{ previewZoom }}%</span>
            <button @click="previewZoom = Math.min(200, previewZoom + 25)">+</button>
          </div>
          <span class="time-readout">{{ formatTime(currentTime) }} / {{ formatTime(totalDuration) }}</span>
        </div>

        <div class="canvas-wrap" @dragover.prevent @drop.prevent="onCanvasDrop">
          <div class="canvas-stage">
            <div class="canvas-frame" :style="{ transform: `scale(${previewZoom / 100})` }">
              <div ref="canvasRef" class="canvas-inner" :style="canvasStyle">
                <video
                  v-if="activeVideoSrc"
                  ref="videoRef"
                  class="preview-video"
                  :src="activeVideoSrc"
                  :loop="loopEnabled"
                  @loadedmetadata="onVideoLoaded"
                  @timeupdate="onTimeUpdate"
                  @ended="isPlaying = false"
                ></video>
                <div v-else class="canvas-placeholder">
                  <strong>Drop media here</strong>
                  <span>or import from the Media panel</span>
                </div>

                <div
                  v-for="element in canvasElements"
                  :key="element.id"
                  class="canvas-element"
                  :class="{ selected: selectedElementId === element.id }"
                  :style="elementStyle(element)"
                  @mousedown="startElementDrag($event, element)"
                >
                  {{ element.text }}
                  <span v-if="selectedElementId === element.id" class="element-outline"></span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="playback-bar">
          <button class="playback-btn" title="Back 5s" @click="skip(-5)">«</button>
          <button class="play-main" @click="togglePlay">{{ isPlaying ? 'Pause' : 'Play' }}</button>
          <button class="playback-btn" title="Forward 5s" @click="skip(5)">»</button>

          <label class="volume-control">
            <span>Vol</span>
            <input type="range" min="0" max="1" step="0.01" v-model.number="volume" @input="applyVolume" />
          </label>

          <button class="playback-btn" :class="{ active: loopEnabled }" title="Loop" @click="loopEnabled = !loopEnabled">Loop</button>
          <button class="playback-btn" title="Fullscreen" @click="toggleFullscreen">Full</button>
        </div>
      </section>

      <aside class="right-panel">
        <div class="right-tabs">
          <button v-for="tab in rightTabs" :key="tab.id" :class="{ active: activeRightTab === tab.id }" @click="activeRightTab = tab.id">
            {{ tab.label }}
          </button>
        </div>

        <section class="right-content">
          <div v-if="activeRightTab === 'clip'" class="prop-panel">
            <template v-if="selectedTimelineClip">
              <div class="prop-title">{{ selectedTimelineClip.name }}</div>
              <PropertySlider label="Opacity" suffix="%" :min="0" :max="100" v-model="selectedTimelineClip.opacity" />
              <PropertySlider label="Scale" suffix="%" :min="10" :max="300" v-model="selectedTimelineClip.scale" />
              <PropertySlider label="Rotation" suffix="deg" :min="-180" :max="180" v-model="selectedTimelineClip.rotation" />
              <PropertySlider label="Speed" suffix="x" :min="0.1" :max="4" :step="0.1" v-model="selectedTimelineClip.speed" />
              <PropertySlider label="Volume" suffix="%" :min="0" :max="200" v-model="selectedTimelineClip.clipVolume" />

              <div class="prop-subtitle">Color Correction</div>
              <PropertySlider label="Brightness" :min="-100" :max="100" v-model="selectedTimelineClip.brightness" />
              <PropertySlider label="Contrast" :min="-100" :max="100" v-model="selectedTimelineClip.contrast" />
              <PropertySlider label="Saturation" :min="-100" :max="100" v-model="selectedTimelineClip.saturation" />
              <PropertySlider label="Hue" suffix="deg" :min="-180" :max="180" v-model="selectedTimelineClip.hue" />
            </template>

            <div v-else class="no-selection">
              <strong>No clip selected</strong>
              <p>Select a clip in the timeline to edit properties.</p>
            </div>
          </div>

          <div v-if="activeRightTab === 'ai'" class="ai-panel">
            <button v-for="tool in aiTools" :key="tool.id" class="ai-tool" :disabled="store.isProcessing" @click="runAiTool(tool.id)">
              <span>{{ tool.icon }}</span>
              <span>
                <strong>{{ tool.name }}</strong>
                <small>{{ tool.desc }}</small>
              </span>
            </button>

            <div v-if="store.status !== 'idle'" class="ai-status">
              <div class="ai-progress"><span :style="{ width: `${store.progress}%` }"></span></div>
              <p>{{ store.statusMessage }}</p>
            </div>
          </div>

          <div v-if="activeRightTab === 'captions'" class="caption-panel">
            <button class="caption-generate" :disabled="store.isProcessing || !activeVideoFile" @click="generateCaptions">
              Auto-Generate Captions
            </button>
            <div class="caption-list">
              <button
                v-for="caption in captions"
                :key="caption.id"
                class="caption-row"
                :class="{ active: currentTime >= caption.start && currentTime <= caption.end }"
                @click="seekTo(caption.start)"
              >
                <span>{{ formatTime(caption.start) }}</span>
                <strong>{{ caption.text }}</strong>
              </button>
              <div v-if="captions.length === 0" class="no-selection">
                <p>No captions yet.</p>
              </div>
            </div>
          </div>
        </section>
      </aside>
    </main>

    <section class="timeline-section">
      <div class="timeline-toolbar">
        <button class="timeline-btn" :disabled="!selectedTimelineClip" @click="splitAtPlayhead">Split</button>
        <button class="timeline-btn" :disabled="!selectedTimelineClip" @click="deleteSelected">Delete</button>
        <span class="divider"></span>
        <label class="timeline-zoom">
          Zoom
          <input type="range" min="35" max="180" v-model.number="timelineZoom" />
        </label>
        <span class="timeline-duration">{{ formatTime(timelineDuration) }}</span>
      </div>

      <div ref="timelineRef" class="timeline-body" @wheel.shift.prevent="scrollTimeline" @click="seekFromTimeline">
        <div class="timeline-ruler" :style="{ width: `${timelineWidth}px` }">
          <span v-for="tick in rulerTicks" :key="tick.key" class="ruler-tick" :style="{ left: `${tick.left}px` }">
            <em v-if="tick.major">{{ tick.label }}</em>
          </span>
        </div>

        <div class="playhead" :style="{ left: `${trackLabelWidth + currentTime * timelineZoom}px` }" @mousedown.stop="startPlayheadDrag">
          <span></span>
        </div>

        <div class="tracks" :style="{ width: `${trackLabelWidth + timelineWidth}px` }" @dragover.prevent @drop.prevent="onTimelineDrop">
          <div v-for="track in tracks" :key="track.id" class="track-row" :data-track-id="track.id">
            <div class="track-label">
              <span class="track-icon">{{ track.icon }}</span>
              <strong>{{ track.name }}</strong>
              <button :class="{ active: track.muted }" @click.stop="track.muted = !track.muted">M</button>
              <button :class="{ active: track.locked }" @click.stop="track.locked = !track.locked">L</button>
            </div>
            <div class="track-lane">
              <div
                v-for="clip in track.clips"
                :key="clip.id"
                class="timeline-clip"
                :class="[clip.type, { selected: clip.id === selectedTimelineClipId, locked: track.locked }]"
                :style="timelineClipStyle(clip)"
                @mousedown.stop="startClipDrag($event, track, clip, 'move')"
              >
                <button class="resize-handle left" @mousedown.stop="startClipDrag($event, track, clip, 'resize-left')"></button>
                <span v-if="clip.type === 'audio'" class="waveform">
                  <i v-for="n in 42" :key="n" :style="{ height: `${waveHeight(clip.id, n, 28)}px` }"></i>
                </span>
                <span v-else class="clip-title">{{ clip.name }}</span>
                <button class="resize-handle right" @mousedown.stop="startClipDrag($event, track, clip, 'resize-right')"></button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { API_BASE, useEditorStore } from './stores/editorStore'

const PropertySlider = defineComponent({
  props: {
    label: { type: String, required: true },
    min: { type: Number, default: 0 },
    max: { type: Number, default: 100 },
    step: { type: Number, default: 1 },
    suffix: { type: String, default: '' },
    modelValue: { type: [Number, String], default: 0 },
  },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () => h('label', { class: 'prop-row' }, [
      h('span', props.label),
      h('input', {
        type: 'range',
        min: props.min,
        max: props.max,
        step: props.step,
        value: props.modelValue,
        onInput: event => emit('update:modelValue', Number(event.target.value)),
      }),
      h('em', `${props.modelValue}${props.suffix}`),
    ])
  },
})

const store = useEditorStore()

const projectName = ref('Untitled Project')
const activeLeftTab = ref('media')
const activeRightTab = ref('clip')
const snapEnabled = ref(true)
const showExport = ref(false)
const aspectRatio = ref('16:9')
const previewZoom = ref(100)
const timelineZoom = ref(76)
const currentTime = ref(0)
const totalDuration = ref(1)
const isPlaying = ref(false)
const volume = ref(0.9)
const loopEnabled = ref(false)
const activeVideoSrc = ref('')
const activeVideoFile = ref(null)
const activeEffect = ref('')
const activeTransition = ref('')
const mediaDragOver = ref(false)
const selectedElementId = ref('')
const selectedTimelineClipId = ref('')
const captions = ref([])
const history = ref([])
const future = ref([])

const videoRef = ref(null)
const canvasRef = ref(null)
const timelineRef = ref(null)
const dragData = ref(null)
const trackLabelWidth = 150

const leftTabs = [
  { id: 'media', label: 'Media', icon: '<svg viewBox="0 0 24 24"><path d="M4 5h16v14H4z"/><path d="m9 9 6 3-6 3z"/></svg>' },
  { id: 'text', label: 'Text', icon: '<svg viewBox="0 0 24 24"><path d="M4 5h16M12 5v14M8 19h8"/></svg>' },
  { id: 'audio', label: 'Audio', icon: '<svg viewBox="0 0 24 24"><path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/></svg>' },
  { id: 'effects', label: 'Effects', icon: '<svg viewBox="0 0 24 24"><path d="m12 2 2.8 6 6.2.6-4.7 4.2 1.4 6.2-5.7-3.2L6.3 19l1.4-6.2L3 8.6 9.2 8z"/></svg>' },
  { id: 'transitions', label: 'Transitions', icon: '<svg viewBox="0 0 24 24"><path d="M4 7h9l-3-3m3 3-3 3M20 17h-9l3-3m-3 3 3 3"/></svg>' },
  { id: 'stickers', label: 'Stickers', icon: '<svg viewBox="0 0 24 24"><path d="M12 3c5 0 9 4 9 9v2l-7 7h-2a9 9 0 0 1 0-18z"/><path d="M14 21v-5a2 2 0 0 1 2-2h5"/></svg>' },
]

const rightTabs = [
  { id: 'clip', label: 'Clip' },
  { id: 'ai', label: 'AI Tools' },
  { id: 'captions', label: 'Captions' },
]

const textPresets = [
  { id: 'title', name: 'Title', label: 'Bold Title', font: 'Inter', weight: 800, color: '#ffffff', size: 42 },
  { id: 'subtitle', name: 'Subtitle', label: 'Clean subtitle', font: 'Inter', weight: 600, color: '#f4f4f4', size: 28 },
  { id: 'hook', name: 'Hook', label: 'Viral Hook', font: 'Impact', weight: 700, color: '#e8ff47', size: 40 },
]

const stockAudio = [
  { id: 'beat-1', name: 'Pulse Drive', genre: 'Electronic', duration: 24, durationLabel: '0:24' },
  { id: 'beat-2', name: 'Soft Focus', genre: 'Ambient', duration: 36, durationLabel: '0:36' },
  { id: 'beat-3', name: 'Creator Pop', genre: 'Pop', duration: 18, durationLabel: '0:18' },
]

const effects = [
  { id: 'glow', name: 'Glow', preview: 'linear-gradient(135deg, #113, #58f)' },
  { id: 'film', name: 'Film', preview: 'linear-gradient(135deg, #222, #a87)' },
  { id: 'punch', name: 'Punch', preview: 'linear-gradient(135deg, #222, #f44)' },
  { id: 'dream', name: 'Dream', preview: 'linear-gradient(135deg, #243, #b7f)' },
]

const transitions = [
  { id: 'fade', name: 'Fade', preview: 'linear-gradient(90deg, #111, #777)' },
  { id: 'slide', name: 'Slide', preview: 'linear-gradient(90deg, #075, #0cf)' },
  { id: 'wipe', name: 'Wipe', preview: 'linear-gradient(90deg, #1a1a1a 48%, #e8ff47 50%)' },
  { id: 'zoom', name: 'Zoom', preview: 'radial-gradient(circle, #e8ff47, #111)' },
]

const stickers = ['🔥', '✨', '⭐', '💬', '🚀', '❤️', '✅', '🎯', 'LOL', 'WOW', 'NEW', 'AI']

const aiTools = [
  { id: 'smart-cut', icon: '✂', name: 'Smart Cut', desc: 'Detect editable key moments' },
  { id: 'scene-detect', icon: '▦', name: 'Scene Detect', desc: 'Call /analyze_scenes' },
  { id: 'captions', icon: 'CC', name: 'Auto Captions', desc: 'Call /generate_captions' },
  { id: 'background', icon: 'AI', name: 'Background Remove', desc: 'Coming soon' },
  { id: 'beat', icon: '♪', name: 'Beat Sync', desc: 'Coming soon' },
]

const mediaItems = ref([])
const canvasElements = ref([])
const tracks = ref([
  { id: 'video', type: 'video', icon: 'V', name: 'Video', muted: false, locked: false, clips: [] },
  { id: 'overlay', type: 'overlay', icon: 'T', name: 'Overlay', muted: false, locked: false, clips: [] },
  { id: 'audio', type: 'audio', icon: 'A', name: 'Audio', muted: false, locked: false, clips: [] },
])

const selectedTimelineClip = computed(() => {
  for (const track of tracks.value) {
    const found = track.clips.find(clip => clip.id === selectedTimelineClipId.value)
    if (found) return found
  }
  return null
})

const timelineDuration = computed(() => {
  const clipEnd = tracks.value.flatMap(track => track.clips).reduce((max, clip) => Math.max(max, clip.start + clip.duration), 0)
  return Math.max(totalDuration.value, clipEnd, 20)
})

const timelineWidth = computed(() => Math.ceil(timelineDuration.value * timelineZoom.value) + 260)
const canExport = computed(() => Boolean(store.videoId && tracks.value.some(track => track.clips.some(clip => clip.type === 'video'))))

const canvasStyle = computed(() => {
  const [w, h] = aspectRatio.value.split(':').map(Number)
  const base = 560
  return {
    width: `${base}px`,
    height: `${Math.round(base * (h / w))}px`,
  }
})

const rulerTicks = computed(() => {
  const step = timelineZoom.value > 120 ? 1 : 5
  const count = Math.ceil(timelineDuration.value / step)
  return Array.from({ length: count + 1 }, (_, index) => {
    const seconds = index * step
    return {
      key: `${seconds}-${timelineZoom.value}`,
      left: trackLabelWidth + seconds * timelineZoom.value,
      major: index % 2 === 0,
      label: formatTime(seconds, false),
    }
  })
})

const defaultClipProps = () => ({
  opacity: 100,
  scale: 100,
  rotation: 0,
  speed: 1,
  clipVolume: 100,
  brightness: 0,
  contrast: 0,
  saturation: 0,
  hue: 0,
})

const makeId = prefix => `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`

const mediaTypeFromFile = file => {
  if (file.type.startsWith('video/')) return 'video'
  if (file.type.startsWith('audio/')) return 'audio'
  return 'image'
}

const mediaColor = type => ({
  video: 'linear-gradient(135deg, #0d6efd, #00c9d8)',
  audio: 'linear-gradient(135deg, #5b2bd8, #b857ff)',
  image: 'linear-gradient(135deg, #167a45, #7bdc7b)',
}[type] || '#333')

const handleFileImport = event => {
  importFiles(Array.from(event.target.files || []))
  event.target.value = ''
}

const handleMediaFileDrop = event => {
  mediaDragOver.value = false
  importFiles(Array.from(event.dataTransfer.files || []))
}

const importFiles = files => {
  files.forEach(file => {
    const type = mediaTypeFromFile(file)
    const item = {
      id: makeId('media'),
      name: file.name,
      type,
      file,
      url: URL.createObjectURL(file),
      duration: type === 'image' ? 5 : 0,
      color: mediaColor(type),
    }
    mediaItems.value.push(item)
    readMediaDuration(item)

    if (type === 'video' && !activeVideoSrc.value) {
      activateVideoItem(item)
      addToTimeline(item, 0)
    }
  })
}

const readMediaDuration = item => {
  if (item.type === 'image') return
  const element = document.createElement(item.type === 'audio' ? 'audio' : 'video')
  element.preload = 'metadata'
  element.src = item.url
  element.onloadedmetadata = () => {
    item.duration = Number.isFinite(element.duration) ? Math.max(0.1, element.duration) : 8
    if (item.type === 'video' && activeVideoSrc.value === item.url) {
      totalDuration.value = Math.max(1, item.duration)
    }
  }
}

const activateVideoItem = item => {
  if (item.type !== 'video') return
  activeVideoSrc.value = item.url
  activeVideoFile.value = item.file
  totalDuration.value = Math.max(1, item.duration || totalDuration.value)
  store.setSelectedFile(item.file)
  nextTick(applyVolume)
}

const onMediaDragStart = (event, item) => {
  event.dataTransfer.setData('application/x-aicut-media', item.id)
}

const onCanvasDrop = event => {
  const item = mediaItems.value.find(media => media.id === event.dataTransfer.getData('application/x-aicut-media'))
  if (!item) return
  if (item.type === 'video') activateVideoItem(item)
  if (item.type === 'image') addSticker('IMG')
  addToTimeline(item, currentTime.value)
}

const onTimelineDrop = event => {
  const item = mediaItems.value.find(media => media.id === event.dataTransfer.getData('application/x-aicut-media'))
  if (!item || !timelineRef.value) return
  const rect = timelineRef.value.getBoundingClientRect()
  const start = Math.max(0, (event.clientX - rect.left + timelineRef.value.scrollLeft - trackLabelWidth) / timelineZoom.value)
  addToTimeline(item, start)
}

const addToTimeline = (item, start = currentTime.value) => {
  if (item.type === 'video') activateVideoItem(item)
  const track = tracks.value.find(candidate => candidate.type === item.type) || tracks.value[0]
  if (track.locked) return
  const clip = {
    id: makeId('clip'),
    mediaId: item.id,
    type: item.type,
    name: item.name,
    url: item.url,
    start: snapTime(start),
    duration: Math.max(0.2, item.duration || 5),
    sourceStart: 0,
    ...defaultClipProps(),
  }
  track.clips.push(clip)
  selectedTimelineClipId.value = clip.id
  pushHistory()
}

const addStockAudio = audio => {
  const track = tracks.value.find(candidate => candidate.type === 'audio')
  const clip = {
    id: makeId('clip'),
    type: 'audio',
    name: audio.name,
    url: '',
    start: snapTime(currentTime.value),
    duration: audio.duration,
    sourceStart: 0,
    ...defaultClipProps(),
  }
  track.clips.push(clip)
  selectedTimelineClipId.value = clip.id
}

const addText = preset => {
  const element = {
    id: makeId('text'),
    type: 'text',
    text: preset.label,
    x: 50,
    y: 50,
    font: preset.font,
    size: preset.size,
    color: preset.color,
    weight: preset.weight,
  }
  canvasElements.value.push(element)
  selectedElementId.value = element.id
  tracks.value[1].clips.push({
    id: makeId('clip'),
    elementId: element.id,
    type: 'text',
    name: preset.name,
    start: snapTime(currentTime.value),
    duration: 4,
    ...defaultClipProps(),
  })
}

const addSticker = sticker => {
  const element = {
    id: makeId('sticker'),
    type: 'sticker',
    text: sticker,
    x: 50,
    y: 50,
    font: 'Inter',
    size: sticker.length > 2 ? 26 : 44,
    color: '#ffffff',
    weight: 800,
  }
  canvasElements.value.push(element)
  selectedElementId.value = element.id
  tracks.value[1].clips.push({
    id: makeId('clip'),
    elementId: element.id,
    type: 'text',
    name: `Sticker ${sticker}`,
    start: snapTime(currentTime.value),
    duration: 3,
    ...defaultClipProps(),
  })
}

const elementStyle = element => ({
  left: `${element.x}%`,
  top: `${element.y}%`,
  fontFamily: element.font,
  fontSize: `${element.size}px`,
  color: element.color,
  fontWeight: element.weight,
  transform: 'translate(-50%, -50%)',
})

const startElementDrag = (event, element) => {
  selectedElementId.value = element.id
  const startX = event.clientX
  const startY = event.clientY
  const startElementX = element.x
  const startElementY = element.y
  const rect = canvasRef.value.getBoundingClientRect()

  const move = moveEvent => {
    const dx = ((moveEvent.clientX - startX) / rect.width) * 100
    const dy = ((moveEvent.clientY - startY) / rect.height) * 100
    element.x = Math.max(0, Math.min(100, startElementX + dx))
    element.y = Math.max(0, Math.min(100, startElementY + dy))
  }
  const up = () => {
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', up)
  }
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
}

const onVideoLoaded = () => {
  totalDuration.value = Math.max(1, videoRef.value?.duration || totalDuration.value)
  applyVolume()
}

const onTimeUpdate = () => {
  currentTime.value = videoRef.value?.currentTime || 0
}

const togglePlay = async () => {
  if (!videoRef.value) return
  if (isPlaying.value) {
    videoRef.value.pause()
    isPlaying.value = false
    return
  }
  await videoRef.value.play()
  isPlaying.value = true
}

const seekTo = seconds => {
  currentTime.value = Math.max(0, Math.min(timelineDuration.value, seconds))
  if (videoRef.value) videoRef.value.currentTime = currentTime.value
}

const skip = seconds => seekTo(currentTime.value + seconds)

const applyVolume = () => {
  if (videoRef.value) videoRef.value.volume = volume.value
}

const toggleFullscreen = () => {
  canvasRef.value?.requestFullscreen?.()
}

const cycleRatio = () => {
  const ratios = ['16:9', '9:16', '1:1', '4:3', '21:9']
  aspectRatio.value = ratios[(ratios.indexOf(aspectRatio.value) + 1) % ratios.length]
}

const fitPreview = () => {
  previewZoom.value = 100
}

const timelineClipStyle = clip => ({
  left: `${clip.start * timelineZoom.value}px`,
  width: `${Math.max(8, clip.duration * timelineZoom.value)}px`,
  opacity: clip.opacity / 100,
})

const seekFromTimeline = event => {
  if (!timelineRef.value || event.target.closest('.timeline-clip') || event.target.closest('.track-label')) return
  const rect = timelineRef.value.getBoundingClientRect()
  seekTo((event.clientX - rect.left + timelineRef.value.scrollLeft - trackLabelWidth) / timelineZoom.value)
}

const startPlayheadDrag = () => {
  const move = event => {
    if (!timelineRef.value) return
    const rect = timelineRef.value.getBoundingClientRect()
    seekTo((event.clientX - rect.left + timelineRef.value.scrollLeft - trackLabelWidth) / timelineZoom.value)
  }
  const up = () => {
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', up)
  }
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
}

const startClipDrag = (event, track, clip, mode) => {
  if (track.locked) return
  selectedTimelineClipId.value = clip.id
  dragData.value = {
    mode,
    clip,
    track,
    startX: event.clientX,
    startClipStart: clip.start,
    startDuration: clip.duration,
  }
  window.addEventListener('mousemove', onTimelineMouseMove)
  window.addEventListener('mouseup', stopTimelineDrag, { once: true })
}

const onTimelineMouseMove = event => {
  const data = dragData.value
  if (!data) return
  const delta = (event.clientX - data.startX) / timelineZoom.value
  if (data.mode === 'move') {
    data.clip.start = snapTime(Math.max(0, data.startClipStart + delta))
  }
  if (data.mode === 'resize-left') {
    const newStart = snapTime(Math.max(0, data.startClipStart + delta))
    const rightEdge = data.startClipStart + data.startDuration
    data.clip.start = Math.min(newStart, rightEdge - 0.1)
    data.clip.duration = Math.max(0.1, rightEdge - data.clip.start)
    if (data.clip.type === 'video') syncStoreMomentsFromTimeline()
  }
  if (data.mode === 'resize-right') {
    data.clip.duration = Math.max(0.1, snapTime(data.startDuration + delta))
    if (data.clip.type === 'video') syncStoreMomentsFromTimeline()
  }
}

const stopTimelineDrag = () => {
  if (dragData.value?.clip?.type === 'video') syncStoreMomentsFromTimeline()
  dragData.value = null
  window.removeEventListener('mousemove', onTimelineMouseMove)
}

const splitAtPlayhead = () => {
  if (!selectedTimelineClip.value) return
  const clip = selectedTimelineClip.value
  if (currentTime.value <= clip.start || currentTime.value >= clip.start + clip.duration) return
  const track = tracks.value.find(candidate => candidate.clips.includes(clip))
  const leftDuration = currentTime.value - clip.start
  const rightDuration = clip.duration - leftDuration
  clip.duration = leftDuration
  track.clips.push({
    ...clip,
    id: makeId('clip'),
    start: currentTime.value,
    duration: rightDuration,
    sourceStart: (clip.sourceStart || 0) + leftDuration,
  })
  syncStoreMomentsFromTimeline()
}

const deleteSelected = () => {
  tracks.value.forEach(track => {
    track.clips = track.clips.filter(clip => clip.id !== selectedTimelineClipId.value)
  })
  selectedTimelineClipId.value = ''
  syncStoreMomentsFromTimeline()
}

const scrollTimeline = event => {
  if (!timelineRef.value) return
  timelineRef.value.scrollLeft += event.deltaY + event.deltaX
}

const syncStoreMomentsFromTimeline = () => {
  const videoClips = tracks.value
    .flatMap(track => track.clips)
    .filter(clip => clip.type === 'video')
    .sort((a, b) => a.start - b.start)

  if (!videoClips.length) return
  store.moments = videoClips.map((clip, index) => ({
    id: clip.id,
    start: Number(clip.start.toFixed(3)),
    end: Number((clip.start + clip.duration).toFixed(3)),
    score: 1,
    peak_score: 1,
    reason: clip.name || `Clip ${index + 1}`,
  }))
  store.selectedClipId = selectedTimelineClipId.value || store.moments[0]?.id || ''
}

const exportCurrentProject = async () => {
  syncStoreMomentsFromTimeline()
  await store.exportProject()
}

const runAiTool = async toolId => {
  if (toolId === 'smart-cut') {
    await store.detectKeyMoments()
    return
  }
  if (toolId === 'scene-detect') {
    await analyzeScenes()
    return
  }
  if (toolId === 'captions') {
    await generateCaptions()
    activeRightTab.value = 'captions'
    return
  }
  store.status = 'complete'
  store.statusMessage = 'This AI tool is ready for a backend endpoint.'
  store.progress = 100
}

const analyzeScenes = async () => {
  if (!activeVideoFile.value) return
  store.status = 'processing'
  store.statusMessage = 'Uploading video for scene detection'
  store.progress = 4
  const fd = new FormData()
  fd.append('video', activeVideoFile.value)
  const payload = await apiRequest('/analyze_scenes', { method: 'POST', body: fd })
  const result = await waitForJob(payload.job_id)
  const scenes = Array.isArray(result.scenes) ? result.scenes : []
  store.status = 'complete'
  store.statusMessage = `Detected ${scenes.length} scene(s).`
  store.progress = 100
}

const generateCaptions = async () => {
  if (!activeVideoFile.value) return
  store.status = 'processing'
  store.statusMessage = 'Uploading video for captions'
  store.progress = 4
  const fd = new FormData()
  fd.append('video', activeVideoFile.value)
  fd.append('device', store.whisperDevice)
  fd.append('use_chunking', String(store.smartChunking))
  const payload = await apiRequest('/generate_captions', { method: 'POST', body: fd })
  const result = await waitForJob(payload.job_id)
  captions.value = (Array.isArray(result.segments) ? result.segments : []).map((segment, index) => ({
    id: `caption-${index}`,
    start: Number(segment.start || 0),
    end: Number(segment.end || 0),
    text: String(segment.text || ''),
  }))
  store.status = 'complete'
  store.statusMessage = `Generated ${captions.value.length} caption(s).`
  store.progress = 100
}

const apiRequest = async (path, options) => {
  const response = await fetch(`${API_BASE}${path}`, options)
  const data = await response.json()
  if (!response.ok) throw new Error(data.detail || data.error || 'Request failed.')
  return data
}

const waitForJob = jobId => new Promise((resolve, reject) => {
  const poll = async () => {
    try {
      const response = await fetch(`${API_BASE}/job_status/${jobId}`)
      const job = await response.json()
      if (!response.ok) throw new Error(job.detail || job.error || 'Status check failed.')
      store.progress = Number(job.progress ?? store.progress)
      store.statusMessage = job.message || store.statusMessage
      if (job.state === 'complete') {
        resolve(job.result || {})
        return
      }
      if (job.state === 'error') {
        reject(new Error(job.error || job.message || 'Processing failed.'))
        return
      }
      window.setTimeout(poll, 500)
    } catch (error) {
      reject(error)
    }
  }
  poll()
})

const snapTime = value => {
  const safe = Math.max(0, Number(value) || 0)
  return snapEnabled.value ? Math.round(safe * 10) / 10 : safe
}

const waveHeight = (seed, index, max = 28) => {
  const code = String(seed).split('').reduce((sum, char) => sum + char.charCodeAt(0), 0)
  return 4 + ((code * (index + 3) * 17) % max)
}

const formatTime = (seconds, withMillis = true) => {
  const safe = Math.max(0, Number(seconds) || 0)
  const minutes = Math.floor(safe / 60)
  const wholeSeconds = Math.floor(safe % 60)
  const millis = Math.round((safe - Math.floor(safe)) * 1000)
  return withMillis
    ? `${minutes}:${String(wholeSeconds).padStart(2, '0')}.${String(millis).padStart(3, '0')}`
    : `${minutes}:${String(wholeSeconds).padStart(2, '0')}`
}

const pushHistory = () => {
  history.value.push(JSON.stringify(tracks.value))
  if (history.value.length > 30) history.value.shift()
}

const undo = () => {
  const last = history.value.pop()
  if (!last) return
  future.value.push(JSON.stringify(tracks.value))
  tracks.value = JSON.parse(last)
}

const redo = () => {
  const next = future.value.pop()
  if (!next) return
  history.value.push(JSON.stringify(tracks.value))
  tracks.value = JSON.parse(next)
}

watch(() => store.moments, moments => {
  if (!Array.isArray(moments) || !moments.length || !activeVideoSrc.value) return
  const videoTrack = tracks.value.find(track => track.type === 'video')
  videoTrack.clips = moments.map((moment, index) => ({
    id: moment.id || makeId('clip'),
    type: 'video',
    name: `AI Moment ${index + 1}`,
    url: activeVideoSrc.value,
    start: Number(moment.start || 0),
    duration: Math.max(0.1, Number(moment.end || 0) - Number(moment.start || 0)),
    sourceStart: Number(moment.start || 0),
    ...defaultClipProps(),
  }))
  selectedTimelineClipId.value = videoTrack.clips[0]?.id || ''
}, { deep: true })

onMounted(() => {
  store.loadWhisperCapabilities()
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onTimelineMouseMove)
})
</script>

<style scoped>
:global(*) {
  box-sizing: border-box;
}

:global(body) {
  margin: 0;
  background: #0b0b0d;
  color: #ececf1;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

button,
input {
  font: inherit;
}

button {
  cursor: pointer;
}

.capcut-shell {
  height: 100vh;
  display: grid;
  grid-template-rows: 48px minmax(0, 1fr) 250px;
  background: #0b0b0d;
  color: #ececf1;
  overflow: hidden;
}

.topbar {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) auto minmax(240px, 1fr);
  align-items: center;
  gap: 14px;
  padding: 0 14px;
  background: #101013;
  border-bottom: 1px solid #24242a;
}

.top-left,
.top-center,
.top-right {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.top-center {
  justify-content: center;
}

.top-right {
  justify-content: flex-end;
}

.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 800;
}

.brand-mark {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  background: linear-gradient(135deg, #00e5ff, #e8ff47);
}

.project-name {
  width: min(260px, 40vw);
  border: 1px solid transparent;
  border-radius: 7px;
  padding: 6px 8px;
  background: transparent;
  color: #dcdce2;
  outline: none;
}

.project-name:focus {
  border-color: #30323a;
  background: #17181d;
}

.icon-btn,
.tool-btn,
.playback-btn,
.timeline-btn,
.ratio-chip {
  border: 1px solid #2b2c33;
  border-radius: 7px;
  background: #18191e;
  color: #b8bac3;
  min-height: 30px;
  padding: 0 10px;
}

.icon-btn {
  width: 32px;
  padding: 0;
}

.icon-btn.active,
.playback-btn.active {
  border-color: #00c9d8;
  color: #00e5ff;
}

.divider {
  width: 1px;
  height: 22px;
  background: #2a2b31;
}

.ratio-chip {
  color: #e8ff47;
}

.autosave {
  min-width: 0;
  max-width: 280px;
  overflow: hidden;
  color: #7b7d86;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.export-btn {
  min-height: 34px;
  border: 0;
  border-radius: 8px;
  padding: 0 18px;
  background: #00c9d8;
  color: #081214;
  font-weight: 900;
}

.export-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.editor-body {
  min-height: 0;
  display: grid;
  grid-template-columns: 310px minmax(0, 1fr) 300px;
  background: #0f1012;
}

.left-panel,
.right-panel {
  min-height: 0;
  display: flex;
  background: #141519;
  overflow: hidden;
}

.left-panel {
  border-right: 1px solid #24252b;
}

.right-panel {
  flex-direction: column;
  border-left: 1px solid #24252b;
}

.left-tabs {
  width: 76px;
  padding: 10px 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: #111216;
  border-right: 1px solid #24252b;
}

.left-tab {
  display: grid;
  place-items: center;
  gap: 4px;
  min-height: 58px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: #8d909a;
  font-size: 11px;
}

.left-tab.active {
  background: #1b2730;
  color: #00e5ff;
}

.tab-icon {
  width: 20px;
  height: 20px;
}

.tab-icon :deep(svg),
.tab-icon svg {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
}

.left-content,
.right-content {
  min-width: 0;
  flex: 1;
  overflow-y: auto;
  scrollbar-color: #3a3b42 #17181d;
  scrollbar-width: thin;
}

.panel-page {
  display: grid;
  gap: 12px;
  padding: 14px;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: #f0f0f4;
}

.mini-action {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: #1e2a35;
  color: #58dce8;
  font-size: 12px;
  font-weight: 800;
}

.mini-action input {
  display: none;
}

.media-drop {
  display: grid;
  place-items: center;
  min-height: 66px;
  border: 1px dashed #30323a;
  border-radius: 9px;
  background: #111216;
  color: #747782;
  font-size: 12px;
}

.media-drop.over {
  border-color: #00c9d8;
  color: #00e5ff;
}

.media-grid,
.tile-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.media-card,
.fx-tile,
.preset-card,
.audio-row,
.sticker,
.ai-tool,
.caption-row {
  border: 1px solid #24252b;
  border-radius: 9px;
  background: #191a1f;
  color: #d8d9df;
  text-align: left;
}

.media-card {
  padding: 0;
  overflow: hidden;
}

.media-thumb {
  position: relative;
  display: grid;
  place-items: center;
  height: 72px;
}

.media-type {
  text-transform: uppercase;
  font-size: 11px;
  font-weight: 900;
}

.media-duration {
  position: absolute;
  right: 6px;
  bottom: 5px;
  padding: 2px 5px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.55);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 10px;
}

.media-name {
  display: block;
  padding: 7px 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
}

.empty-panel,
.no-selection {
  grid-column: 1 / -1;
  display: grid;
  gap: 6px;
  place-items: center;
  min-height: 130px;
  padding: 20px;
  color: #6f727c;
  text-align: center;
}

.empty-panel p,
.no-selection p {
  margin: 0;
  font-size: 12px;
}

.preset-card {
  display: grid;
  gap: 4px;
  padding: 13px;
}

.preset-card small,
.audio-row small,
.ai-tool small {
  display: block;
  color: #70737d;
  font-size: 11px;
}

.audio-row {
  display: grid;
  grid-template-columns: 66px 1fr;
  align-items: center;
  gap: 10px;
  padding: 10px;
}

.mini-wave,
.waveform {
  display: flex;
  align-items: center;
  gap: 2px;
}

.mini-wave i,
.waveform i {
  width: 2px;
  border-radius: 2px;
  background: #8f5cff;
}

.fx-tile {
  padding: 0;
  overflow: hidden;
}

.fx-tile span {
  display: grid;
  place-items: center;
  height: 60px;
  color: rgba(255, 255, 255, 0.7);
  font-weight: 900;
}

.fx-tile strong {
  display: block;
  padding: 7px 8px;
  font-size: 11px;
}

.fx-tile.active {
  border-color: #00c9d8;
}

.sticker-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.sticker {
  display: grid;
  place-items: center;
  aspect-ratio: 1;
  font-size: 22px;
}

.preview-area {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: 42px minmax(0, 1fr) 56px;
  background: #0c0d10;
}

.preview-toolbar,
.playback-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
  background: #15161a;
  border-bottom: 1px solid #24252b;
}

.playback-bar {
  border-top: 1px solid #24252b;
  border-bottom: 0;
}

.zoom-control {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 7px;
  background: #1d1e24;
  color: #9ea1aa;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
}

.zoom-control button {
  border: 0;
  background: transparent;
  color: #d7d9df;
}

.time-readout {
  margin-left: auto;
  color: #787b84;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
}

.canvas-wrap {
  min-height: 0;
  display: grid;
  place-items: center;
  overflow: hidden;
  background: radial-gradient(circle at center, #18191d, #090a0c);
}

.canvas-stage {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
}

.canvas-frame {
  transform-origin: center;
  transition: transform 160ms ease;
}

.canvas-inner {
  position: relative;
  overflow: hidden;
  background: #000;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.72), 0 0 0 1px #292a31;
}

.preview-video {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.canvas-placeholder {
  width: 100%;
  height: 100%;
  display: grid;
  place-content: center;
  gap: 8px;
  color: #444852;
  text-align: center;
}

.canvas-element {
  position: absolute;
  z-index: 4;
  padding: 4px 7px;
  border-radius: 5px;
  border: 1px solid transparent;
  white-space: nowrap;
  cursor: move;
  user-select: none;
}

.canvas-element.selected {
  border-color: #00c9d8;
}

.element-outline {
  position: absolute;
  inset: -7px;
  border: 1px dashed #00c9d8;
  pointer-events: none;
}

.play-main {
  min-width: 74px;
  min-height: 36px;
  border: 0;
  border-radius: 999px;
  background: #f3f4f8;
  color: #111216;
  font-weight: 900;
}

.volume-control {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
  color: #858893;
  font-size: 12px;
}

.volume-control input {
  width: 92px;
}

.right-tabs {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-bottom: 1px solid #24252b;
}

.right-tabs button {
  min-height: 42px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: #777a84;
  font-size: 12px;
  font-weight: 800;
}

.right-tabs button.active {
  border-bottom-color: #00c9d8;
  color: #00e5ff;
}

.prop-panel,
.ai-panel,
.caption-panel {
  display: grid;
  gap: 14px;
  padding: 14px;
}

.prop-title {
  padding-bottom: 10px;
  border-bottom: 1px solid #25262d;
  color: #f2f3f8;
  font-weight: 900;
}

.prop-subtitle {
  color: #8b8e97;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 11px;
  font-weight: 900;
}

.prop-row {
  display: grid;
  grid-template-columns: 82px 1fr 42px;
  align-items: center;
  gap: 8px;
  color: #9da0a9;
  font-size: 12px;
}

.prop-row input {
  width: 100%;
  accent-color: #00c9d8;
}

.prop-row em {
  color: #777a84;
  font-style: normal;
  text-align: right;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11px;
}

.ai-tool {
  display: grid;
  grid-template-columns: 34px 1fr;
  align-items: center;
  gap: 10px;
  padding: 11px;
}

.ai-tool > span:first-child {
  display: grid;
  place-items: center;
  min-height: 34px;
  border-radius: 8px;
  background: #1d2933;
  color: #00e5ff;
  font-weight: 900;
}

.ai-status {
  display: grid;
  gap: 7px;
  color: #8b8e97;
  font-size: 12px;
}

.ai-progress {
  height: 5px;
  overflow: hidden;
  border-radius: 999px;
  background: #26272e;
}

.ai-progress span {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #00c9d8, #e8ff47);
}

.caption-generate {
  min-height: 36px;
  border: 0;
  border-radius: 8px;
  background: #1d2933;
  color: #00e5ff;
  font-weight: 900;
}

.caption-generate:disabled {
  opacity: 0.45;
}

.caption-list {
  display: grid;
  gap: 7px;
}

.caption-row {
  display: grid;
  grid-template-columns: 58px 1fr;
  gap: 8px;
  padding: 9px;
}

.caption-row.active {
  border-color: #00c9d8;
}

.caption-row span {
  color: #777a84;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11px;
}

.caption-row strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.timeline-section {
  min-height: 0;
  display: grid;
  grid-template-rows: 42px minmax(0, 1fr);
  background: #141519;
  border-top: 1px solid #24252b;
}

.timeline-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border-bottom: 1px solid #24252b;
}

.timeline-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.timeline-zoom {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #858893;
  font-size: 12px;
}

.timeline-duration {
  margin-left: auto;
  color: #666a74;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
}

.timeline-body {
  position: relative;
  min-height: 0;
  overflow: auto;
  scrollbar-color: #3b3c43 #17181d;
  scrollbar-width: thin;
}

.timeline-ruler {
  position: sticky;
  top: 0;
  z-index: 5;
  height: 28px;
  background: #101115;
  border-bottom: 1px solid #24252b;
}

.ruler-tick {
  position: absolute;
  bottom: 0;
  width: 1px;
  height: 9px;
  background: #3b3c43;
}

.ruler-tick em {
  position: absolute;
  left: 5px;
  top: -14px;
  color: #666a74;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 10px;
  font-style: normal;
}

.playhead {
  position: absolute;
  top: 0;
  bottom: 0;
  z-index: 20;
  width: 1px;
  background: #00e5ff;
  cursor: col-resize;
}

.playhead span {
  position: absolute;
  left: -6px;
  top: 1px;
  width: 12px;
  height: 12px;
  background: #00e5ff;
  clip-path: polygon(50% 100%, 0 0, 100% 0);
}

.tracks {
  display: grid;
  gap: 2px;
  padding: 6px 0 20px;
}

.track-row {
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr);
  min-height: 44px;
}

.track-label {
  position: sticky;
  left: 0;
  z-index: 4;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 8px;
  background: #141519;
  border-right: 1px solid #24252b;
  color: #858893;
  font-size: 12px;
}

.track-icon {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: #1d1e24;
  color: #00e5ff;
  font-weight: 900;
}

.track-label strong {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.track-label button {
  width: 22px;
  height: 22px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: #626670;
  font-size: 10px;
}

.track-label button.active {
  background: #2d2430;
  color: #ffcf5a;
}

.track-lane {
  position: relative;
  min-height: 44px;
  background: #17181d;
  box-shadow: inset 0 -1px 0 #202127;
}

.timeline-clip {
  position: absolute;
  top: 6px;
  bottom: 6px;
  display: flex;
  align-items: center;
  min-width: 8px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 6px;
  overflow: hidden;
  cursor: grab;
}

.timeline-clip.selected {
  border-color: #e8ffff;
  box-shadow: 0 0 0 1px #00c9d8;
}

.timeline-clip.locked {
  opacity: 0.55;
  cursor: not-allowed;
}

.timeline-clip.video {
  background: linear-gradient(90deg, #064c76, #0d6efd);
}

.timeline-clip.audio {
  background: linear-gradient(90deg, #38206f, #8f5cff);
}

.timeline-clip.text,
.timeline-clip.image {
  background: linear-gradient(90deg, #6a4b12, #e6a23c);
}

.clip-title {
  position: relative;
  z-index: 1;
  padding: 0 10px;
  overflow: hidden;
  color: #fff;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  font-weight: 800;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.7);
}

.waveform {
  position: absolute;
  inset: 0;
  padding: 3px 8px;
}

.waveform i {
  background: rgba(255, 255, 255, 0.6);
}

.resize-handle {
  position: absolute;
  top: 0;
  bottom: 0;
  z-index: 3;
  width: 7px;
  border: 0;
  background: transparent;
  cursor: ew-resize;
}

.resize-handle:hover {
  background: rgba(255, 255, 255, 0.35);
}

.resize-handle.left {
  left: 0;
}

.resize-handle.right {
  right: 0;
}

@media (max-width: 1150px) {
  .editor-body {
    grid-template-columns: 260px minmax(0, 1fr);
  }

  .right-panel {
    display: none;
  }
}

@media (max-width: 820px) {
  .capcut-shell {
    grid-template-rows: auto minmax(0, 1fr) 220px;
  }

  .topbar,
  .editor-body {
    grid-template-columns: 1fr;
  }

  .top-center,
  .top-right,
  .left-panel {
    display: none;
  }
}
</style>
