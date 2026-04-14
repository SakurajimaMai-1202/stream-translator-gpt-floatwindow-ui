"""
配置管理系統 (Backend Port)
提供 YAML 配置的讀取、儲存、驗證與視窗狀態管理
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
import copy
from backend.config import settings

class ConfigManager:
    """配置管理器 - 處理所有配置相關操作"""
    
    DEFAULT_CONFIG = {
        'general': {
            'openai_api_key': '',
            'google_api_key': '',
            'log_level': 'INFO'
        },
        'server': {
            'public_port': 8765,
            'enable_subtitle_sharing': True,
        },
        'input': {
            'input_source': 'url',
            'url': '',
            'format': 'ba/wa*',
            'cookies': '',
            'proxy': '',
            'source_type': 'youtube',
            'timeout': 30,
            'device_recording_interval': 0.5,  # 音訊錄音間隔(秒)，建議範圍 0.1~1.0
            'audio_source': 'url',
            'device_index': None,
        },
        'audio_slicing_vad': {
            'min_audio_length': 0.5,
            'max_audio_length': 30.0,
            'target_audio_length': 5.0,
            'continuous_no_speech_threshold': 1.0,
            'disable_dynamic_no_speech_threshold': False,
            'vad_threshold': 0.35,
            'disable_dynamic_vad_threshold': False,
            'prefix_retention_length': 0.5,
            'chunk_gap_threshold': 0.5,
            'vad_enabled': True,
            'vad_neg_threshold': 0.35,
            'vad_min_speech_duration_ms': 250,
            'vad_min_silence_duration_ms': 100,
            'vad_window_size_samples': 512,
            'vad_speech_pad_ms': 30,
            'vad_every_n_frames': 2,
            'realtime_processing': False
        },
        'transcription': {
            'backend': 'qwen3-asr',
            'model': 'Qwen/Qwen3-ASR-1.7B',
            'language': 'auto',
            'filters': [],
            'use_faster_whisper': False,
            'use_simul_streaming': False,
            'simul_streaming_encoder': 'whisper',
            'use_openai_transcription_api': False,
            'use_qwen3_asr': True,
            'qwen3_asr_model': 'Qwen/Qwen3-ASR-1.7B',
            'qwen3_dtype': 'bfloat16',
            'qwen3_load_in_4bit': False,
            'openai_transcription_model': 'whisper-1',
            'whisper_filters': [],
            'disable_transcription_context': False,
            'transcription_initial_prompt': ''
        },
        'translation': {
            'backend': 'custom:localllm',
            'model': 'localllm',
            'translation_prompt': '翻譯成繁體中文',
            'target_language': '繁體中文',
            'history_size': 0,
            'timeout': 10,
            'gpt_model': 'localllm',
            'gemini_model': 'gemini-2.0-flash-exp',
            'translation_history_size': 0,
            'translation_timeout': 10,
            'gpt_base_url': 'http://127.0.0.1:8080',
            'gemini_base_url': '',
            'processing_proxy': '',
            'use_json_result': False,
            'retry_if_translation_fails': True,
            'api_key': '',
            'use_smart_prompt': True,
            'smart_prompt_enabled': True,
            'custom_models': [
                {
                    'name': 'localllm',
                    'base_url': 'http://127.0.0.1:8080',
                    'api_key': '114514',
                    'model_name': 'localllm'
                }
            ]
        },
        'terminology': {
            'use_terminology_glossary': False,
            'terminology_glossary': {},
            'glossary': '',
            'glossary_list': [],
        },
        'output': {
            'output_file': '',
            'show_timestamp': True,
            'hide_transcript': False,
            'cqhttp_url': '',
            'cqhttp_token': '',
            'output_dir': './output',
            'output_srt': True,
            'output_txt': False,
            'output_ass': False,
            'max_history': 20,
        },
        'output_notification': {
            'output_proxy': '',
            'discord_enabled': False,
            'discord_webhook_url': '',
            'telegram_enabled': False,
            'telegram_bot_token': '',
            'telegram_chat_id': '',
            'output_file_path': '',
            'output_timestamps': True,
            'hide_transcribe_result': False
        },
        'subtitle_settings': {
            'fontSize': 24,
            'fontWeight': 700,
            'opacity': 100,
            'showOriginal': True,
            'showTranslated': True,
            'showTimestamp': False,
            'position': 'bottom',
            'autoScroll': True,
            'maxDisplayCount': 5,
            'textColor': '#FFFFFF',
            'translatedColor': '#FFDD00',
            'timestampColor': '#888888',
            'backgroundColor': '#000000',
            'backgroundOpacity': 50
        },
        'ui': {
            'theme': 'light',
            'transparency': 80,
            'font_size': 16,
            'font_name': 'Arial',
            'show_timestamp_in_subtitle': True,
            'max_history': 50,
            'transcript_color': 'rgba(255, 255, 255, 0.6)',
            'translation_color': '#ffffff',
            'background_color': {
                'custom': 'rgba(0, 0, 0, 1)'
            },
            'blur_enabled': False,
            'bg_opacity': 75,
            'windows': {
                'home': {'x': 100, 'y': 100, 'width': 600, 'height': 500, 'visible': True},
                'settings': {'x': 150, 'y': 150, 'width': 800, 'height': 600, 'visible': False},
                'floating_subtitle': {'x': 200, 'y': 200, 'width': 800, 'height': 200, 'visible': True, 'transparency': 80}
            }
        },
        'llama': {
            'model_dir': '',
            'model_path': '',
            'selected_preset': '',
            'default_preset': '',
            'host': '127.0.0.1',
            'port': 8080,
            'n_ctx': 2048,
            'n_gpu_layers': 0,
            'n_threads': 4,
            'n_parallel': 1,
            'top_k': 40,
            'top_p': 0.95,
            'temp': 0.8,
            'repeat_penalty': 1.1,
            'n_predict': 512,
            'flash_attn': True,
            'no_mmap': False,
            'custom_presets': {},  # 用戶自訂配置
            'custom_model_series': [],
        }
    }
    
    def __init__(self, config_path: Path = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置檔案路徑
        """
        self.config_path = config_path if config_path else settings.CONFIG_FILE
        self.config = self._load_or_create()
    
    def _load_or_create(self) -> Dict[str, Any]:
        """載入配置，若不存在則建立預設值"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
                    # 與預設值合併（新增遺漏的欄位）
                    merged = self._merge_with_defaults(config)
                    # 舊版設定遷移（例如 localllm -> llama）
                    migrated, changed = self._migrate_legacy_config(merged)
                    if changed:
                        self._save(migrated)
                    return migrated
            except Exception as e:
                print(f"配置載入失敗: {e}，使用預設值")
                return self._deep_copy(self.DEFAULT_CONFIG)
        else:
            # 首次執行，建立預設配置
            default = self._deep_copy(self.DEFAULT_CONFIG)
            self._save(default)
            return default
    
    def _deep_copy(self, obj: Any) -> Any:
        """深度複製物件"""
        return copy.deepcopy(obj)
    
    def _merge_with_defaults(self, config: Dict) -> Dict:
        """遞迴合併使用者配置與預設值"""
        def merge(default: Dict, user: Dict) -> Dict:
            result = self._deep_copy(default)
            for key, value in user.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = merge(result[key], value)
                elif key in result: # 只合併存在的 key，避免舊配置殘留無用欄位，但這裡我們先保留所有以防萬一
                    result[key] = self._deep_copy(value)
                else:
                    # 使用者配置中有但預設值沒有的 key，保留它 (可能是新插件或自訂欄位)
                    result[key] = self._deep_copy(value)
            return result
        
        return merge(self.DEFAULT_CONFIG, config)

    def _migrate_legacy_config(self, config: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
        """遷移舊版配置到新版欄位/枚舉值。回傳 (config, 是否有變更)"""
        changed = False
        translation = config.get('translation', {})
        backend = str(translation.get('backend', '') or '').strip().lower()

        # 舊版本曾使用 localllm/localllm，統一遷移為 llama
        # 注意：custom:localllm 代表使用者自訂模型，不應強制改成 llama，
        # 否則前端「自訂模型設定」區塊會被隱藏。
        legacy_backends = {
            'localllm',
            'local-llm',
        }
        if backend in legacy_backends:
            translation['backend'] = 'llama'
            config['translation'] = translation
            changed = True

        return config, changed
    
    def save(self):
        """儲存當前配置到檔案"""
        self._save(self.config)
    
    def _save(self, config: Dict):
        """內部儲存方法"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        except Exception as e:
            print(f"配置儲存失敗: {e}")
    
    def get_config(self) -> Dict[str, Any]:
        """獲取完整配置"""
        return self.config

    def _resolve_translation_api_keys(self, config: Dict[str, Any]) -> Dict[str, str]:
        """
        解析翻譯 API 金鑰優先級

        優先級：
        1) translation.api_key（若有填寫，僅覆蓋當前 translation.backend 對應服務）
        2) general.openai_api_key / general.google_api_key
        """
        translation_config = config.get('translation', {})
        general_config = config.get('general', {})

        backend = translation_config.get('backend', '')
        override_key = str(translation_config.get('api_key', '') or '').strip()

        resolved_openai_key = str(general_config.get('openai_api_key', '') or '').strip()
        resolved_google_key = str(general_config.get('google_api_key', '') or '').strip()

        if override_key:
            if backend == 'gemini':
                resolved_google_key = override_key
            elif not str(backend).startswith('custom:'):
                resolved_openai_key = override_key

        return {
            'openai_api_key': resolved_openai_key,
            'google_api_key': resolved_google_key,
        }

    def get_config_status(self) -> List[Dict[str, Any]]:
        """
        檢查配置的健康狀態
        
        Returns:
            警告列表，每個警告包含 level, message, action, page
        """
        warnings = []
        
        # 檢查 API 金鑰（使用與執行階段一致的解析規則）
        resolved_api_keys = self._resolve_translation_api_keys(self.config)
        translation_backend = self.config.get('translation', {}).get('backend', '')

        if not resolved_api_keys.get('openai_api_key') and translation_backend == 'gpt':
            warnings.append({
                'level': 'error',
                'message': 'OpenAI API 金鑰未設定',
                'action': 'setting', # 前端動作標識
                'page': 'general'
            })
        
        if not resolved_api_keys.get('google_api_key') and translation_backend == 'gemini':
            warnings.append({
                'level': 'error',
                'message': 'Google API 金鑰未設定',
                'action': 'setting',
                'page': 'general'
            })
        
        # 檢查輸入設定
        if self.config['input']['input_source'] == 'url' and not self.config['input'].get('url'):
            warnings.append({
                'level': 'warning',
                'message': 'URL 未填入',
                'action': 'focus_url',
                'page': None
            })
        
        # 檢查翻譯設定
        if self.config['translation']['backend'] != 'none' and \
           not self.config['translation'].get('translation_prompt'):
            warnings.append({
                'level': 'warning',
                'message': '翻譯提示詞未設定',
                'action': 'setting',
                'page': 'translation'
            })
        
        return warnings
    
    def save_window_state(self, window_name: str, state: Dict[str, Any]):
        """
        保存視窗狀態到配置 (API 版本)
        
        Args:
            window_name: 視窗名稱 (home/settings/floating_subtitle)
            state: 視窗狀態字典 {'x', 'y', 'width', 'height', 'visible', 'transparency'(opt)}
        """
        if 'ui' not in self.config:
            self.config['ui'] = {'windows': {}}
        if 'windows' not in self.config['ui']:
            self.config['ui']['windows'] = {}
        
        # 合併現有狀態與新狀態 (避免覆蓋未傳遞的字段)
        current_state = self.config['ui']['windows'].get(window_name, {})
        current_state.update(state)
        
        self.config['ui']['windows'][window_name] = current_state
        self.save()
    
    def load_window_state(self, window_name: str) -> Dict[str, Any]:
        """從配置載入視窗狀態"""
        default_states = self.DEFAULT_CONFIG['ui']['windows']
        
        if 'ui' not in self.config or 'windows' not in self.config['ui']:
            return default_states.get(window_name, {})
        
        return self.config['ui']['windows'].get(window_name, default_states.get(window_name, {}))
    
    def to_main_args(self, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        轉換配置為 stream_translator_gpt.main.main() 函式參數
        
        Args:
            config: 可選的配置字典，若未提供則使用 self.config
            
        Returns:
            參數字典
        """
        if config is None:
            config = self.config
        
        # 處理音訊來源
        input_config = config.get('input', {})
        audio_source = input_config.get('audio_source', 'url')
        
        # 根據音訊來源決定 URL 參數
        url = ''
        loopback = False
        use_loopback = False
        
        if audio_source == 'system_audio':
            url = 'loopback'
            loopback = True
        elif audio_source == 'microphone':
            url = 'device'
            use_loopback = False
        elif audio_source in ['url', 'file']:
            url = input_config.get('url', '')
        else:
            # 預設使用 URL
            url = input_config.get('url', '')
        
        transcription_backend = config['transcription'].get('backend', 'faster-whisper')
        # Qwen3-ASR 使用獨立模型欄位，其他後端沿用一般 model 欄位
        transcription_model = (
            config['transcription'].get('qwen3_asr_model')
            if transcription_backend == 'qwen3-asr'
            else config['transcription'].get('model', 'base')
        )

        # 基本參數對映
        args = {
            # 輸入
            'url': url,
            'loopback': loopback,
            'use_loopback': use_loopback,
            'proxy': '',  # 全域代理
            'format': input_config.get('format', 'ba/wa*'),
            'cookies': input_config.get('cookies', ''),
            'input_proxy': input_config.get('proxy', ''),
            'device_index': input_config.get('device_index'),
            'device_recording_interval': input_config.get('device_recording_interval', 0.05),
            
            # 音頻切片
            'min_audio_length': config.get('audio_slicing_vad', {}).get('min_audio_length', 0.5),
            'max_audio_length': config.get('audio_slicing_vad', {}).get('max_audio_length', 30.0),
            'target_audio_length': config.get('audio_slicing_vad', {}).get('target_audio_length', 5.0),
            'continuous_no_speech_threshold': config.get('audio_slicing_vad', {}).get('continuous_no_speech_threshold', 1.0),
            'disable_dynamic_no_speech_threshold': config.get('audio_slicing_vad', {}).get('disable_dynamic_no_speech_threshold', False),
            'vad_threshold': config.get('audio_slicing_vad', {}).get('vad_threshold', 0.35),
            'disable_dynamic_vad_threshold': config.get('audio_slicing_vad', {}).get('disable_dynamic_vad_threshold', False),
            'prefix_retention_length': config.get('audio_slicing_vad', {}).get('prefix_retention_length', 0.5),
            'vad_every_n_frames': config.get('audio_slicing_vad', {}).get('vad_every_n_frames', 2),
            'realtime_processing': config.get('audio_slicing_vad', {}).get('realtime_processing', False),
            
            # 語音轉文字
            'model': transcription_model,
            'language': config['transcription'].get('language', 'auto'),
            'use_faster_whisper': transcription_backend == 'faster-whisper',
            'use_simul_streaming': 'simul' in transcription_backend,
            'use_openai_transcription_api': transcription_backend == 'openai-api',
            'use_qwen3_asr': transcription_backend == 'qwen3-asr',
            'openai_transcription_model': config['transcription'].get('openai_model', 'whisper-1'),
            'whisper_filters': config['transcription'].get('whisper_filters', []),
            'disable_transcription_context': config['transcription'].get('disable_transcription_context', False),
            'transcription_initial_prompt': config['transcription'].get('transcription_initial_prompt', ''),
            'qwen3_dtype': config['transcription'].get('qwen3_dtype', 'bfloat16'),
            'qwen3_load_in_4bit': config['transcription'].get('qwen3_load_in_4bit', False),
        }
        
        # Qwen3-ASR 語言格式轉換：短碼 → 完整名稱
        if transcription_backend == 'qwen3-asr':
            qwen3_lang_map = {
                'ja': 'Japanese', 'en': 'English', 'zh': 'Chinese',
                'ko': 'Korean', 'fr': 'French', 'de': 'German',
                'es': 'Spanish', 'pt': 'Portuguese', 'ru': 'Russian',
                'it': 'Italian', 'ar': 'Arabic', 'th': 'Thai',
                'vi': 'Vietnamese', 'id': 'Indonesian', 'tr': 'Turkish',
                'hi': 'Hindi', 'ms': 'Malay', 'nl': 'Dutch',
                'sv': 'Swedish', 'da': 'Danish', 'fi': 'Finnish',
                'pl': 'Polish', 'cs': 'Czech', 'el': 'Greek',
                'ro': 'Romanian', 'hu': 'Hungarian',
                'auto': '',  # Qwen3-ASR 不支援 auto，傳空字串讓它自動偵測
            }
            raw_lang = str(args.get('language', 'auto') or 'auto').strip()
            normalized_lang = raw_lang.lower()
            args['language'] = qwen3_lang_map.get(normalized_lang, raw_lang)
        
        # Qwen3-ASR 上下文處理 (術語表整合)
        if transcription_backend == 'qwen3-asr':
            use_glossary = config.get('terminology', {}).get('use_terminology_glossary', False)
            terminology_config = config.get('terminology', {})
            glossary = terminology_config.get('terminology_glossary', {})
            glossary_list = terminology_config.get('glossary_list', [])
            # 相容前端 glossary_list array 格式
            if not glossary and glossary_list:
                glossary = {item['original']: item['translated']
                            for item in glossary_list
                            if item.get('original') and item.get('translated')}
            
            if use_glossary and glossary:
                # 將術語表轉換為上下文文本
                # 格式: "原文: 翻譯\n原文2: 翻譯2"
                context_lines = [f"{source}: {target}" for source, target in glossary.items()]
                args['qwen3_context'] = "\n".join(context_lines)
            else:
                args['qwen3_context'] = None
        else:
            args['qwen3_context'] = None
        
        translation_config = config.get('translation', {})
        resolved_api_keys = self._resolve_translation_api_keys(config)

        # 翻譯提示詞邏輯 (保留原版智慧判斷)
        if config['translation'].get('backend') != 'none':
            # 檢查是否使用智能提示詞
            use_smart_prompt = config['translation'].get('use_smart_prompt', True)
            
            if use_smart_prompt:
                # 智能生成提示詞
                input_language = config['transcription'].get('language', 'auto')
                target_language_code = config['translation'].get('target_language', '繁體中文') or '繁體中文'
                
                zh_languages = ['zh', 'auto', '繁體中文', '簡體中文', 'Traditional Chinese', 'Simplified Chinese']
                is_zh_involved = input_language in zh_languages or target_language_code in zh_languages
                
                target_lang_map_zh = {
                    '繁體中文': '繁體中文', 'Traditional Chinese': '繁體中文',
                    '簡體中文': '簡體中文', 'Simplified Chinese': '簡體中文',
                    '日文': '日文', 'Japanese': '日文',
                    '英文': '英文', 'English': '英文',
                    '韓文': '韓文', 'Korean': '韓文'
                }
                
                target_lang_map_en = {
                    '繁體中文': 'Traditional Chinese', 'Traditional Chinese': 'Traditional Chinese',
                    '簡體中文': 'Simplified Chinese', 'Simplified Chinese': 'Simplified Chinese',
                    '日文': 'Japanese', 'Japanese': 'Japanese',
                    '英文': 'English', 'English': 'English',
                    '韓文': 'Korean', 'Korean': 'Korean'
                }
                
                if is_zh_involved:
                    target_lang_name = target_lang_map_zh.get(target_language_code, target_language_code)
                    base_prompt = f"將以下文本翻譯為{target_lang_name}，注意只需要輸出翻譯後的結果，不要額外解釋"
                else:
                    target_lang_name = target_lang_map_en.get(target_language_code, target_language_code)
                    base_prompt = f"Translate the following segment into {target_lang_name}, without additional explanation."
                
                args['translation_prompt'] = base_prompt
                
                use_glossary = config.get('terminology', {}).get('use_terminology_glossary', False)
                terminology_config = config.get('terminology', {})
                glossary = terminology_config.get('terminology_glossary', {})
                glossary_list = terminology_config.get('glossary_list', [])
                # 相容前端 glossary_list array 格式
                if not glossary and glossary_list:
                    glossary = {item['original']: item['translated']
                                for item in glossary_list
                                if item.get('original') and item.get('translated')}
                
                if use_glossary and glossary:
                    import json as _json
                    args['translation_glossary'] = _json.dumps(glossary, ensure_ascii=False)
                else:
                    args['translation_glossary'] = None
            else:
                # 使用自訂提示詞
                args['translation_prompt'] = config['translation'].get('translation_prompt', '')
                args['translation_glossary'] = None
        else:
            args['translation_prompt'] = ''
            args['translation_glossary'] = None
        
        # 翻譯參數
        args.update({
            'translation_history_size': translation_config.get('translation_history_size', 0),
            'translation_timeout': translation_config.get('translation_timeout', 10),
            'gpt_model': translation_config.get('gpt_model', 'gpt-4o-mini'),
            'gemini_model': translation_config.get('gemini_model', 'gemini-2.0-flash-exp'),
            'gpt_base_url': translation_config.get('gpt_base_url', ''),
            'gemini_base_url': translation_config.get('gemini_base_url', ''),
            'processing_proxy': translation_config.get('processing_proxy', ''),
            'use_json_result': translation_config.get('use_json_result', False),
            'retry_if_translation_fails': translation_config.get('retry_if_translation_fails', True),
        })
        
        # 後端模型邏輯
        backend = config['translation'].get('backend', '')
        gpt_model = config['translation'].get('gpt_model', 'gpt-4o-mini')
        custom_models = config['translation'].get('custom_models', [])
        
        if not backend.startswith('custom:'):
            args['backend'] = backend
            
        is_custom_model = False
        model_name = None
        
        if backend.startswith('custom:'):
            is_custom_model = True
            model_name = backend.replace('custom:', '')
        else:
            for model in custom_models:
                if model.get('name') == gpt_model:
                    is_custom_model = True
                    model_name = gpt_model
                    break
        
        if is_custom_model and model_name:
            for model in custom_models:
                if model.get('name') == model_name:
                    api_key = model.get('api_key', '')
                    args['openai_api_key'] = api_key if api_key else '114514'
                    # 優先使用 model_name 欄位（實際 API 模型 ID），否則用顯示名稱
                    actual_model_id = model.get('model_name') or model_name
                    args['gpt_model'] = actual_model_id
                    # 處理 base_url (舊格式) 或 api_url (新格式)
                    base_url = model.get('base_url') or model.get('api_url', '')
                    if base_url:
                        args['gpt_base_url'] = base_url
                    break
            else:
                args['gpt_model'] = gpt_model
                args['openai_api_key'] = resolved_api_keys.get('openai_api_key', '')
        else:
            args['gpt_model'] = gpt_model
            args['openai_api_key'] = resolved_api_keys.get('openai_api_key', '')
        
        args['google_api_key'] = resolved_api_keys.get('google_api_key', '')
        
        # 輸出配置
        output_notification = config.get('output_notification', {})
        output_config = config.get('output', {})
        
        # Discord 設定 - 只在啟用時才添加
        discord_url = ''
        if output_notification.get('discord_enabled', False):
            url = output_notification.get('discord_webhook_url', '')
            # 移除前後空格
            discord_url = url.strip() if url else ''
        
        # Telegram 設定 - 只在啟用時才添加
        telegram_token = ''
        telegram_chat_id = ''
        if output_notification.get('telegram_enabled', False):
            telegram_token = output_notification.get('telegram_bot_token') or ''
            telegram_chat_id = output_notification.get('telegram_chat_id') or ''
        
        # output_file_path：手動填寫優先，否則根據 output_dir + output_srt/txt/ass 自動組合
        manual_output_file_path = (output_notification.get('output_file_path') or '').strip()
        if not manual_output_file_path:
            output_dir = (output_config.get('output_dir') or '').strip()
            if output_dir:
                import os as _os
                from datetime import datetime as _dt
                _os.makedirs(output_dir, exist_ok=True)
                timestamp_str = _dt.now().strftime('%Y%m%d_%H%M%S')
                # 優先順序：srt > ass > txt
                if output_config.get('output_srt', False):
                    auto_output_file_path = _os.path.join(output_dir, f'{timestamp_str}.srt')
                elif output_config.get('output_ass', False):
                    auto_output_file_path = _os.path.join(output_dir, f'{timestamp_str}.ass')
                elif output_config.get('output_txt', False):
                    auto_output_file_path = _os.path.join(output_dir, f'{timestamp_str}.txt')
                else:
                    auto_output_file_path = ''
            else:
                auto_output_file_path = ''
            resolved_output_file_path = auto_output_file_path
        else:
            resolved_output_file_path = manual_output_file_path
        
        args.update({
            'output_file_path': resolved_output_file_path,
            'output_timestamps': output_notification.get('output_timestamps', True),  # 預設開啟
            'hide_transcribe_result': output_notification.get('hide_transcribe_result', False),
            'output_proxy': output_notification.get('output_proxy') or '',
            'cqhttp_url': output_notification.get('cqhttp_url') or '',
            'cqhttp_token': output_notification.get('cqhttp_token') or '',
            'discord_webhook_url': discord_url,
            'telegram_token': telegram_token,
            'telegram_chat_id': telegram_chat_id,
        })
        
        return args
    
    def update_from_ui(self, section: str, key: str, value: Any):
        """從 UI 更新單個配置值"""
        if section in self.config:
            self.config[section][key] = value
            self.save()
            
    def update_section(self, section: str, data: Dict[str, Any]):
        """更新整個區段 - 完全覆蓋而非合併"""
        # 直接更新或建立區段，不檢查是否存在，確保匯入時能還原所有設定
        self.config[section] = data
        self.save()

    def reset_to_defaults(self):
        """重置為預設配置"""
        self.config = self._deep_copy(self.DEFAULT_CONFIG)
        self.save()
