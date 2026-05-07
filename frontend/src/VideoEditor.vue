<!-- Hash-route shell that switches between the home page and the editor lab. -->
<template>
  <div class="site-shell">
    <header v-if="!immersiveRoute" class="global-header">
      <a href="#/" class="logo">
        <span class="logo-mark">◆</span>
        <span>Alcut Studio</span>
      </a>
      <nav>
        <a href="#/" :class="{ active: currentRoute === '/' }">Home</a>
        <a href="#/lab" :class="{ active: currentRoute === '/lab' }">Video Lab</a>
        <a href="#/builder" :class="{ active: currentRoute === '/builder' }">Template Builder</a>
      </nav>
    </header>

    <component :is="activeView" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import HomePage from './HomePage.vue'
import TemplateBuilder from './TemplateBuilder.vue'
import VideoLab from './VideoLab.vue'

const currentRoute = ref('/')

const readRoute = () => {
  const hash = window.location.hash.replace('#', '') || '/'
  currentRoute.value = ['/lab', '/builder'].includes(hash) ? hash : '/'
}

onMounted(() => {
  if (!window.location.hash) {
    window.location.hash = '#/'
  }
  readRoute()
  window.addEventListener('hashchange', readRoute)
})

onBeforeUnmount(() => window.removeEventListener('hashchange', readRoute))

const immersiveRoute = computed(() => currentRoute.value === '/lab' || currentRoute.value === '/builder')
const activeView = computed(() => {
  if (currentRoute.value === '/lab') return VideoLab
  if (currentRoute.value === '/builder') return TemplateBuilder
  return HomePage
})
</script>

<style scoped>
.site-shell {
  min-height: 100vh;
  background: var(--studio-workspace);
}

.global-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 20;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.8rem 1.2rem;
  background: rgba(10, 10, 10, 0.76);
  border-bottom: 1px solid var(--studio-border);
  backdrop-filter: blur(24px);
}

.logo {
  display: inline-flex;
  gap: 0.45rem;
  align-items: center;
  color: var(--studio-text);
  text-decoration: none;
  font-weight: 600;
}

.logo-mark {
  color: var(--studio-cyan);
  text-shadow: 0 0 18px rgba(34, 211, 238, 0.36);
}

nav {
  display: flex;
  gap: 0.65rem;
}

nav a {
  color: var(--studio-muted);
  text-decoration: none;
  font-size: 0.9rem;
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 0.35rem 0.75rem;
}

nav a.active {
  border-color: rgba(34, 211, 238, 0.34);
  color: var(--studio-cyan-hot);
  background: rgba(34, 211, 238, 0.08);
  box-shadow: var(--studio-shadow-cyan);
}
</style>
