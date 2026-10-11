<script setup lang="ts">
import { useSettingsContext } from '../../composables/settings/settingsContext';
const { localConfig } = useSettingsContext();

</script>

<template>
<div class="settings-paint-section apple-settings">
            <header class="apple-page-header"><h2>輸出選項</h2><p>設定字幕輸出、分享與通知。</p></header>

            <div class="bg-white/5 rounded-xl p-4 border border-white/10 mb-6">
              <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label class="block text-white/70 font-semibold mb-2">輸出目錄</label>
                  <input v-model="localConfig.output.output_dir" type="text" placeholder="./output"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                </div>

                <div>
                  <label class="block text-white/70 font-semibold mb-2">最大歷史紀錄數</label>
                  <input v-model.number="localConfig.output.max_history" type="number" min="5" max="100"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>

                <div class="md:col-span-2">
                  <label class="block text-white/70 font-semibold mb-3">輸出格式</label>
                  <div class="flex flex-wrap gap-6">
                    <label class="flex items-center gap-2 cursor-pointer">
                      <input v-model="localConfig.output.output_srt" type="checkbox" class="w-5 h-5 accent-blue-500" />
                      <span class="text-white">SRT 字幕</span>
                    </label>
                    <label class="flex items-center gap-2 cursor-pointer">
                      <input v-model="localConfig.output.output_txt" type="checkbox" class="w-5 h-5 accent-blue-500" />
                      <span class="text-white">純文字</span>
                    </label>
                    <label class="flex items-center gap-2 cursor-pointer">
                      <input v-model="localConfig.output.output_ass" type="checkbox" class="w-5 h-5 accent-blue-500" />
                      <span class="text-white">ASS 字幕</span>
                    </label>
                  </div>
                </div>

                <div class="md:col-span-2">
                  <label class="block text-white/70 font-semibold mb-2">
                    自訂輸出檔案路徑
                    <span class="text-white/40 font-normal text-xs ml-2">（選填，留空則根據上方目錄與格式自動命名）</span>
                  </label>
                  <input v-model="localConfig.output_notification.output_file_path" type="text"
                    placeholder="例如：F:\subtitle\result.srt（留空則自動生成）"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                  <p class="text-white/40 text-xs mt-1">填寫後以此路徑為準，覆蓋自動生成的路徑。副檔名決定輸出格式（.srt/.txt/.ass）</p>
                </div>

                <div class="md:col-span-2">
                  <label class="flex items-center gap-2 cursor-pointer group">
                    <input v-model="localConfig.output_notification.hide_transcribe_result" type="checkbox" class="w-5 h-5 accent-blue-500" />
                    <div class="flex flex-col">
                      <span class="text-white group-hover:text-blue-300 transition">隱藏 Whisper 轉錄結果</span>
                      <span class="text-white/50 text-xs">開啟後只輸出翻譯結果，不顯示原始轉錄文字</span>
                    </div>
                  </label>
                </div>
              </div>
            </div>

            <!-- 通知設定 -->
            <h3 class="text-lg font-bold text-white mb-4">🔔 通知推播</h3>

            <!-- Discord -->
            <div class="bg-white/5 rounded-xl p-4 border border-white/10 mb-4">
              <div class="flex items-center justify-between mb-4">
                <h4 class="text-blue-300 font-semibold">Discord Webhook</h4>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input v-model="localConfig.output_notification.discord_enabled" type="checkbox" class="w-5 h-5 accent-blue-500" />
                  <span class="text-white">啟用</span>
                </label>
              </div>
              <div>
                <input v-model="localConfig.output_notification.discord_webhook_url" :disabled="!localConfig.output_notification.discord_enabled" type="text" placeholder="https://discord.com/api/webhooks/..."
                  :class="[
                    'w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400',
                    !localConfig.output_notification.discord_enabled ? 'opacity-50 cursor-not-allowed' : ''
                  ]" />
              </div>
            </div>

            <!-- Telegram -->
            <div class="bg-white/5 rounded-xl p-4 border border-white/10">
              <div class="flex items-center justify-between mb-4">
                <h4 class="text-blue-300 font-semibold">Telegram Bot</h4>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input v-model="localConfig.output_notification.telegram_enabled" type="checkbox" class="w-5 h-5 accent-blue-500" />
                  <span class="text-white">啟用</span>
                </label>
              </div>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label class="block text-white/70 text-sm mb-1">Bot Token</label>
                  <input v-model="localConfig.output_notification.telegram_bot_token" :disabled="!localConfig.output_notification.telegram_enabled" type="password" placeholder="123456:ABC-DEF..."
                    :class="[
                      'w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400',
                      !localConfig.output_notification.telegram_enabled ? 'opacity-50 cursor-not-allowed' : ''
                    ]" />
                </div>
                <div>
                  <label class="block text-white/70 text-sm mb-1">Chat ID</label>
                  <input v-model="localConfig.output_notification.telegram_chat_id" :disabled="!localConfig.output_notification.telegram_enabled" type="text" placeholder="@channel_name 或 -123456789"
                    :class="[
                      'w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400',
                      !localConfig.output_notification.telegram_enabled ? 'opacity-50 cursor-not-allowed' : ''
                    ]" />
                </div>
              </div>
            </div>
          </div>
</template>

<style scoped src="./settings-shared.css"></style>
