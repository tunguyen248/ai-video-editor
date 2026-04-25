<template>
  <component :is="currentPage" />
</template>

<script setup>
import HomePage from './HomePage.vue'
import VideoLab from './VideoLab.vue'

const path = window.location.pathname.toLowerCase()
const currentPage = path.startsWith('/lab') ? VideoLab : HomePage
</script>
