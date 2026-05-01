// Vue application bootstrap: installs Pinia and mounts the editor shell.
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import VideoEditor from './VideoEditor.vue'
import './styles/theme.css'

createApp(VideoEditor).use(createPinia()).mount('#app')
