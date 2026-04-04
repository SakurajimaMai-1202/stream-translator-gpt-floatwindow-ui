import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './style.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
const pinia = createPinia()

function preventUnexpectedPageZoom() {
    const shouldBlockZoom = (event: KeyboardEvent) => {
        if (!(event.ctrlKey || event.metaKey)) return false;
        const key = event.key;
        return key === '+' || key === '-' || key === '=' || key === '0';
    };

    document.addEventListener('wheel', (event) => {
        if (event.ctrlKey) {
            event.preventDefault();
        }
    }, { passive: false });

    document.addEventListener('keydown', (event) => {
        if (shouldBlockZoom(event)) {
            event.preventDefault();
        }
    });
}

app.use(pinia)
app.use(router)

// 動態注入 Qt WebChannel 腳本以避免 Vite 構建錯誤
if ((window as any).qt || window.location.protocol === 'qrc:') {
    const script = document.createElement('script');
    script.src = 'qrc:///qtwebchannel/qwebchannel.js';
    document.head.appendChild(script);

    // 在桌面版 WebView 中鎖定頁面縮放，避免下拉選單滾動觸發持續放大
    preventUnexpectedPageZoom();
}

app.mount('#app')
