import os
import queue
import requests

from .common import TranslationTask, LoopWorkerBase, sec2str, start_daemon_thread, BOLD, ENDC


class ResultExporter(LoopWorkerBase):

    def __init__(self, cqhttp_url: str, cqhttp_token: str, discord_webhook_url: str, telegram_token: str,
                 telegram_chat_id: int, output_file_path: str, proxy: str, output_whisper_result: bool,
                 output_timestamps: bool, gui_callback=None) -> None:
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        self.cqhttp_queue = None
        self.discord_queue = None
        self.telegram_queue = None
        self.file_queue = None
        self.output_whisper_result = output_whisper_result
        self.output_timestamps = output_timestamps
        self.output_file_path = output_file_path  # 保留以判斷是否為 SRT
        self.gui_callback = gui_callback  # GUI 回呼函式

        if cqhttp_url:
            self.cqhttp_queue = queue.SimpleQueue()
            start_daemon_thread(self._send_message_to_cqhttp, url=cqhttp_url, token=cqhttp_token)
        if discord_webhook_url:
            self.discord_queue = queue.SimpleQueue()
            start_daemon_thread(self._send_message_to_discord, webhook_url=discord_webhook_url)
        if telegram_token and telegram_chat_id:
            self.telegram_queue = queue.SimpleQueue()
            start_daemon_thread(self._send_message_to_telegram, token=telegram_token, chat_id=telegram_chat_id)
        if output_file_path:
            self.file_queue = queue.SimpleQueue()
            self._file_counter = 0
            start_daemon_thread(self._write_message_to_file, file_path=output_file_path)

    def _send_message_to_cqhttp(self, url: str, token: str):
        headers = {'Authorization': f'Bearer {token}'} if token else None
        while True:
            text = self.cqhttp_queue.get()
            if text is None:
                break
            data = {'message': text}
            try:
                requests.post(url, headers=headers, data=data, timeout=10, proxies=self.proxies)
            except Exception as e:
                print(e)

    def _send_message_to_discord(self, webhook_url: str):
        while True:
            text = self.discord_queue.get()
            if text is None:
                break
            try:
                chunks = []
                for line in text.split('\n'):
                    if not line:
                        continue
                    while len(line) > 1900:
                        chunks.append(line[:1900])
                        line = line[1900:]
                    chunks.append(line)
                if not chunks:
                    chunks = ['\u200b']
                for sub_text in chunks:
                    data = {'content': sub_text}
                    response = requests.post(webhook_url, json=data, timeout=10, proxies=self.proxies)
                    if response.status_code >= 300:
                        print(f"Discord webhook failed: {response.status_code} {response.text}")
            except Exception as e:
                print(f"Discord webhook error: {e}")

    def _send_message_to_telegram(self, token: str, chat_id: int):
        while True:
            text = self.telegram_queue.get()
            if text is None:
                break
            url = f'https://api.telegram.org/bot{token}/sendMessage?chat_id={chat_id}&text={text}'
            try:
                requests.post(url, timeout=10, proxies=self.proxies)
            except Exception as e:
                print(e)

    def _write_message_to_file(self, file_path: str):
        is_srt = file_path.lower().endswith('.srt')
        if file_path:
            if os.path.exists(file_path):
                os.remove(file_path)
        while True:
            text = self.file_queue.get()
            if text is None:
                break
            with open(file_path, 'a', encoding='utf-8') as f:
                if is_srt:
                    self._file_counter += 1
                    f.write(f'{self._file_counter}\n{text}\n\n')
                else:
                    f.write(text + '\n\n')

    def loop(self, input_queue: queue.SimpleQueue[TranslationTask]):
        while True:
            task = input_queue.get()
            if task is None:
                if self.cqhttp_queue:
                    self.cqhttp_queue.put(None)
                if self.discord_queue:
                    self.discord_queue.put(None)
                if self.telegram_queue:
                    self.telegram_queue.put(None)
                if self.file_queue:
                    self.file_queue.put(None)
                break
            
            # GUI 回呼（新增）
            if self.gui_callback:
                try:
                    self.gui_callback(task)
                except Exception as e:
                    print(f"GUI callback error: {e}")
            
            timestamp_text = f'{sec2str(task.time_range[0])} --> {sec2str(task.time_range[1])}'
            text_to_send = (task.transcript + '\n') if self.output_whisper_result else ''
            if self.output_timestamps:
                text_to_send = timestamp_text + '\n' + text_to_send
            
            # 調試：檢查翻譯結果
            if task.translation:
                text_to_print = task.translation
                if self.output_timestamps:
                    text_to_print = timestamp_text + ' ' + text_to_print
                text_to_print = text_to_print.strip()
                print(f'{BOLD}{text_to_print}{ENDC}', flush=True)
                text_to_send += task.translation
            elif task.transcript:
                # 如果有轉錄但沒有翻譯，輸出警告
                print(f'[DEBUG] 轉錄文字: {task.transcript[:50]}... | 翻譯結果: {task.translation}', flush=True)
            text_to_send = text_to_send.strip()
            if self.cqhttp_queue:
                self.cqhttp_queue.put(text_to_send)
            if self.discord_queue:
                self.discord_queue.put(text_to_send)
            if self.telegram_queue:
                self.telegram_queue.put(text_to_send)
            if self.file_queue:
                # SRT 格式強制包含時間戳（不受 output_timestamps 旗標影響）
                is_srt = self.output_file_path and self.output_file_path.lower().endswith('.srt')
                if is_srt and not self.output_timestamps:
                    text_to_file = timestamp_text + '\n'
                    text_to_file += (task.transcript + '\n') if self.output_whisper_result else ''
                    if task.translation:
                        text_to_file += task.translation
                    text_to_file = text_to_file.strip()
                else:
                    text_to_file = text_to_send
                self.file_queue.put(text_to_file)
