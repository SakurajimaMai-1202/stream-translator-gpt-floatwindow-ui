<script setup lang="ts">
import { computed, watchEffect, onMounted, onBeforeUnmount } from 'vue';
import { RouterView } from 'vue-router';
import { useRoute, useRouter } from 'vue-router';

const route = useRoute();
const router = useRouter();
const openSubtitleSettings = () => { void router.push('/subtitle-style'); };
onMounted(() => window.addEventListener('native-open-subtitle-settings', openSubtitleSettings));
onBeforeUnmount(() => window.removeEventListener('native-open-subtitle-settings', openSubtitleSettings));
const isTransparentPage = computed(() => {
  const pathname = window.location.pathname.replace(/\/+$/, '') || '/';
  return route.name === 'subtitle' || route.path === '/subtitle' || pathname === '/subtitle';
});

watchEffect(() => {
  const method = isTransparentPage.value ? 'add' : 'remove';
  document.documentElement.classList[method]('transparent-page');
  document.body.classList[method]('transparent-page');
});
</script>

<template>
  <div id="app" :class="{ 'transparent-page': isTransparentPage }">
    <RouterView />
  </div>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body, #app {
  width: 100%;
  height: 100%;
}

html.transparent-page,
body.transparent-page,
#app.transparent-page {
  background: transparent !important;
}
</style>
