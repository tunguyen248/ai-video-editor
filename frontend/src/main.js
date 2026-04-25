import { createApp } from 'vue'
import { createPinia } from 'pinia'
import VideoEditor from './VideoEditor.vue'

createApp(VideoEditor).use(createPinia()).mount('#app')
