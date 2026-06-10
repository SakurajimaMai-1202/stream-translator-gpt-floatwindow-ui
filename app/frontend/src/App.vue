<script setup lang="ts">
import { computed, watchEffect } from 'vue';
import { RouterView } from 'vue-router';
import { useRoute } from 'vue-router';

const route = useRoute();
const isTransparentPage = computed(() => {
  return route.name === 'subtitle' || route.path === '/subtitle' || window.location.pathname.endsWith('/subtitle') || window.location.pathname.includes('/subtitle');
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
