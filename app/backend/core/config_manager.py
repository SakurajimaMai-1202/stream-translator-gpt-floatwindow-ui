"""
配置管理系統 (Backend Port)
提供 YAML 配置的讀取、儲存、驗證與視窗狀態管理
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import logging
import yaml
import copy
import json
import os
import tempfile
import time
import shutil
from datetime import datetime
from backend.core.config_secrets import SECRET_KEYS, restore_masked_secrets
from contextlib import contextmanager
from backend.config import settings
from backend.core.cookie_manager import resolve_cookie_path
from backend.core.hardware_detector import default_llama_gpu_layers
from backend.core.runtime_profiles import (
    effective_asr_compute_backend,
    get_asr_capabilities,
    get_runtime_capabilities,
    normalize_asr_compute_backend,
)
from backend.core.asr_model_capabilities import coerce_model_language
from backend.core.portable_paths import get_packaged_runtime_profile


logger = logging.getLogger(__name__)


def normalize_transcription_engine_flags(transcription: Dict[str, Any]) -> None:
    """Make the selected engine authoritative over legacy saved booleans."""
    selected_engine = transcription.get('backend', 'faster-whisper')
    transcription.update({
        'use_faster_whisper': selected_engine in {'faster-whisper', 'faster-whisper-simul'},
        'use_simul_streaming': selected_engine in {'simul-streaming', 'faster-whisper-simul'},
        'use_openai_transcription_api': selected_engine == 'openai-api',
        'use_qwen3_asr': selected_engine == 'qwen3-asr',
        'use_sensevoice_asr': selected_engine == 'sensevoice',
        'use_fun_asr': selected_engine == 'fun-asr-nano',
        'use_nemo_asr': selected_engine == 'parakeet-ctc-ja',
    })

class ConfigManager:
    """配置管理器 - 處理所有配置相關操作"""
    
    DEFAULT_CONFIG = {
        'general': {
            'log_level': 'INFO'
        },
        'server': {
            'public_port': 8765,
            'enable_subtitle_sharing': True,
        },
        'runtime': {
            'profile': 'cuda',
            'device_policy': 'auto_discrete',
            'device_index': None,
            'device_name': '',
            'allow_integrated_gpu': False,
        },
        'models': {
            'storage_path': '',
        },
        'input': {
            'input_source': 'url',
            'url': '',
            'format': 'ba/wa*',
            'cookies': '',
            'cookies_by_site': {
                'youtube': '',
                'tiktok': '',
                'twitter': '',
                'twitch': '',
                'bilibili': '',
            },
            'proxy': '',
            'source_type': 'youtube',
            'timeout': 30,
            'device_recording_interval': 0.1,
            'audio_source': 'url',
            'device_index': None,
            'process_id': None,
            'process_start_time': '',
            'window_handle': '',
            'process_name': '',
            'title': '',
        },
        'audio_slicing_vad': {
            'min_audio_length': 0.7,
            'max_audio_length': 8.0,
            'target_audio_length': 4.0,
            'continuous_no_speech_threshold': 0.5,
            'disable_dynamic_no_speech_threshold': False,
            'vad_threshold': 0.35,
            'disable_dynamic_vad_threshold': False,
            'prefix_retention_length': 0.25,
            'vad_enabled': True,
            'vad_every_n_frames': 2,
            'vad_backend': 'firered',
            'firered_vad_model_path': '',
            'slicing_mode': 'omnivad_native',
            'omnivad_threshold': 0.35,
            'omnivad_max_audio_length': 6.0,
            'omnivad_smooth_window_size': 5,
            'omnivad_pad_start_frame': 5,
            'omnivad_min_speech_frame': 8,
            'omnivad_max_speech_frame': 2000,
            'omnivad_min_silence_frame': 20
        },
        'transcription': {
            'openai_api_key': '',
            'backend': 'qwen3-asr',
            'asr_compute_backend': 'auto',
            'model': 'Qwen/Qwen3-ASR-1.7B',
            'language': 'auto',
            'filters': [],
            'use_faster_whisper': False,
            'use_simul_streaming': False,
            'simul_streaming_encoder': 'whisper',
            'use_openai_transcription_api': False,
            'use_qwen3_asr': True,
            'use_sensevoice_asr': False,
            'use_fun_asr': False,
            'use_nemo_asr': False,
            'qwen3_asr_model': 'Qwen/Qwen3-ASR-1.7B',
            'qwen3_dtype': 'bfloat16',
            'qwen3_load_in_4bit': False,
            'qwen3_rms_threshold': 0.005,
            'sensevoice_model': 'iic/SenseVoiceSmall',
            'fun_asr_model': 'FunAudioLLM/Fun-ASR-Nano-2512',
            'nemo_asr_model': 'nvidia/parakeet-tdt_ctc-0.6b-ja',
            'nemo_asr_device': 'auto',
            'nemo_asr_decoding': 'tdt',
            'nemo_asr_dtype': 'bfloat16',
            'asr_corrections_enabled': False,
            'asr_correction_log_enabled': False,
            'asr_correction_learning_enabled': False,
            'asr_corrections_case_sensitive': False,
            'asr_correction_rules': [],
            'openai_transcription_model': 'whisper-1',
            'whisper_filters': [],
            'disable_transcription_context': False,
            'transcription_initial_prompt': ''
        },
        'translation': {
            'openai_api_key': '',
            'google_api_key': '',
            'backend': 'custom:localllm',
            'model': 'localllm',
            'translation_prompt': '翻譯成繁體中文',
            'target_language': 'Traditional Chinese',
            'history_size': 0,
            'timeout': 10,
            'gpt_model': 'localllm',
            'gemini_model': 'gemini-2.5-flash-lite',
            'translation_history_size': 0,
            'translation_timeout': 10,
            'gpt_base_url': 'https://api.openai.com/v1',
            'gemini_base_url': 'https://generativelanguage.googleapis.com/v1beta',
            'processing_proxy': '',
            'use_json_result': False,
            'retry_if_translation_fails': True,
            'translation_model_family': 'auto',
            'translation_output_format': 'auto',
            'translation_max_concurrency': 0,
            'translation_max_output_tokens': 128,
            'family_optimizer_auto': True,
            'hy_mt2_optimizer_enabled': False,
            'hy_mt2_context_window': 3,
            'hy_mt2_max_context_chars': 1000,
            'hy_mt2_max_terms': 10,
            'hy_mt2_style': True,
            'hy_mt2_style_text': '使用自然、簡潔的台灣繁體中文直播字幕；保留原文語氣，不要補充原文沒有的資訊；只輸出譯文。',
            'hy_mt2_preferences': '',
            'hy_mt2_debug': False,
            'hy_mt2_provider': 'existing',
            'hy_mt2_lm_studio_url': 'http://127.0.0.1:1234/v1',
            'hy_mt2_lm_studio_model': '',
            'hy_mt2_lm_studio_api_key': '',
            'hy_mt2_llama_cpp_url': 'http://127.0.0.1:8081/v1',
            'hy_mt2_llama_cpp_model': '',
            'hy_mt2_llama_cpp_api_key': '',
            'hy_mt2_glossary_folder': '',
            'hy_mt2_glossary_preset': '',
            'index_translate_optimizer_enabled': False,
            'index_translate_context_window': 3,
            'index_translate_max_context_chars': 1000,
            'index_translate_max_terms': 10,
            'index_translate_style': True,
            'index_translate_style_text': '使用自然、簡潔的台灣繁體中文直播字幕；保留原文語氣，不要補充原文沒有的資訊；只輸出譯文。',
            'index_translate_preferences': '',
            'index_translate_debug': False,
            'index_translate_provider': 'existing',
            'index_translate_lm_studio_url': 'http://127.0.0.1:1234/v1',
            'index_translate_lm_studio_model': '',
            'index_translate_lm_studio_api_key': '',
            'index_translate_llama_cpp_url': 'http://127.0.0.1:8081/v1',
            'index_translate_llama_cpp_model': '',
            'index_translate_llama_cpp_api_key': '',
            'index_translate_glossary_folder': '',
            'index_translate_glossary_preset': '',
            'translation_glossary_scope': None,
            'paired_subtitle_mode': True,
            'deduplicate_asr_overlap': True,
            'subtitle_assembler_enabled': True,
            'subtitle_assembler_wait_ms': 400,
            'subtitle_assembler_max_duration': 6.0,
            'subtitle_assembler_gap_threshold': 0.8,
            'use_smart_prompt': True,
            'smart_prompt_enabled': True,
            'custom_models': [
                {
                    'name': 'localllm',
                    'base_url': 'http://127.0.0.1:8081',
                    'api_key': '114514',
                    'model_name': 'localllm'
                }
            ]
        },
        'terminology': {
            'use_terminology_glossary': True,
            'active_categories': [],
            'builtin_disabled': [],
            'schema_version': 2,
            'translation_glossary_audit_enabled': False,
            'terminology_glossary': {},
            'glossary': '',
            'glossary_list': [],
            'custom_glossary_scopes': [],
            'glossary_to_asr_prompt': False,
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
            '_visibility_defaults_v2': False,
            'fontSize': 18,
            'fontWeight': 700,
            'opacity': 100,
            'showOriginal': True,
            'showTranslated': True,
            'showTimestamp': True,
            'showLatency': True,
            'position': 'bottom',
            'autoScroll': True,
            'maxDisplayCount': 5,
            'textColor': '#55FFFF',
            'translatedColor': '#FFDD00',
            'timestampColor': '#FF5500',
            'latencyColor': '#AAFF00',
            'backgroundColor': '#FFFFFF',
            'backgroundOpacity': 5,
            'mousePassthrough': False,
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
                'main_window': {'width': 1287, 'height': 917},
                'settings': {'x': 150, 'y': 150, 'width': 800, 'height': 600, 'visible': False},
                'floating_subtitle': {'width': 800, 'height': 300, 'visible': True, 'transparency': 80}
            }
        },
        'llama': {
            'local_llm_enabled': False,
            'model_dir': '',
            'model_path': '',
            'server_exe': '',
            'recent_model_paths': [],
            'favorite_model_paths': [],
            'selected_preset': '',
            'default_preset': '',
            'host': '127.0.0.1',
            'port': 8081,
            'n_ctx': 2048,
            'n_gpu_layers': 0,
            'gpu_device': 'auto',
            'gpu_device_name': '',
            'allow_integrated_gpu': False,
            'n_threads': 4,
            'n_parallel': 1,
            'top_k': 40,
            'top_p': 0.95,
            'temp': 0.8,
            'repeat_penalty': 1.1,
            'n_predict': 512,
            'flash_attn': 'auto',
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
        self.config = self._enforce_packaged_runtime(self._load_or_create())
        self._file_signature = self._get_file_signature()
    
    LOCK_TIMEOUT_SECONDS = 10.0

    def _load_or_create(self) -> Dict[str, Any]:
        """Serialize first creation, recovery, and migration with other writers."""
        with self._config_lock():
            if not self.config_path.exists():
                legacy = self.config_path.parent / "data" / "config.yaml"
                if legacy.exists():
                    try:
                        with legacy.open(encoding='utf-8') as stream:
                            loaded = yaml.safe_load(stream)
                        config, _ = self._migrate_legacy_config(self._merge_with_defaults(loaded))
                        config = self._enforce_packaged_runtime(config)
                    except (yaml.YAMLError, UnicodeError, ValueError):
                        logger.warning("Invalid legacy configuration; using defaults")
                        config = self._profile_defaults()
                else:
                    config = self._profile_defaults()
                self._save(config)
                return config
            raw = []
            config = self._read_current_config(raw_out=raw)
            # Write back only when merging defaults or migrating changed what is on
            # disk, so hand edits survive an ordinary start.
            changed = bool(raw) and config != raw[0]
            llama = config['llama']
            if llama.pop('first_run_gpu_default', False) is True:
                if llama.get('gpu_layers_default_applied') is not True and llama.get('n_gpu_layers') == 0:
                    llama['n_gpu_layers'] = default_llama_gpu_layers()
                llama['gpu_layers_default_applied'] = True
                changed = True
            if changed:
                try:
                    self._save(config)
                except OSError:
                    logger.warning("Configuration loaded but migration could not be saved")
            return config

    def _backup_path(self, kind):
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        return self.config_path.with_name(f"{self.config_path.name}.{kind}-{stamp}")

    def _validate_structure(self, config):
        """Reject invalid mapping shapes before migration or persistence."""
        def check(value, defaults, path):
            if not isinstance(value, dict):
                raise ValueError(f"Configuration {path} must be a mapping")
            for key, default in defaults.items():
                if isinstance(default, dict) and key in value:
                    check(value[key], default, f"{path}.{key}")
                elif isinstance(default, list) and key in value and not isinstance(value[key], list):
                    raise ValueError(f"Configuration {path}.{key} must be a list")
        check(config, self.DEFAULT_CONFIG, 'root')
        for index, model in enumerate(config.get('translation', {}).get('custom_models', [])):
            if not isinstance(model, dict):
                raise ValueError(f"translation.custom_models[{index}] must be a mapping")
            for field in ('name', 'model_name', 'api_key', 'base_url', 'api_url'):
                if field in model and model[field] is not None and not isinstance(model[field], str):
                    raise ValueError(f"translation.custom_models[{index}].{field} must be a string or null")

    def _profile_defaults(self) -> Dict[str, Any]:
        """Defaults for first run and explicit reset, never for loaded configs."""
        config = self._enforce_packaged_runtime(self._deep_copy(self.DEFAULT_CONFIG))
        config['llama']['n_gpu_layers'] = default_llama_gpu_layers()
        # Fresh defaults already use the v2 visibility defaults; mark them so the
        # next start does not "migrate" and rewrite a just-created file.
        config['subtitle_settings']['_visibility_defaults_v2'] = True
        return config

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
        
        self._validate_structure(config)
        merged = merge(self.DEFAULT_CONFIG, config)
        # Preserve absent migration inputs until the old file is migrated.
        terminology = config.get('terminology', {})
        for key in ('schema_version', 'active_categories'):
            if key not in terminology:
                merged['terminology'].pop(key, None)
        if 'use_terminology_glossary' not in terminology:
            merged['terminology']['use_terminology_glossary'] = False
        return merged

    def _deep_merge(self, base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge dictionaries while preserving unknown/new settings."""
        result = self._deep_copy(base)
        for key, value in updates.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = self._deep_copy(value)
        return result

    def _enforce_packaged_runtime(self, config: Dict[str, Any]) -> Dict[str, Any]:
        packaged_profile = get_packaged_runtime_profile()
        if packaged_profile is None:
            return config
        runtime = config.setdefault('runtime', {})
        runtime['profile'] = packaged_profile
        if packaged_profile == 'cpu':
            runtime['device_policy'] = 'cpu'
            runtime['allow_integrated_gpu'] = False
            config.setdefault('transcription', {})['asr_compute_backend'] = 'cpu'
        return config

    def _migrate_legacy_config(self, config: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
        """遷移舊版配置到新版欄位/枚舉值。回傳 (config, 是否有變更)"""
        changed = False
        translation = config.get('translation', {})
        transcription = config.get('transcription', {})
        general = config.get('general', {})
        backend = str(translation.get('backend', '') or '').strip().lower()
        terminology = config.setdefault('terminology', {})
        before = self._deep_copy((terminology, transcription))
        from backend.core.hy_mt2_glossary_presets import _term_aliases
        rows = terminology.get('glossary_list')
        if not isinstance(rows, list):
            rows = terminology['glossary_list'] = []
        for row in rows:
            if isinstance(row, dict):
                row['aliases'] = _term_aliases(row)
        if terminology.get('schema_version', 0) < 2:
            if 'active_categories' not in terminology:
                category = translation.get('translation_glossary_scope')
                if category is None:
                    category = translation.get('hy_mt2_glossary_preset')
                category = category.strip() if isinstance(category, str) else ''
                if category in ('hololive_vtuber', 'cosplay'):
                    terminology['active_categories'] = ['general_chat', category]
                else:
                    terminology['active_categories'] = [category] if category and category != 'all' else []
            for rule in transcription.get('asr_correction_rules', []) or []:
                if not isinstance(rule, dict):
                    continue
                canonical = rule.get('canonical')
                if not isinstance(canonical, str) or not canonical.strip():
                    continue
                # Manual rules applied to every session, so they only merge into
                # a 一般 row; a row in another category would switch them off
                # whenever that category is not selected.
                row = next((row for row in rows if isinstance(row, dict) and row.get('original') == canonical
                            and (row.get('scope') or 'all') == 'all'), None)
                if row is None:
                    row = {'original': canonical, 'translated': '', 'aliases': [], 'scope': 'all'}
                    rows.append(row)
                row['aliases'] = list(dict.fromkeys([*_term_aliases(row), *_term_aliases(rule)]))
            transcription['asr_correction_rules'] = []
            for source, target in (terminology.get('terminology_glossary') or {}).items():
                row = next((row for row in rows if isinstance(row, dict) and row.get('original') == source
                            and (row.get('scope') or 'all') == 'all'), None)
                if row is None:
                    rows.append({'original': source, 'translated': target, 'aliases': [], 'scope': 'all'})
                else:
                    row['translated'] = target
            terminology['terminology_glossary'] = {}
            terminology.setdefault('builtin_disabled', [])
            terminology['schema_version'] = 2
        changed = before != (terminology, transcription)

        # Move the former global/provider-shared keys into their owning
        # feature sections so ASR, OpenAI translation, and Gemini translation
        # are unambiguous in both the UI and persisted config.
        legacy_openai = str(general.get('openai_api_key', '') or '').strip()
        legacy_google = str(general.get('google_api_key', '') or '').strip()
        legacy_translation = str(translation.get('api_key', '') or '').strip()
        if not transcription.get('openai_api_key') and legacy_openai:
            transcription['openai_api_key'] = legacy_openai
            changed = True
        if not translation.get('openai_api_key') and (legacy_translation if backend == 'gpt' else legacy_openai):
            translation['openai_api_key'] = legacy_translation if backend == 'gpt' and legacy_translation else legacy_openai
            changed = True
        if not translation.get('google_api_key') and (legacy_translation if backend == 'gemini' else legacy_google):
            translation['google_api_key'] = legacy_translation if backend == 'gemini' and legacy_translation else legacy_google
            changed = True
        for legacy_field in ('openai_api_key', 'google_api_key'):
            if legacy_field in general:
                general.pop(legacy_field, None)
                changed = True
        if 'api_key' in translation:
            translation.pop('api_key', None)
            changed = True
        config['general'] = general
        config['transcription'] = transcription

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

        # 舊版以空字串代表官方端點；改為顯式保存，讓設定頁能直接顯示
        # 實際使用的預設 URL，同時保留所有非空白的自訂端點。
        endpoint_defaults = {
            'gpt_base_url': 'https://api.openai.com/v1',
            'gemini_base_url': 'https://generativelanguage.googleapis.com/v1beta',
        }
        for key, default_url in endpoint_defaults.items():
            if key == 'gemini_base_url' and translation.get(key) == 'https://generativelanguage.googleapis.com':
                translation[key] = default_url
                changed = True
            if not str(translation.get(key, '') or '').strip():
                translation[key] = default_url
                changed = True
        config['translation'] = translation

        subtitle_settings = config.setdefault('subtitle_settings', {})
        if not subtitle_settings.get('_visibility_defaults_v2'):
            for key in ('showOriginal', 'showTranslated', 'showTimestamp', 'showLatency', 'autoScroll'):
                subtitle_settings[key] = True
            subtitle_settings['_visibility_defaults_v2'] = True
            changed = True

        # 本地 LLM 的啟用開關是程序工作階段狀態，不可跨程式啟動保留。
        # 模型路徑與生成參數仍照常保存；舊版留下的 true 在載入時清除。
        llama = config.setdefault('llama', {})
        if llama.get('local_llm_enabled') is not False:
            llama['local_llm_enabled'] = False
            changed = True

        return config, changed
    
    def save(self):
        """儲存當前配置到檔案"""
        with self._config_lock():
            self._save(self.config)
    
    def _save(self, config: Dict):
        """內部儲存方法"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.config_path.name}.",
            suffix=".tmp",
            dir=str(self.config_path.parent),
        )
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
                yaml.safe_dump(
                    config,
                    f,
                    allow_unicode=True,
                    default_flow_style=False,
                    sort_keys=False,
                )
                f.flush()
                os.fsync(f.fileno())
            replace_error = None
            for attempt in range(5):
                try:
                    os.replace(temp_name, self.config_path)
                    replace_error = None
                    break
                except PermissionError as error:
                    replace_error = error
                    if os.name != 'nt' or attempt == 4:
                        raise
                    # Windows can briefly deny replacement while another
                    # process, antivirus, or indexer has the YAML open.
                    time.sleep(0.03 * (2 ** attempt))
            if replace_error is not None:
                raise replace_error
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    def _read_current_config(self, secret_source=None, raw_out=None) -> Dict[str, Any]:
        """Read the latest disk state before a cross-process update.

        raw_out, when given, receives the parsed file content as read from disk.
        """
        if not self.config_path.exists():
            return self._deep_copy(self.DEFAULT_CONFIG)

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                loaded = yaml.safe_load(f)
            self._validate_structure(loaded)
        except (yaml.YAMLError, UnicodeError, ValueError):
            backup = self._backup_path('corrupt')
            self.config_path.rename(backup)
            logger.warning("Invalid configuration moved to %s; restoring defaults", backup)
            defaults = self._profile_defaults()
            self._save(defaults)
            return defaults
        if raw_out is not None:
            raw_out.append(self._deep_copy(loaded))
        merged = self._merge_with_defaults(loaded)
        if secret_source is not None:
            # Restore exact stored credentials, including empty values, before
            # migration can copy legacy keys into other sections or remove them.
            # This snapshot is read under the same lock as the mutation.
            secret_source.update(self._deep_copy(merged))
        migrated, _changed = self._migrate_legacy_config(merged)
        return self._enforce_packaged_runtime(migrated)

    def _get_file_signature(self):
        """Return a cheap signature used to detect external config changes."""
        try:
            stat = self.config_path.stat()
            return (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            return None

    @contextmanager
    def _config_lock(self):
        """Serialize read-merge-write updates from the UI and backend processes."""
        lock_path = self.config_path.with_suffix(self.config_path.suffix + '.lock')
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, 'a+b') as lock_file:
            # Windows byte-range locks also forbid reads by other handles.
            # Do not read/initialize the byte before acquiring its lock:
            # locking past EOF is supported, including an empty lock file.
            lock_file.seek(0)

            deadline = time.monotonic() + self.LOCK_TIMEOUT_SECONDS
            if os.name == 'nt':
                import msvcrt
                while True:
                    try:
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError as exc:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Timed out waiting for configuration lock") from exc
                        time.sleep(0.02)
                try:
                    yield
                finally:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                while True:
                    try:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError as exc:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Timed out waiting for configuration lock") from exc
                        time.sleep(0.02)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    
    def get_config(self) -> Dict[str, Any]:
        """Return cached config, reloading only after an external file change."""
        signature = self._get_file_signature()
        if signature != self._file_signature:
            with self._config_lock():
                signature = self._get_file_signature()
                if signature != self._file_signature:
                    self.config = self._read_current_config()
                    self._file_signature = signature
        return self._deep_copy(self.config)

    def _resolve_translation_api_keys(self, config: Dict[str, Any]) -> Dict[str, str]:
        """
        解析翻譯 API 金鑰優先級

        優先級：
        1) translation.api_key（若有填寫，僅覆蓋當前 translation.backend 對應服務）
        2) general.openai_api_key / general.google_api_key
        """
        translation_config = config.get('translation', {})
        general_config = config.get('general', {})
        legacy_key = str(translation_config.get('api_key', '') or '').strip()
        backend = str(translation_config.get('backend', '') or '')

        # Provider-specific fields prevent OpenAI and Gemini keys from being
        # overwritten when the user switches translation backends.  The old
        # fields remain read-only fallbacks for upgrades from existing config.
        resolved_openai_key = str(
            translation_config.get('openai_api_key', '')
            or (legacy_key if backend == 'gpt' else '')
            or general_config.get('openai_api_key', '')
            or ''
        ).strip()
        resolved_google_key = str(
            translation_config.get('google_api_key', '')
            or (legacy_key if backend == 'gemini' else '')
            or general_config.get('google_api_key', '')
            or ''
        ).strip()

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
        transcription_config = self.config.get('transcription', {})

        if (transcription_config.get('use_openai_transcription_api')
                and not str(transcription_config.get('openai_api_key', '') or '').strip()):
            warnings.append({
                'level': 'error',
                'message': 'OpenAI ASR API 金鑰未設定',
                'action': 'setting',
                'page': 'transcription'
            })

        if not resolved_api_keys.get('openai_api_key') and translation_backend == 'gpt':
            warnings.append({
                'level': 'error',
                'message': 'OpenAI API 金鑰未設定',
                'action': 'setting', # 前端動作標識
                'page': 'translation'
            })
        
        if not resolved_api_keys.get('google_api_key') and translation_backend == 'gemini':
            warnings.append({
                'level': 'error',
                'message': 'Google API 金鑰未設定',
                'action': 'setting',
                'page': 'translation'
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
        self.update_section('ui', {'windows': {window_name: state}})
    
    def load_window_state(self, window_name: str) -> Dict[str, Any]:
        """從配置載入視窗狀態"""
        default_states = self.DEFAULT_CONFIG['ui']['windows']
        
        if 'ui' not in self.config or 'windows' not in self.config['ui']:
            return default_states.get(window_name, {})
        
        return self.config['ui']['windows'].get(window_name, default_states.get(window_name, {}))
    
    def _coerce_transcription_backend(self, requested_backend: Any, runtime_capabilities: Any) -> str:
        requested = str(requested_backend or '').strip() or 'faster-whisper'
        allowed_local = set(runtime_capabilities.local_asr_engines)
        allowed_remote = set(runtime_capabilities.remote_asr_engines)
        allowed = allowed_local | allowed_remote
        if requested in allowed:
            return requested
        if requested in {'faster-whisper', 'simul-streaming', 'faster-whisper-simul'} and 'faster-whisper' in allowed:
            return 'faster-whisper'
        if 'qwen3-asr' in allowed:
            return 'qwen3-asr'
        if 'sensevoice' in allowed:
            return 'sensevoice'
        if 'faster-whisper' in allowed:
            return 'faster-whisper'
        if 'openai-api' in allowed:
            return 'openai-api'
        return 'qwen3-asr'

    def _coerce_model_id(self, requested_model: Any, allowed_models: tuple[str, ...], fallback: str) -> str:
        requested = str(requested_model or '').strip()
        if requested and (not allowed_models or requested in allowed_models):
            return requested
        return allowed_models[0] if allowed_models else fallback

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
        elif audio_source == 'process_audio':
            url = 'process_audio'
        elif audio_source in ['url', 'file']:
            url = input_config.get('url', '')
        else:
            # 預設使用 URL
            url = input_config.get('url', '')
        
        runtime_config = config.get('runtime', {})
        runtime_capabilities = get_runtime_capabilities(runtime_config.get('profile'))
        configured_asr_compute_backend = normalize_asr_compute_backend(
            config['transcription'].get('asr_compute_backend'),
            runtime_capabilities.profile,
        )
        effective_asr_backend = effective_asr_compute_backend(
            configured_asr_compute_backend,
            runtime_capabilities.profile,
        )
        asr_capabilities = get_asr_capabilities(
            runtime_capabilities.profile,
            configured_asr_compute_backend,
        )
        requested_transcription_backend = config['transcription'].get('backend', 'faster-whisper')
        if config['transcription'].get('model') in asr_capabilities.sensevoice_model_ids:
            requested_transcription_backend = 'sensevoice'
        if config['transcription'].get('model') in asr_capabilities.fun_asr_model_ids:
            requested_transcription_backend = 'fun-asr-nano'
        if config['transcription'].get('model') in asr_capabilities.parakeet_model_ids:
            requested_transcription_backend = 'parakeet-ctc-ja'
        if config['transcription'].get('use_fun_asr'):
            requested_transcription_backend = 'fun-asr-nano'
        elif config['transcription'].get('use_sensevoice_asr'):
            requested_transcription_backend = 'sensevoice'
        elif config['transcription'].get('use_nemo_asr'):
            requested_transcription_backend = 'parakeet-ctc-ja'
        elif config['transcription'].get('use_qwen3_asr'):
            requested_transcription_backend = 'qwen3-asr'
        elif config['transcription'].get('use_openai_transcription_api'):
            requested_transcription_backend = 'openai-api'
        elif config['transcription'].get('use_faster_whisper') and config['transcription'].get('use_simul_streaming'):
            requested_transcription_backend = 'faster-whisper-simul'
        elif config['transcription'].get('use_simul_streaming'):
            requested_transcription_backend = 'simul-streaming'
        elif config['transcription'].get('use_faster_whisper'):
            requested_transcription_backend = 'faster-whisper'

        transcription_backend = self._coerce_transcription_backend(
            requested_transcription_backend,
            asr_capabilities,
        )
        runtime_device_policy = runtime_config.get('device_policy') or runtime_capabilities.default_device_policy
        if runtime_capabilities.profile == 'cpu':
            runtime_device_policy = 'cpu'
        runtime_allow_integrated_gpu = bool(runtime_config.get(
            'allow_integrated_gpu',
            runtime_capabilities.allow_integrated_gpu,
        ))
        qwen3_dtype = config['transcription'].get('qwen3_dtype')
        if not qwen3_dtype or (
            effective_asr_backend == 'cpu' and qwen3_dtype == 'bfloat16'
        ):
            qwen3_dtype = asr_capabilities.qwen3_default_dtype
        qwen3_device_map = 'cpu' if effective_asr_backend == 'cpu' else 'auto'
        # Qwen3-ASR 使用獨立模型欄位，其他後端沿用一般 model 欄位
        if transcription_backend == 'qwen3-asr':
            requested_qwen3_model = config['transcription'].get('qwen3_asr_model')
            if requested_qwen3_model == 'neosophie/Qwen3-ASR-1.7B-JA':
                requested_qwen3_model = 'jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame'
            transcription_model = self._coerce_model_id(
                requested_qwen3_model,
                asr_capabilities.qwen3_asr_model_ids,
                'Qwen/Qwen3-ASR-0.6B',
            )
        elif transcription_backend == 'sensevoice':
            transcription_model = self._coerce_model_id(
                config['transcription'].get('sensevoice_model'),
                asr_capabilities.sensevoice_model_ids,
                'iic/SenseVoiceSmall',
            )
        elif transcription_backend == 'fun-asr-nano':
            transcription_model = self._coerce_model_id(
                config['transcription'].get('fun_asr_model'),
                asr_capabilities.fun_asr_model_ids,
                'FunAudioLLM/Fun-ASR-Nano-2512',
            )
        elif transcription_backend == 'parakeet-ctc-ja':
            transcription_model = self._coerce_model_id(
                config['transcription'].get('nemo_asr_model'),
                asr_capabilities.parakeet_model_ids,
                'nvidia/parakeet-tdt_ctc-0.6b-ja',
            )
        else:
            transcription_model = self._coerce_model_id(
                config['transcription'].get('model', 'base'),
                asr_capabilities.faster_whisper_model_ids,
                'small',
            )

        # 基本參數對映
        transcription_language = coerce_model_language(
            transcription_model,
            config['transcription'].get('language', 'auto'),
        )

        args = {
            # 輸入
            'url': url,
            'loopback': loopback,
            'use_loopback': use_loopback,
            'proxy': '',  # 全域代理
            'format': input_config.get('format', 'ba/wa*'),
            'cookies': resolve_cookie_path(url, input_config),
            'input_proxy': input_config.get('proxy', ''),
            'device_index': input_config.get('device_index'),
            'process_id': input_config.get('process_id') if audio_source == 'process_audio' else None,
            'process_start_time': str(input_config.get('process_start_time') or '') if audio_source == 'process_audio' else '',
            'device_recording_interval': input_config.get('device_recording_interval', 0.1),
            'runtime_profile': runtime_capabilities.profile,
            'asr_compute_backend': configured_asr_compute_backend,
            'runtime_device_policy': runtime_device_policy,
            'runtime_allow_integrated_gpu': runtime_allow_integrated_gpu,
            
            # 音頻切片
            'min_audio_length': config.get('audio_slicing_vad', {}).get('min_audio_length', 0.7),
            'max_audio_length': (
                config.get('audio_slicing_vad', {}).get('omnivad_max_audio_length', 6.0)
                if config.get('audio_slicing_vad', {}).get('slicing_mode', 'omnivad_native') == 'omnivad_native'
                else config.get('audio_slicing_vad', {}).get('max_audio_length', 8.0)
            ),
            'target_audio_length': config.get('audio_slicing_vad', {}).get('target_audio_length', 4.0),
            'continuous_no_speech_threshold': config.get('audio_slicing_vad', {}).get('continuous_no_speech_threshold', 0.5),
            'disable_dynamic_no_speech_threshold': config.get('audio_slicing_vad', {}).get('disable_dynamic_no_speech_threshold', False),
            'vad_threshold': config.get('audio_slicing_vad', {}).get('vad_threshold', 0.35),
            'disable_dynamic_vad_threshold': config.get('audio_slicing_vad', {}).get('disable_dynamic_vad_threshold', False),
            'prefix_retention_length': config.get('audio_slicing_vad', {}).get('prefix_retention_length', 0.25),
            'disable_vad': not config.get('audio_slicing_vad', {}).get('vad_enabled', True),
            'vad_every_n_frames': config.get('audio_slicing_vad', {}).get('vad_every_n_frames', 2),
            'vad_backend': config.get('audio_slicing_vad', {}).get('vad_backend', 'firered'),
            'firered_vad_model_path': config.get('audio_slicing_vad', {}).get('firered_vad_model_path', ''),
            'slicing_mode': config.get('audio_slicing_vad', {}).get('slicing_mode', 'omnivad_native'),
            'omnivad_threshold': config.get('audio_slicing_vad', {}).get('omnivad_threshold', 0.35),
            'omnivad_smooth_window_size': config.get('audio_slicing_vad', {}).get('omnivad_smooth_window_size', 5),
            'omnivad_pad_start_frame': config.get('audio_slicing_vad', {}).get('omnivad_pad_start_frame', 5),
            'omnivad_min_speech_frame': config.get('audio_slicing_vad', {}).get('omnivad_min_speech_frame', 8),
            'omnivad_max_speech_frame': config.get('audio_slicing_vad', {}).get('omnivad_max_speech_frame', 2000),
            'omnivad_min_silence_frame': config.get('audio_slicing_vad', {}).get('omnivad_min_silence_frame', 20),
            'preload_asr_model': transcription_backend in ['qwen3-asr', 'faster-whisper', 'whisper', 'sensevoice', 'fun-asr-nano', 'parakeet-ctc-ja'],
            'keep_asr_loaded': transcription_backend in ['qwen3-asr', 'faster-whisper', 'whisper', 'sensevoice', 'fun-asr-nano', 'parakeet-ctc-ja'],
            
            # 語音轉文字
            'model': transcription_model,
            'language': transcription_language,
            'use_faster_whisper': transcription_backend in ['faster-whisper', 'faster-whisper-simul'],
            'use_simul_streaming': 'simul' in transcription_backend,
            'use_openai_transcription_api': transcription_backend == 'openai-api',
            'use_qwen3_asr': transcription_backend == 'qwen3-asr',
            'use_sensevoice_asr': transcription_backend == 'sensevoice',
            'use_fun_asr': transcription_backend == 'fun-asr-nano',
            'use_nemo_asr': transcription_backend == 'parakeet-ctc-ja',
            'openai_transcription_model': config['transcription'].get('openai_transcription_model', config['transcription'].get('openai_model', 'whisper-1')),
            'whisper_filters': config['transcription'].get('whisper_filters', []),
            'disable_transcription_context': config['transcription'].get('disable_transcription_context', False),
            'transcription_initial_prompt': config['transcription'].get('transcription_initial_prompt', ''),
            'qwen3_dtype': qwen3_dtype,
            'qwen3_asr_dtype': qwen3_dtype,
            'qwen3_asr_device_map': qwen3_device_map,
            'qwen3_load_in_4bit': config['transcription'].get('qwen3_load_in_4bit', False),
            'qwen3_rms_threshold': config['transcription'].get('qwen3_rms_threshold', 0.005),
            'sensevoice_model': transcription_model if transcription_backend == 'sensevoice' else config['transcription'].get('sensevoice_model', 'iic/SenseVoiceSmall'),
            'sensevoice_device': 'cpu' if effective_asr_backend == 'cpu' else 'auto',
            'fun_asr_model': transcription_model if transcription_backend == 'fun-asr-nano' else config['transcription'].get('fun_asr_model', 'FunAudioLLM/Fun-ASR-Nano-2512'),
            'fun_asr_device': 'cpu' if effective_asr_backend == 'cpu' else 'auto',
            'nemo_asr_model': transcription_model if transcription_backend == 'parakeet-ctc-ja' else config['transcription'].get('nemo_asr_model', 'nvidia/parakeet-tdt_ctc-0.6b-ja'),
            'nemo_asr_device': 'auto',
            'nemo_asr_decoding': (
                'ctc'
                if transcription_backend == 'parakeet-ctc-ja'
                and transcription_model == 'grider-transwithai/parakeet-ctc-1.1b-ja'
                else config['transcription'].get('nemo_asr_decoding', 'tdt')
            ),
            'nemo_asr_dtype': config['transcription'].get('nemo_asr_dtype', 'bfloat16'),
            'asr_corrections_enabled': config['transcription'].get('asr_corrections_enabled', False),
            # Forward the auxiliary switches edited in SettingsView.  Without
            # these keys the rule list is loaded, but correction logging and
            # learned aliases silently remain disabled in the runtime.
            'asr_correction_log_enabled': config['transcription'].get('asr_correction_log_enabled', False),
            'asr_correction_learning_enabled': config['transcription'].get('asr_correction_learning_enabled', False),
            'asr_corrections_case_sensitive': config['transcription'].get('asr_corrections_case_sensitive', False),
        }

        # Resolve once so every engine feed shares the same session vocabulary.
        from backend.core.hy_mt2_glossary_presets import ASR_PROMPT_BACKENDS, session_vocabulary
        vocabulary = session_vocabulary(config)
        terminology_config = config.get('terminology', {})
        args['asr_correction_rules'] = json.dumps(
            vocabulary['asr_rules'],
            ensure_ascii=False, separators=(',', ':'))
        if (terminology_config.get('use_terminology_glossary', True)
                and terminology_config.get('glossary_to_asr_prompt', False)
                and transcription_backend in ASR_PROMPT_BACKENDS):
            typed = str(args.get('transcription_initial_prompt') or '').strip().rstrip(',，、 ')
            words, used = [], len(typed)
            for word in vocabulary['hotwords']:
                if used + len(word) + 2 > 300:
                    break
                words.append(word)
                used += len(word) + 2
            args['transcription_initial_prompt'] = ', '.join(([typed] if typed else []) + words)

        # Qwen3-ASR 語言格式轉換：短碼 → 完整名稱
        if transcription_backend == 'qwen3-asr':
            qwen3_lang_map = {
                'ja': 'Japanese', 'en': 'English', 'zh': 'Chinese',
                # Preserve the requested Chinese script for deterministic
                # post-ASR OpenCC conversion. The transcriber still maps these
                # language hints to Chinese when calling the model itself.
                'zh-tw': 'zh-tw', 'zh-hant': 'zh-hant',
                'zh-cn': 'zh-cn', 'zh-hans': 'zh-hans',
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
        
        # Qwen3-ASR 上下文 (context) 說明：
        # 術語表不再注入至 ASR 的 context 參數，原因如下：
        #   當音訊品質差（唱歌、雜音、突然靜音），Qwen3-ASR 的 audio attention 大幅下降，
        #   模型會轉而仰賴 context token 進行解碼，導致整個術語表被直接「複製」輸出為幻覺文字。
        # 術語對照功能完全由翻譯層的 _filter_glossary() 承擔（只注入原文中有出現的術語），
        # 這樣可以保留翻譯準確性，同時消除 ASR 幻覺風險。
        args['qwen3_context'] = None
        
        translation_config = config.get('translation', {})
        resolved_api_keys = self._resolve_translation_api_keys(config)

        args['translation_target_language'] = config['translation'].get('target_language') or 'Traditional Chinese'

        # 翻譯提示詞邏輯 (保留原版智慧判斷)
        if config['translation'].get('backend') != 'none':
            # 檢查是否使用智能提示詞
            use_smart_prompt = config['translation'].get('use_smart_prompt', True)
            
            if use_smart_prompt:
                # 智能生成提示詞
                input_language = config['transcription'].get('language', 'auto')
                target_language_code = config['translation'].get('target_language', '繁體中文') or '繁體中文'
                
                zh_languages = [
                    'zh', 'zh-tw', 'zh-hant', 'zh-cn', 'zh-hans', 'auto',
                    '繁體中文', '簡體中文', 'Traditional Chinese', 'Simplified Chinese',
                ]
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
                
                glossary = vocabulary['translation_terms']
                args['translation_glossary'] = json.dumps(glossary, ensure_ascii=False) if glossary else None
            else:
                # 使用自訂提示詞
                args['translation_prompt'] = config['translation'].get('translation_prompt', '')

                glossary = vocabulary['translation_terms']
                args['translation_glossary'] = json.dumps(glossary, ensure_ascii=False) if glossary else None
        else:
            args['translation_prompt'] = ''
            args['translation_glossary'] = None
        
        # 翻譯參數
        translation_backend = str(translation_config.get('backend', '') or '')
        if translation_backend == 'gemini':
            translation_provider = 'gemini'
        elif translation_backend.startswith('custom:') or translation_backend in {'llama', 'localllm'}:
            translation_provider = 'openai_compatible'
        else:
            translation_provider = 'openai'
        args.update({
            'translation_glossary_audit_enabled': config.get('terminology', {}).get('translation_glossary_audit_enabled', False),
            'translation_provider': translation_provider,
            'translation_history_size': translation_config.get('translation_history_size', 0),
            'translation_timeout': translation_config.get('translation_timeout', 10),
            'translation_model_family': translation_config.get('translation_model_family', 'auto'),
            'family_optimizer_auto': translation_config.get('family_optimizer_auto', True),
            'translation_output_format': translation_config.get('translation_output_format', 'auto'),
            'translation_max_concurrency': translation_config.get('translation_max_concurrency', 0),
            'translation_max_output_tokens': translation_config.get('translation_max_output_tokens', 128),
            'hy_mt2_optimizer_enabled': translation_config.get('hy_mt2_optimizer_enabled', False),
            'hy_mt2_context_window': translation_config.get('hy_mt2_context_window', 3),
            'hy_mt2_max_context_chars': translation_config.get('hy_mt2_max_context_chars', 1000),
            'hy_mt2_max_terms': translation_config.get('hy_mt2_max_terms', 10),
            'hy_mt2_style': translation_config.get('hy_mt2_style', True),
            'hy_mt2_style_text': translation_config.get('hy_mt2_style_text', ''),
            'hy_mt2_preferences': translation_config.get('hy_mt2_preferences', ''),
            'hy_mt2_debug': translation_config.get('hy_mt2_debug', False),
            'index_translate_optimizer_enabled': translation_config.get('index_translate_optimizer_enabled', False),
            'index_translate_context_window': translation_config.get('index_translate_context_window', 3),
            'index_translate_max_context_chars': translation_config.get('index_translate_max_context_chars', 1000),
            'index_translate_max_terms': translation_config.get('index_translate_max_terms', 10),
            'index_translate_style': translation_config.get('index_translate_style', True),
            'index_translate_style_text': translation_config.get('index_translate_style_text', ''),
            'index_translate_preferences': translation_config.get('index_translate_preferences', ''),
            'index_translate_debug': translation_config.get('index_translate_debug', False),
            'disable_paired_subtitle_mode': not translation_config.get('paired_subtitle_mode', True),
            'disable_asr_overlap_deduplication': not translation_config.get('deduplicate_asr_overlap', True),
            'disable_subtitle_assembler': not translation_config.get('subtitle_assembler_enabled', True),
            'subtitle_assembler_wait_ms': translation_config.get('subtitle_assembler_wait_ms', 400),
            'subtitle_assembler_max_duration': translation_config.get('subtitle_assembler_max_duration', 6.0),
            'subtitle_assembler_gap_threshold': translation_config.get('subtitle_assembler_gap_threshold', 0.8),
            'gpt_model': translation_config.get('gpt_model', 'gpt-4o-mini'),
            'gemini_model': translation_config.get('gemini_model', 'gemini-2.5-flash-lite'),
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

        # Both local servers use the same OpenAI-compatible request path. Only
        # endpoint identity changes; glossary, context and prompt stay upstream.
        # Explicit family wins over stale optimizer/provider settings from another family.
        from stream_translator_gpt.translation_policy import resolve_model_family
        requested_family = translation_config.get('translation_model_family', 'auto')
        family = resolve_model_family(requested_family, args.get('gpt_model'), args.get('translation_provider'))
        if (str(requested_family or 'auto').lower() == 'auto'
                and family not in {'hy_mt2', 'index_translate'}
                and args.get('translation_provider') == 'openai_compatible'):
            # An alias such as "localllm" hides the family; ask the server what it serves.
            from backend.core.model_identity import detect_served_family, family_probe_target, is_loopback_probe
            probe_url, fallback_model = family_probe_target(backend, config, args)
            served_family = ''
            if is_loopback_probe(probe_url):
                served_family, _ = detect_served_family(probe_url, args.get('openai_api_key', ''),
                                                        args['translation_provider'], args.get('gpt_model', ''))
            if not served_family and fallback_model:
                # Server not up yet: the model selected in Llama settings is what it will load.
                fallback_family = resolve_model_family('auto', fallback_model, args['translation_provider'])
                if fallback_family in {'hy_mt2', 'index_translate'}:
                    served_family = fallback_family
            if served_family:
                family = served_family
                args['translation_model_family'] = family
        if (str(requested_family or 'auto').lower() == 'auto'
                and family not in {'hy_mt2', 'index_translate'}
                and translation_config.get('hy_mt2_optimizer_enabled')
                and translation_config.get('hy_mt2_provider') in {'lm_studio', 'llama_cpp'}):
            # Preserve old local HY configs predating an explicit family selector.
            family = 'hy_mt2'
        if family in {'hy_mt2', 'index_translate'} and backend != 'none':
            local_provider = translation_config.get(f'{family}_provider', 'existing')
            if local_provider in {'lm_studio', 'llama_cpp'}:
                prefix = f'{family}_{local_provider}'
                endpoint = str(translation_config.get(f'{prefix}_url', '') or '').strip()
                model_id = str(translation_config.get(f'{prefix}_model', '') or '').strip()
                if not endpoint or not model_id:
                    raise ValueError(f'{local_provider} requires a server URL and model ID')
                args['translation_provider'] = local_provider
                args['translation_model_family'] = family
                args['gpt_base_url'] = endpoint
                args['gpt_model'] = model_id
                args['openai_api_key'] = str(translation_config.get(f'{prefix}_api_key', '') or '').strip() or '114514'

        auto_optimizer = bool(translation_config.get('family_optimizer_auto', True))
        legacy_hy = bool(translation_config.get('hy_mt2_optimizer_enabled', False))
        legacy_index = bool(translation_config.get('index_translate_optimizer_enabled', False))
        if auto_optimizer:
            hy_enabled = backend != 'none' and family == 'hy_mt2'
            index_enabled = backend != 'none' and family == 'index_translate'
        else:
            hy_enabled = legacy_hy
            index_enabled = legacy_index
        args['hy_mt2_optimizer_enabled'] = hy_enabled
        args['index_translate_optimizer_enabled'] = index_enabled
        for _family, _enabled in (('hy_mt2', hy_enabled), ('index_translate', index_enabled)):
            if not _enabled:
                continue
            aliases = vocabulary['translation_terms']
            if aliases:
                args[f'{_family}_aliases'] = json.dumps(aliases, ensure_ascii=False)
            folder = str(translation_config.get(f'{_family}_glossary_folder', '') or '').strip()
            if folder:
                path = Path(folder)
                if not path.is_absolute():
                    path = self.config_path.parent / path
                args[f'{_family}_glossary_folder'] = str(path)

        args['google_api_key'] = resolved_api_keys.get('google_api_key', '')
        args['openai_transcription_api_key'] = str(
            config.get('transcription', {}).get('openai_api_key', '')
            or config.get('general', {}).get('openai_api_key', '')
            or ''
        ).strip()
        
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
                from pathlib import Path as _Path
                output_dir_path = _Path(output_dir)
                if not output_dir_path.is_absolute():
                    output_dir_path = settings.CONFIG_FILE.parent / output_dir_path
                output_dir = str(output_dir_path)
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
            'emit_json_events': True,
            'show_latency_log': True,
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
        self.update_section(section, {key: value})

    def update_config(self, updates: Dict[str, Any]):
        """Merge updates into the latest disk state and persist them once."""
        with self._config_lock():
            secret_source = {}
            current = self._read_current_config(secret_source)
            self._validate_structure(updates)
            updates = restore_masked_secrets(updates, secret_source or current)
            updated = self._enforce_packaged_runtime(self._deep_merge(current, updates))
            return self._persist_locked(updated)

    def update_section(self, section: str, data: Dict[str, Any]):
        """更新配置區段，保留 UI 沒送回來的既有設定。"""
        self.update_config({section: data})

    def replace_config(self, config: Dict[str, Any]):
        """Replace settings with imported values plus defaults, retaining secrets."""
        self._validate_structure(config)
        with self._config_lock():
            secret_source = {}
            current = self._read_current_config(secret_source)
            incoming = self._deep_copy(config)
            for section in self.DEFAULT_CONFIG:
                incoming.setdefault(section, {})
            incoming = restore_masked_secrets(incoming, secret_source or current)
            updated, _ = self._migrate_legacy_config(self._merge_with_defaults(incoming))
            # Import adopts migration markers, but explicit visibility choices
            # must survive the one-time visibility-default migration.
            for key in ('showOriginal', 'showTranslated', 'showTimestamp', 'showLatency', 'autoScroll'):
                if key in incoming.get('subtitle_settings', {}):
                    updated['subtitle_settings'][key] = incoming['subtitle_settings'][key]
            # Migration can move or fill legacy credentials. Preserve the exact
            # imported/restored values, including deliberately empty credentials.
            for section in ('general', 'transcription', 'translation'):
                for key in SECRET_KEYS:
                    if key in incoming.get(section, {}):
                        updated[section][key] = self._deep_copy(incoming[section][key])
            return self._persist_locked(updated)

    def update_key(self, path, value=None, *, delete=False):
        """Replace or delete one nested key in the latest disk state atomically."""
        if not path or any(not isinstance(key, str) for key in path):
            raise ValueError("Configuration key path must contain strings")
        with self._config_lock():
            current = self._read_current_config()
            parent = current
            for key in path[:-1]:
                if key not in parent:
                    if delete:
                        raise KeyError(tuple(path))
                    parent[key] = {}
                parent = parent[key]
                if not isinstance(parent, dict):
                    raise ValueError("Configuration key parent must be a mapping")
            if delete:
                del parent[path[-1]]
            else:
                parent[path[-1]] = self._deep_copy(value)
            self._validate_structure(current)
            return self._persist_locked(current)

    def _persist_locked(self, config):
        updated = self._enforce_packaged_runtime(config)
        from backend.core.hy_mt2_glossary_presets import _term_aliases
        for row in updated.get('terminology', {}).get('glossary_list', []):
            if isinstance(row, dict):
                row['aliases'] = _term_aliases(row)
        self._save(updated)
        self.config = updated
        self._file_signature = self._get_file_signature()
        return self._deep_copy(updated)

    def reset_to_defaults(self):
        """Back up the exact previous file before resetting under the lock."""
        with self._config_lock():
            if self.config_path.exists():
                shutil.copy2(self.config_path, self._backup_path('bak'))
            return self._persist_locked(self._profile_defaults())

