"""
LLM 翻譯器集成

支援多種翻譯引擎：GPT、Gemini、Llama
"""
import logging
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class TranslationEngine(str, Enum):
    """翻譯引擎類型"""
    GPT = "gpt"
    GEMINI = "gemini"
    LLAMA = "llama"


class LLMTranslator:
    """統一的 LLM 翻譯介面"""
    
    def __init__(
        self,
        engine: TranslationEngine = TranslationEngine.GPT,
        model: Optional[str] = None,
        prompt: Optional[str] = None,
        history_size: int = 3,
        use_json_result: bool = False,
        **kwargs
    ):
        """
        初始化翻譯器
        
        Args:
            engine: 翻譯引擎類型
            model: 模型名稱
            prompt: 自訂提示詞
            history_size: 歷史訊息數量
            use_json_result: 是否使用 JSON 格式結果
            **kwargs: 引擎特定參數
        """
        self.engine = engine
        self.model = model
        self.prompt = prompt or self._default_prompt()
        self.history_size = history_size
        self.use_json_result = use_json_result
        self.history_messages: List[Dict] = []
        self.kwargs = kwargs
        
        # 根據引擎類型初始化客戶端
        self._client = None
        self._init_client()
    
    def _default_prompt(self) -> str:
        """預設翻譯提示詞"""
        return (
            "You are a professional translator. "
            "Translate the text accurately and naturally. "
            "Preserve the original meaning and tone."
        )
    
    def _init_client(self):
        """初始化翻譯客戶端"""
        if self.engine == TranslationEngine.GPT:
            self._init_gpt_client()
        elif self.engine == TranslationEngine.GEMINI:
            self._init_gemini_client()
        elif self.engine == TranslationEngine.LLAMA:
            self._init_llama_client()
        else:
            raise ValueError(f"不支援的翻譯引擎: {self.engine}")
    
    def _init_gpt_client(self):
        """初始化 GPT 客戶端"""
        try:
            from openai import OpenAI
            import httpx
            
            proxy = self.kwargs.get('proxy')
            api_key = self.kwargs.get('api_key')
            base_url = self.kwargs.get('base_url')
            
            client_kwargs = {}
            if proxy:
                client_kwargs['http_client'] = httpx.Client(proxy=proxy)
            if api_key:
                client_kwargs['api_key'] = api_key
            if base_url:
                client_kwargs['base_url'] = base_url
            
            self._client = OpenAI(**client_kwargs)
            logger.info(f"GPT 客戶端已初始化 (模型: {self.model})")
            
        except ImportError:
            logger.error("OpenAI 函式庫未安裝，請執行: pip install openai")
            raise
    
    def _init_gemini_client(self):
        """初始化 Gemini 客戶端"""
        try:
            import google.generativeai as genai
            
            api_key = self.kwargs.get('api_key')
            if not api_key:
                raise ValueError("Gemini 需要 API key")
            
            genai.configure(api_key=api_key)
            self._client = genai.GenerativeModel(self.model)
            logger.info(f"Gemini 客戶端已初始化 (模型: {self.model})")
            
        except ImportError:
            logger.error("Google AI 函式庫未安裝，請執行: pip install google-generativeai")
            raise
    
    def _init_llama_client(self):
        """初始化 Llama 客戶端（使用本地 llama_manager）"""
        try:
            from backend.core.llama_manager import llama_manager
            
            if not llama_manager.is_running:
                logger.warning("Llama 伺服器未啟動，將在翻譯時自動啟動")
            
            self._client = llama_manager
            logger.info(f"Llama 客戶端已初始化 (伺服器: {llama_manager.server_url})")
            
        except ImportError:
            logger.error("Llama 管理器未安裝")
            raise
    
    async def translate(
        self,
        text: str,
        source_lang: str = "English",
        target_lang: str = "Traditional Chinese",
        context: Optional[str] = None
    ) -> str:
        """
        翻譯文字
        
        Args:
            text: 要翻譯的文字
            source_lang: 來源語言
            target_lang: 目標語言
            context: 上下文資訊
            
        Returns:
            翻譯後的文字
        """
        if not text or not text.strip():
            return ""
        
        try:
            if self.engine == TranslationEngine.GPT:
                return await self._translate_with_gpt(text, source_lang, target_lang, context)
            elif self.engine == TranslationEngine.GEMINI:
                return await self._translate_with_gemini(text, source_lang, target_lang, context)
            elif self.engine == TranslationEngine.LLAMA:
                return await self._translate_with_llama(text, source_lang, target_lang, context)
            else:
                raise ValueError(f"不支援的翻譯引擎: {self.engine}")
                
        except Exception as e:
            logger.error(f"翻譯失敗 ({self.engine}): {e}")
            raise
    
    async def _translate_with_gpt(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: Optional[str]
    ) -> str:
        """使用 GPT 翻譯"""
        messages = [{"role": "system", "content": self.prompt}]
        
        # 添加歷史訊息
        messages.extend(self.history_messages)
        
        # 建構用戶訊息
        user_message = f"Translate from {source_lang} to {target_lang}:\n{text}"
        if context:
            user_message = f"Context: {context}\n\n{user_message}"
        
        messages.append({"role": "user", "content": user_message})
        
        # 呼叫 API
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3,
            max_tokens=512
        )
        
        translated = response.choices[0].message.content.strip()
        
        # 更新歷史
        self._append_history(user_message, translated)
        
        return translated
    
    async def _translate_with_gemini(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: Optional[str]
    ) -> str:
        """使用 Gemini 翻譯"""
        prompt = f"{self.prompt}\n\nTranslate from {source_lang} to {target_lang}:\n{text}"
        if context:
            prompt = f"Context: {context}\n\n{prompt}"
        
        response = self._client.generate_content(prompt)
        translated = response.text.strip()
        
        return translated
    
    async def _translate_with_llama(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        context: Optional[str]
    ) -> str:
        """使用 Llama 翻譯"""
        return await self._client.translate(
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
            context=context,
            temperature=0.3,
            max_tokens=512
        )
    
    def _append_history(self, user_content: str, assistant_content: str):
        """添加歷史訊息"""
        if not user_content or not assistant_content:
            return
        
        self.history_messages.extend([
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content}
        ])
        
        # 保持歷史大小
        while len(self.history_messages) > self.history_size * 2:
            self.history_messages.pop(0)
    
    def clear_history(self):
        """清空歷史訊息"""
        self.history_messages.clear()
    
    def get_info(self) -> Dict[str, Any]:
        """獲取翻譯器資訊"""
        info = {
            "engine": self.engine.value,
            "model": self.model,
            "history_size": self.history_size,
            "history_count": len(self.history_messages) // 2
        }
        
        if self.engine == TranslationEngine.LLAMA:
            info["llama_status"] = self._client.get_status()
        
        return info


# ==================== 工廠函式 ====================

def create_translator(config: Dict[str, Any]) -> LLMTranslator:
    """
    根據配置建立翻譯器
    
    Args:
        config: 翻譯配置
        
    Returns:
        LLMTranslator 實例
    """
    # 判斷使用哪種引擎
    if config.get('use_llama', False):
        engine = TranslationEngine.LLAMA
        model = config.get('llama_model', 'default')
    elif config.get('gemini_model'):
        engine = TranslationEngine.GEMINI
        model = config['gemini_model']
    else:
        engine = TranslationEngine.GPT
        model = config.get('gpt_model', 'gpt-3.5-turbo')
    
    return LLMTranslator(
        engine=engine,
        model=model,
        prompt=config.get('translation_prompt'),
        history_size=config.get('translation_history_size', 3),
        use_json_result=config.get('use_json_result', False),
        proxy=config.get('proxy'),
        api_key=config.get('openai_api_key') or config.get('google_api_key'),
        base_url=config.get('gpt_base_url') or config.get('gemini_base_url')
    )
