<script setup lang="ts">
import { useRouter } from 'vue-router';

const router = useRouter();

function goToSettings(tab: string) {
  router.push({ path: '/settings', query: { tab } });
}

function goToHome() {
  router.push('/');
}
</script>

<template>
  <div class="mx-auto max-w-6xl p-5 pb-12 sm:p-8">
    <div class="mb-7 flex flex-wrap items-end justify-between gap-4">
      <div>
        <p class="mb-2 text-[10px] font-bold uppercase tracking-[0.25em] text-cyan-300">Stream Translator</p>
        <h1 class="text-2xl font-black tracking-tight text-white sm:text-3xl">使用教學</h1>
        <p class="mt-2 max-w-2xl text-sm leading-relaxed text-white/55">第一次使用只要準備 ASR 語音模型，再選擇翻譯模型。一般情況下，主畫面會在啟動時自動檢查並提示你。</p>
      </div>
      <button type="button" class="rounded-xl bg-cyan-500 px-4 py-2.5 text-xs font-bold text-slate-950 shadow-lg shadow-cyan-950/30 transition hover:bg-cyan-400" @click="goToHome">回到即時轉譯</button>
    </div>

    <div class="mb-7 grid gap-3 md:grid-cols-4">
      <a href="#quick-start" class="guide-summary-card border-cyan-400/20 bg-cyan-950/20"><span>01</span><strong>快速開始</strong><small>貼網址並啟動翻譯</small></a>
      <a href="#asr" class="guide-summary-card border-indigo-400/20 bg-indigo-950/20"><span>02</span><strong>ASR 模型</strong><small>選擇、下載與用途</small></a>
      <a href="#gemini" class="guide-summary-card border-blue-400/20 bg-blue-950/20"><span>03</span><strong>Gemini API</strong><small>API Key 與雲端翻譯</small></a>
      <a href="#llama" class="guide-summary-card border-emerald-400/20 bg-emerald-950/20"><span>04</span><strong>本地 LLM</strong><small>llama.cpp 與 GGUF 設定</small></a>
    </div>

    <section id="quick-start" class="guide-section">
      <div class="guide-section-heading"><span class="guide-number">01</span><div><h2>快速開始</h2><p>最簡單的使用流程</p></div></div>
      <div class="grid gap-4 md:grid-cols-3">
        <div class="guide-step"><b>1. 選擇音訊來源</b><p>在即時轉譯頁選「URL 串流」，貼上 YouTube Live、Twitch、X、TikTok 或其他支援平台的直播網址。</p></div>
        <div class="guide-step"><b>2. 選擇語言與翻譯模型</b><p>選擇輸入語言、目標語言，勾選「翻譯」，再選 OpenAI、Gemini 或本地 LLM。</p></div>
        <div class="guide-step"><b>3. 按下啟動</b><p>第一次使用若缺 ASR 模型，程式會先提醒、顯示進度並協助下載，完成後自動開始。</p></div>
      </div>
      <div class="guide-note">提示：ASR 是「語音轉文字」，翻譯模型是「文字轉成目標語言」。兩者是不同模型，缺一不可。</div>
    </section>

    <section id="asr" class="guide-section">
      <div class="guide-section-heading"><span class="guide-number">02</span><div><h2>ASR 模型怎麼選</h2><p>ASR = Automatic Speech Recognition，負責把聲音轉成文字</p></div></div>
      <div class="overflow-x-auto rounded-xl border border-white/10">
        <table class="w-full min-w-[680px] text-left text-xs">
          <thead><tr class="border-b border-white/10 bg-white/5 text-white/55"><th class="px-4 py-3">引擎</th><th class="px-4 py-3">適合情境</th><th class="px-4 py-3">優點</th><th class="px-4 py-3">建議</th></tr></thead>
          <tbody class="divide-y divide-white/5 text-white/70">
            <tr><td class="px-4 py-3 font-bold text-cyan-200">Faster-Whisper</td><td class="px-4 py-3">一般多語言、影片與直播</td><td class="px-4 py-3">穩定、模型選擇多</td><td class="px-4 py-3">新手先用 base；GPU 足夠可用 small／large-v3</td></tr>
            <tr><td class="px-4 py-3 font-bold text-cyan-200">Parakeet</td><td class="px-4 py-3">日文或特定語言的即時轉錄</td><td class="px-4 py-3">速度快、適合 sherpa-onnx</td><td class="px-4 py-3">日文直播可優先選 Parakeet</td></tr>
            <tr><td class="px-4 py-3 font-bold text-cyan-200">SenseVoice</td><td class="px-4 py-3">中、英、日等多語言</td><td class="px-4 py-3">體積較小、啟動快</td><td class="px-4 py-3">CPU 電腦或想降低資源使用時適合</td></tr>
            <tr><td class="px-4 py-3 font-bold text-cyan-200">Qwen3-ASR</td><td class="px-4 py-3">需要較新的多語言辨識</td><td class="px-4 py-3">辨識能力較強</td><td class="px-4 py-3">GPU 足夠時選 1.7B；追求速度選 0.6B</td></tr>
            <tr><td class="px-4 py-3 font-bold text-cyan-200">Fun-ASR</td><td class="px-4 py-3">中文、日文與混合語音</td><td class="px-4 py-3">適合特定語音場景</td><td class="px-4 py-3">依畫面顯示的可用模型選擇</td></tr>
          </tbody>
        </table>
      </div>
      <div class="mt-4 grid gap-4 md:grid-cols-2">
        <div class="guide-card"><h3>如何下載 ASR 模型</h3><ol><li>到左側「ASR 模型管理」。</li><li>依目前 Runtime Profile 選擇模型。</li><li>按「下載」，等待進度到 100%。</li><li>回到即時轉譯，選擇同一個引擎與模型。</li></ol><p class="guide-muted">也可以直接在即時轉譯按「啟動」；若模型不存在，程式會提醒並自動下載。</p></div>
        <div class="guide-card"><h3>下載時注意</h3><ul><li>模型檔通常較大，第一次下載需要等待。</li><li>不要在下載中關閉程式或刪除模型資料夾。</li><li>CPU / sherpa-onnx 與 GPU / Python 模型是不同套件，請依畫面建議下載。</li><li>下載完成後會顯示「已下載」，之後不需要重複下載。</li></ul></div>
      </div>
      <button type="button" class="guide-action" @click="goToSettings('model_management')">前往 ASR 模型管理</button>
    </section>

    <section id="gemini" class="guide-section">
      <div class="guide-section-heading"><span class="guide-number">03</span><div><h2>使用 Gemini API 翻譯</h2><p>用 Google AI Studio 的 API Key 進行雲端翻譯</p></div></div>
      <div class="grid gap-4 md:grid-cols-2">
        <div class="guide-card">
          <h3>A. 取得 Gemini API Key</h3>
          <ol>
            <li>登入 <a class="guide-link" href="https://aistudio.google.com/app/apikey" target="_blank" rel="noreferrer">Google AI Studio API Keys</a>。</li>
            <li>按「Create API key」；如果畫面要求選專案，選擇或匯入要使用的 Google Cloud 專案。</li>
            <li>複製新建立的 API Key。API Key 像密碼一樣保管，不要貼到公開文章、截圖或 Git。</li>
          </ol>
          <p class="guide-muted">免費額度、模型可用性與計費規則由 Google 帳戶及專案決定；長時間直播前請先確認配額與帳單設定。</p>
        </div>
        <div class="guide-card">
          <h3>B. 填入程式設定</h3>
          <ol>
            <li>開啟左側「設定」→「翻譯選項」。</li>
            <li>將「翻譯後端」選為「Google Gemini」。</li>
            <li>在「API Key」貼上剛才複製的金鑰；模型名稱保留畫面預設值，或改成帳戶目前可用的 Gemini 模型。API Base URL 保留 <code>https://generativelanguage.googleapis.com/v1beta</code>。</li>
            <li>按右側「測試連線」，看到成功訊息後儲存設定。</li>
          </ol>
        </div>
      </div>
      <div class="guide-card mt-4">
        <h3>C. 開始翻譯</h3>
        <ol>
          <li>回到「即時轉譯」，確認「翻譯」已開啟，並選好輸入語言與目標語言。</li>
          <li>在「翻譯模型／後端」選擇「Google Gemini」，不要同時開啟「使用本地 LLM」。</li>
          <li>按「啟動即時轉譯」；ASR 會先把語音轉成文字，再交給 Gemini 翻譯。</li>
        </ol>
      </div>
      <div class="guide-warning">如果測試失敗，先檢查 API Key 是否完整、模型名稱是否仍可用、網路與 Google 配額是否正常。OpenAI ASR Key、OpenAI GPT 翻譯 Key 與 Gemini Key 是三組不同的金鑰，不能互相代用。</div>
      <button type="button" class="guide-action" @click="goToSettings('translation')">前往 Gemini 翻譯設定</button>
    </section>

    <section id="llama" class="guide-section">
      <div class="guide-section-heading"><span class="guide-number">04</span><div><h2>本地 LLM／llama.cpp 怎麼設定</h2><p>本地 LLM 負責翻譯，不負責語音辨識</p></div></div>
      <div class="grid gap-4 md:grid-cols-2">
        <div class="guide-card"><h3>A. 先準備 llama.cpp Runtime</h3><ol><li>到左側「Llama 執行設定」。</li><li>Runtime 區會自動核對目前版本與官方最新版。</li><li>如果已是最新版本，畫面會顯示「已是最新版本」，不需要再下載。</li><li>如果有新版，選擇依硬體推薦的 CUDA、HIP、Vulkan 或 CPU Runtime。</li><li>等待下載、驗證、安裝完成通知。</li></ol><p class="guide-muted">NVIDIA 通常選 CUDA；AMD 可選 HIP；不確定時使用畫面上的硬體推薦。</p></div>
        <div class="guide-card"><h3>B. 下載並選擇 GGUF 模型</h3><ol><li>到左側「LLM 模型管理」。</li><li>下載或匯入 GGUF 格式模型，例如 Qwen、HY-MT 等。</li><li>回到「Llama 執行設定」，選擇模型檔案。</li><li>保留建議的上下文、執行緒與 GPU layers，先測試能否啟動。</li></ol><p class="guide-muted">模型越大通常翻譯品質越好，但需要更多 VRAM／RAM。第一次建議使用 7B、Q4 量化模型。</p></div>
      </div>
      <div class="guide-card mt-4"><h3>C. 在即時轉譯啟用本地翻譯</h3><ol><li>在即時轉譯頁確認「翻譯」已勾選。</li><li>在「翻譯模型／後端」選擇「Llama（本地）」。</li><li>打開底部「使用本地 LLM」開關。</li><li>看到「服務已就緒」後，再按「啟動即時轉譯」。</li></ol><div class="guide-warning">如果只想使用 OpenAI 或 Gemini，不要開啟本地 LLM；直接在翻譯模型／後端選擇對應服務並設定 API Key。</div></div>
      <button type="button" class="guide-action" @click="goToSettings('llama')">前往 Llama 執行設定</button>
      <button type="button" class="guide-action secondary" @click="router.push('/llm-models')">前往 LLM 模型管理</button>
    </section>

    <section class="guide-section"><div class="guide-section-heading"><span class="guide-number">05</span><div><h2>常見問題</h2><p>遇到問題時先看這裡</p></div></div><div class="grid gap-3 md:grid-cols-2"><details class="guide-faq"><summary>按開始後為什麼要下載模型？</summary><p>模型沒有預先下載時，程式會先建立下載任務。看到進度完成後會自動接續啟動，不需要手動重開。</p></details><details class="guide-faq"><summary>ASR 有了，為什麼沒有翻譯？</summary><p>請確認「翻譯」勾選、目標語言已選擇，並且翻譯後端已設定。使用本地 LLM 時還要確認 llama.cpp 顯示服務已就緒。</p></details><details class="guide-faq"><summary>Gemini 測試連線失敗怎麼辦？</summary><p>回到「設定 → 翻譯選項」，確認後端是 Google Gemini、API Key 沒有多餘空白，模型名稱是帳戶目前可用的模型，再按一次「測試連線」。</p></details><details class="guide-faq"><summary>本地 LLM 啟動失敗怎麼辦？</summary><p>先確認 Runtime 已安裝、GGUF 模型路徑正確，再到 Llama 執行設定按測試。NVIDIA 優先選 CUDA Runtime。</p></details><details class="guide-faq"><summary>模型該選大還是小？</summary><p>先用較小模型確認流程正常，再依 VRAM／RAM 增加模型大小。即時翻譯通常要在品質與延遲之間取平衡。</p></details></div></section>
  </div>
</template>

<style scoped>
.guide-summary-card { display: grid; gap: 2px; border-width: 1px; border-radius: 16px; padding: 16px; transition: transform .2s, background .2s; }
.guide-summary-card:hover { transform: translateY(-2px); background-color: rgba(255,255,255,.08); }
.guide-summary-card span { color: rgba(255,255,255,.4); font-size: 10px; font-weight: 800; letter-spacing: .12em; }
.guide-summary-card strong { color: white; font-size: 15px; }
.guide-summary-card small { color: rgba(255,255,255,.45); font-size: 11px; }
.guide-section { margin-top: 22px; border: 1px solid rgba(255,255,255,.09); border-radius: 20px; background: rgba(2,6,23,.72); padding: 20px; box-shadow: 0 18px 50px rgba(2,6,23,.18); }
.guide-section-heading { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; }
.guide-section-heading h2 { color: white; font-size: 18px; font-weight: 800; }
.guide-section-heading p { color: rgba(255,255,255,.42); font-size: 11px; margin-top: 3px; }
.guide-number { display: inline-flex; width: 34px; height: 34px; align-items: center; justify-content: center; border-radius: 11px; background: rgba(34,211,238,.12); color: #67e8f9; font-size: 11px; font-weight: 900; }
.guide-step, .guide-card { border: 1px solid rgba(255,255,255,.08); border-radius: 14px; background: rgba(255,255,255,.035); padding: 15px; }
.guide-step b, .guide-card h3 { color: rgba(255,255,255,.9); font-size: 13px; }
.guide-step p, .guide-card p, .guide-card li { color: rgba(255,255,255,.58); font-size: 11px; line-height: 1.75; }
.guide-card h3 { margin-bottom: 9px; }
.guide-card ol, .guide-card ul { padding-left: 18px; list-style: decimal; }
.guide-card ul { list-style: disc; }
.guide-card li::marker { color: #67e8f9; }
.guide-muted { margin-top: 10px; color: rgba(103,232,249,.65) !important; }
.guide-note, .guide-warning { margin-top: 16px; border-radius: 12px; background: rgba(34,211,238,.08); padding: 12px 14px; color: rgba(165,243,252,.8); font-size: 11px; line-height: 1.7; }
.guide-warning { background: rgba(251,191,36,.08); color: rgba(253,230,138,.8); }
.guide-action { margin-top: 16px; border-radius: 10px; background: #06b6d4; padding: 10px 14px; color: #082f49; font-size: 11px; font-weight: 800; transition: background .2s; }
.guide-action:hover { background: #22d3ee; }
.guide-action.secondary { margin-left: 8px; background: rgba(255,255,255,.1); color: rgba(255,255,255,.75); }
.guide-action.secondary:hover { background: rgba(255,255,255,.16); }
.guide-link { color: #67e8f9; text-decoration: underline; text-underline-offset: 2px; }
.guide-link:hover { color: #a5f3fc; }
.guide-faq { border: 1px solid rgba(255,255,255,.08); border-radius: 13px; background: rgba(255,255,255,.035); padding: 13px 15px; }
.guide-faq summary { cursor: pointer; color: rgba(255,255,255,.85); font-size: 12px; font-weight: 700; }
.guide-faq p { margin-top: 9px; color: rgba(255,255,255,.55); font-size: 11px; line-height: 1.7; }
</style>
