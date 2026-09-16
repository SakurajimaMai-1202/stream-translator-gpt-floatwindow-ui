<script setup lang="ts">
defineProps<{ name: string }>();
</script>

<template>
  <svg class="app-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <template v-if="name === 'home'"><path d="M4 5h16v14H4z"/><path d="m7 13 2-3 2.5 6 2.5-8 2 5h2"/></template>
    <template v-else-if="name === 'subtitle-style'"><path d="M4 5h16v12H9l-4 3v-3H4z"/><path d="M8 9h8M8 13h5"/></template>
    <template v-else-if="name === 'guide'"><path d="M5 4h10a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z"/><path d="M8 8h7M8 12h7"/></template>
    <template v-else-if="name === 'general'"><circle cx="12" cy="12" r="3"/><path d="M19 13.5v-3l-2-.7-.5-1.2.9-1.9-2.1-2.1-1.9.9-1.2-.5-.7-2h-3l-.7 2-1.2.5-1.9-.9-2.1 2.1.9 1.9-.5 1.2-2 .7v3l2 .7.5 1.2-.9 1.9 2.1 2.1 1.9-.9 1.2.5.7 2h3l.7-2 1.2-.5 1.9.9 2.1-2.1-.9-1.9.5-1.2z"/></template>
    <template v-else-if="name === 'input'"><path d="M4 4h11v16H4z"/><path d="M9 12h11M16 8l4 4-4 4"/></template>
    <template v-else-if="name === 'output'"><path d="M9 4h11v16H9z"/><path d="M15 12H3M7 8l-4 4 4 4"/></template>
    <template v-else-if="name === 'audio_vad'"><path d="M4 13h2l2-5 3 9 3-11 3 7h3"/></template>
    <template v-else-if="name === 'transcription'"><rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/></template>
    <template v-else-if="name === 'model_management'"><path d="m12 3 8 4-8 4-8-4zM4 7v10l8 4 8-4V7M12 11v10"/></template>
    <template v-else-if="name === 'translation'"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></template>
    <template v-else-if="name === 'llama'"><path d="M7 20v-8l2-3V5l2-2 2 2h3l2 3v12M7 14H4v6M18 14h2v6M10 9h.01M15 9h.01"/></template>
    <template v-else-if="name === 'llm-models'"><path d="M8 4a3 3 0 0 0-3 3v2a3 3 0 0 0 0 6v2a3 3 0 0 0 5 2 3 3 0 0 0 2-3V7a3 3 0 0 0-4-3zM16 4a3 3 0 0 1 3 3v2a3 3 0 0 1 0 6v2a3 3 0 0 1-5 2 3 3 0 0 1-2-3V7a3 3 0 0 1 4-3z"/></template>
    <template v-else-if="name === 'translation-models'"><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8"/><circle cx="12" cy="12" r="3"/></template>
    <template v-else-if="name === 'url'"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></template>
    <template v-else-if="name === 'file'"><path d="M4 4h6l2 3h8v13H4z"/></template>
    <template v-else-if="name === 'microphone'"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/></template>
    <template v-else-if="name === 'system-audio'"><path d="M4 10h4l5-4v12l-5-4H4zM16 9a4 4 0 0 1 0 6M18 6a8 8 0 0 1 0 12"/></template>
    <template v-else-if="name === 'brain'"><path d="M8 4a3 3 0 0 0-3 3v2a3 3 0 0 0 0 6v2a3 3 0 0 0 5 2 3 3 0 0 0 2-3V7a3 3 0 0 0-4-3zM16 4a3 3 0 0 1 3 3v2a3 3 0 0 1 0 6v2a3 3 0 0 1-5 2 3 3 0 0 1-2-3V7a3 3 0 0 1 4-3z"/></template>
    <template v-else-if="name === 'download'"><path d="M12 3v12M7 10l5 5 5-5M4 20h16"/></template>
    <template v-else-if="name === 'play'"><path d="m8 5 11 7-11 7z"/></template>
    <template v-else-if="name === 'stop'"><rect x="6" y="6" width="12" height="12" rx="1"/></template>
    <template v-else-if="name === 'refresh'"><path d="M20 6v5h-5M4 18v-5h5M18 9a7 7 0 0 0-12-2M6 15a7 7 0 0 0 12 2"/></template>
    <template v-else-if="name === 'log'"><path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5"/></template>
    <template v-else-if="name === 'trash'"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5"/></template>
    <template v-else-if="name === 'desktop'"><rect x="3" y="4" width="18" height="12" rx="1"/><path d="M8 20h8M12 16v4"/></template>
    <template v-else-if="name === 'mobile'"><rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/></template>
    <template v-else-if="name === 'warning'"><path d="m12 3 10 18H2zM12 9v5M12 18h.01"/></template>
    <template v-else><path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5"/></template>
  </svg>
</template>
