import type { WindowWithPyQt } from './homeContext';

export async function writeTextToClipboard(text: string): Promise<boolean> {
  const win = window as WindowWithPyQt;

  // 1) 桌面版 bridge（PyQt QWebChannel）
  //    QWebChannel slot 用 callback 方式回傳結果，需要包成 Promise
  if (win.pyqt?.copyToClipboard) {
    try {
      const result = await new Promise<boolean>((resolve) => {
        win.pyqt!.copyToClipboard!(text, (ok: boolean) => resolve(ok));
      });
      if (result) return true;
    } catch (error) {
      console.warn('[copyLink] pyqt.copyToClipboard failed:', error);
    }
  }

  // 2) 標準 Clipboard API（需要 HTTPS 或 localhost）
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (error) {
      console.warn('[copyLink] navigator.clipboard.writeText failed:', error);
    }
  }

  // 3) 備援：execCommand('copy')
  try {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.setAttribute('readonly', '');
    textArea.style.position = 'fixed';
    textArea.style.left = '-9999px';
    textArea.style.top = '0';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();

    const successful = document.execCommand('copy');
    document.body.removeChild(textArea);
    return successful;
  } catch (error) {
    console.warn('[copyLink] execCommand fallback failed:', error);
    return false;
  }
}
