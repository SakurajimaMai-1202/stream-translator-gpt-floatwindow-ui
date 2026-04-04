"""
Llama.cpp 模型管理器

負責管理 llama.cpp 伺服器的生命週期和模型載入
提供統一的介面供翻譯引擎使用
"""
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)


class LlamaManager:
    """Llama.cpp 管理器"""
    
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.server_url: Optional[str] = None
        self.is_running: bool = False
        self.current_model: Optional[str] = None
        self.config: Dict[str, Any] = {}
        
    def start_server(
        self,
        model_path: str,
        host: str = "127.0.0.1",
        port: int = 8080,
        n_ctx: int = 2048,
        n_gpu_layers: int = 0,
        n_threads: int = 4,
        server_exe: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        啟動 llama-server
        
        Args:
            model_path: 模型檔案路徑
            host: 伺服器主機
            port: 伺服器埠號
            n_ctx: 上下文長度
            n_gpu_layers: GPU 層數
            n_threads: 執行緒數
            server_exe: llama-server.exe 路徑
            
        Returns:
            包含啟動資訊的字典
        """
        if self.is_running:
            raise RuntimeError("伺服器已在執行中")
        
        # 檢查模型檔案
        model_file = Path(model_path)
        if not model_file.exists():
            raise FileNotFoundError(f"模型檔案不存在: {model_path}")
        
        # 尋找 llama-server.exe
        if server_exe and Path(server_exe).exists():
            exe_path = Path(server_exe)
        else:
            # 預設路徑
            exe_path = Path(__file__).parent.parent.parent.parent / "llama" / "llama-server.exe"
            if not exe_path.exists():
                raise FileNotFoundError("找不到 llama-server.exe")
        
        # 組建命令
        cmd = [
            str(exe_path),
            "-m", str(model_file),
            "--host", host,
            "--port", str(port),
            "-c", str(n_ctx),
            "-ngl", str(n_gpu_layers),
            "-t", str(n_threads),
        ]
        
        try:
            # 啟動子程序
            import os
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # 更新狀態
            self.server_url = f"http://{host}:{port}"
            self.is_running = True
            self.current_model = model_file.name
            self.config = {
                "host": host,
                "port": port,
                "n_ctx": n_ctx,
                "n_gpu_layers": n_gpu_layers,
                "n_threads": n_threads
            }
            
            logger.info(f"Llama 伺服器已啟動: {self.server_url} (模型: {self.current_model})")
            
            return {
                "status": "started",
                "pid": self.process.pid,
                "url": self.server_url,
                "model": self.current_model
            }
            
        except Exception as e:
            logger.error(f"啟動 llama 伺服器失敗: {e}")
            raise
    
    def stop_server(self) -> Dict[str, str]:
        """
        停止 llama-server
        
        Returns:
            包含停止狀態的字典
        """
        if not self.is_running or not self.process:
            raise RuntimeError("伺服器未在執行")
        
        try:
            self.process.terminate()
            self.process.wait(timeout=5)
            
            self.process = None
            self.is_running = False
            self.server_url = None
            self.current_model = None
            self.config = {}
            
            logger.info("Llama 伺服器已停止")
            return {"status": "stopped"}
            
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process = None
            self.is_running = False
            logger.warning("Llama 伺服器強制終止")
            return {"status": "killed"}
    
    async def translate(
        self,
        text: str,
        source_lang: str = "English",
        target_lang: str = "Traditional Chinese",
        context: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 512
    ) -> str:
        """
        使用 llama 翻譯文字
        
        Args:
            text: 要翻譯的文字
            source_lang: 來源語言
            target_lang: 目標語言
            context: 上下文資訊
            temperature: 溫度參數
            max_tokens: 最大 token 數
            
        Returns:
            翻譯後的文字
        """
        if not self.is_running:
            raise RuntimeError("Llama 伺服器未啟動")
        
        # 建構翻譯提示詞
        prompt = f"""You are a professional translator. Translate the following text from {source_lang} to {target_lang}.
Only output the translated text without any explanation.

{f"Context: {context}" if context else ""}

Text to translate:
{text}

Translation:"""
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.server_url}/completion",
                    json={
                        "prompt": prompt,
                        "n_predict": max_tokens,
                        "temperature": temperature,
                        "top_p": 0.9,
                        "stop": ["\n\n", "Text to translate:"]
                    },
                    timeout=60.0
                )
                response.raise_for_status()
                result = response.json()
                
                translated = result.get("content", "").strip()
                logger.debug(f"翻譯完成: {text[:50]}... -> {translated[:50]}...")
                return translated
                
        except Exception as e:
            logger.error(f"翻譯失敗: {e}")
            raise
    
    async def inference(
        self,
        prompt: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        執行通用推論
        
        Args:
            prompt: 輸入提示詞
            max_tokens: 最大 token 數
            temperature: 溫度參數
            top_p: Top-p 採樣
            stop: 停止符號列表
            
        Returns:
            包含推論結果的字典
        """
        if not self.is_running:
            raise RuntimeError("Llama 伺服器未啟動")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.server_url}/completion",
                    json={
                        "prompt": prompt,
                        "n_predict": max_tokens,
                        "temperature": temperature,
                        "top_p": top_p,
                        "stop": stop or []
                    },
                    timeout=60.0
                )
                response.raise_for_status()
                result = response.json()
                
                return {
                    "text": result.get("content", ""),
                    "tokens_predicted": result.get("tokens_predicted", 0),
                    "model": self.current_model
                }
                
        except Exception as e:
            logger.error(f"推論失敗: {e}")
            raise
    
    def get_status(self) -> Dict[str, Any]:
        """
        獲取當前狀態
        
        Returns:
            包含狀態資訊的字典
        """
        return {
            "is_running": self.is_running,
            "server_url": self.server_url,
            "current_model": self.current_model,
            "pid": self.process.pid if self.process else None,
            "config": self.config
        }
    
    async def health_check(self) -> bool:
        """
        檢查伺服器健康狀態
        
        Returns:
            True 如果伺服器正常運作
        """
        if not self.is_running:
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.server_url}/health",
                    timeout=5.0
                )
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"健康檢查失敗: {e}")
            return False
    
    def __del__(self):
        """清理資源"""
        if self.is_running and self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except:
                pass


# 全域實例
llama_manager = LlamaManager()
