<template>
  <div class="site-shell">
    <header class="global-header">
      <a href="#/" class="logo">
        <span class="logo-mark">◆</span>
        <span>Reel Studio</span>
      </a>
      <nav>
        <a href="#/" :class="{ active: currentRoute === '/' }">Home</a>
        <a href="#/lab" :class="{ active: currentRoute === '/lab' }">Video Lab</a>
      </nav>
    </header>

    <component :is="activeView" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import HomePage from './HomePage.vue'
import VideoLab from './VideoLab.vue'

const currentRoute = ref('/')

const readRoute = () => {
  const hash = window.location.hash.replace('#', '') || '/'
  currentRoute.value = hash === '/lab' ? '/lab' : '/'
}

onMounted(() => {
  if (!window.location.hash) {
    window.location.hash = '#/'
  }
  readRoute()
  window.addEventListener('hashchange', readRoute)
})

onBeforeUnmount(() => window.removeEventListener('hashchange', readRoute))

const activeView = computed(() => (currentRoute.value === '/lab' ? VideoLab : HomePage))
</script>

<style scoped>
.site-shell {
  min-height: 100vh;
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
  background: rgba(20, 18, 16, 0.8);
  backdrop-filter: blur(8px);
}

.logo {
  display: inline-flex;
  gap: 0.45rem;
  align-items: center;
  color: #f6ede3;
  text-decoration: none;
  font-weight: 600;
}

.logo-mark {
  color: #dc8b5e;
}

nav {
  display: flex;
  gap: 0.65rem;
}

nav a {
  color: #dccabd;
  text-decoration: none;
  font-size: 0.9rem;
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 0.35rem 0.75rem;
}

nav a.active {
  border-color: #9f8576;
  color: #fff3e6;
}
</style>
