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

function loadQtWebChannel(): Promise<void> {
    if ((window as any).QWebChannel) return Promise.resolve();

    return new Promise((resolve, reject) => {
        const existing = document.querySelector<HTMLScriptElement>('script[data-qt-webchannel]');
        if (existing) {
            existing.addEventListener('load', () => resolve(), { once: true });
            existing.addEventListener('error', () => reject(new Error('Qt WebChannel script failed to load')), { once: true });
            return;
        }

        const script = document.createElement('script');
        script.src = 'qrc:///qtwebchannel/qwebchannel.js';
        script.dataset.qtWebchannel = 'true';
        script.onload = () => resolve();
        script.onerror = () => reject(new Error('Qt WebChannel script failed to load'));
        document.head.appendChild(script);
    });
}

async function bootstrap() {
    const isQtWebView = !!(window as any).qt || window.location.protocol === 'qrc:';
    if (isQtWebView) {
        try {
            await Promise.race([
                loadQtWebChannel(),
                new Promise<void>((resolve) => window.setTimeout(resolve, 900)),
            ]);
        } catch (error) {
            console.error('Qt WebChannel 初始化腳本載入失敗:', error);
        }

        // 在桌面版 WebView 中鎖定頁面縮放，避免下拉選單滾動觸發持續放大
        preventUnexpectedPageZoom();
    }

    app.mount('#app');
}

void bootstrap();
