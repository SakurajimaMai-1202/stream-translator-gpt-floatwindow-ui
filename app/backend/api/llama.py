"""
Llama.cpp 整合 API

提供 llama.cpp 模型管理和推論功能
可供 UI2 和 llama launcher 共用
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from pathlib import Path
import subprocess
import asyncio
import logging
import os
from backend.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llama", tags=["Llama"])

# 全域狀態管理
class LlamaState:
    def __init__(self):
        self.server_process: Optional[subprocess.Popen] = None
        self.server_url: Optional[str] = None
        self.is_running: bool = False
        self.is_ready: bool = False  # 新增就緒狀態
        self.current_model: Optional[str] = None
        
llama_state = LlamaState()


# ==================== 啟動探測 ====================

async def probe_existing_llama_server() -> bool:
    """
    啟動時探測是否有現有的 llama.cpp 伺服器在執行中。
    讀取設定的 host/port（預設 127.0.0.1:8080），嘗試連線 /health。
    若成功，進一步查詢 /props 或 /v1/models 取得模型名稱，並更新 llama_state。
    """
    if llama_state.is_running:
        return False  # 本 app 已管理一個伺服器，不需探測

    # 讀取設定的 host/port
    try:
        from backend.api.config import get_config_manager
        cfg = get_config_manager().get_config()
        llama_cfg = cfg.get('llama', {})
        host = llama_cfg.get('host', '127.0.0.1')
        port = int(llama_cfg.get('port', 8080))
    except Exception:
        host = '127.0.0.1'
        port = 8080

    url = f"http://{host}:{port}"

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            # 1) /health 健康檢查
            resp = await client.get(f"{url}/health", timeout=2.0)
            if resp.status_code != 200:
                return False

            # 2) 嘗試從 /props 取得正在執行的模型路徑
            model_name: Optional[str] = None
            try:
                props_resp = await client.get(f"{url}/props", timeout=2.0)
                if props_resp.status_code == 200:
                    props = props_resp.json()
                    model_path = (
                        props.get('default_generation_settings', {}).get('model', '')
                        or props.get('model', '')
                    )
                    if model_path:
                        model_name = Path(model_path).name
            except Exception:
                pass

            # 3) fallback：嘗試 /v1/models（OpenAI-compatible endpoint）
            if not model_name:
                try:
                    models_resp = await client.get(f"{url}/v1/models", timeout=2.0)
                    if models_resp.status_code == 200:
                        data = models_resp.json()
                        models_list = data.get('data', [])
                        if models_list:
                            model_name = models_list[0].get('id', '') or None
                except Exception:
                    pass

            # 更新全域狀態
            llama_state.is_running = True
            llama_state.is_ready = True
            llama_state.server_url = url
            llama_state.current_model = model_name or '未知模型'
            llama_state.server_process = None  # 非本 app 啟動，無 process 物件

            logger.info(f"✅ 偵測到現有 llama 伺服器: {url}，模型: {llama_state.current_model}")
            return True

    except Exception as e:
        logger.debug(f"未偵測到 llama 伺服器 ({url}): {e}")
        return False

# ==================== 資料模型 ====================

class ModelInfo(BaseModel):
    """模型資訊"""
    name: str
    path: str
    size_mb: float
    modified_time: str

class ServerConfig(BaseModel):
    """伺服器配置"""
    model_path: str = ""
    host: str = "127.0.0.1"
    port: int = 8080
    n_ctx: int = 2048
    n_gpu_layers: int = 0
    n_threads: int = 4
    n_parallel: int = 1
    server_exe: Optional[str] = None
    
    # 進階生成參數
    top_k: int = 40
    top_p: float = 0.95
    temp: float = 0.8
    repeat_penalty: float = 1.1
    n_predict: int = 512
    
    # 進階性能參數
    flash_attn: bool = True
    no_mmap: bool = False

class ServerStatus(BaseModel):
    """伺服器狀態"""
    is_running: bool
    is_ready: bool  # 新增就緒狀態
    server_url: Optional[str]
    current_model: Optional[str]
    pid: Optional[int]

class InferenceRequest(BaseModel):
    """推論請求"""
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.8
    top_p: float = 0.95
    stop: Optional[List[str]] = None

class TranslateRequest(BaseModel):
    """翻譯請求"""
    text: str
    source_lang: str = "English"
    target_lang: str = "Traditional Chinese"
    context: Optional[str] = None

# ==================== API 端點 ====================

@router.get("/models")
async def list_models(model_dir: Optional[str] = None):
    """
    列出目錄下所有 GGUF 模型
    
    Args:
        model_dir: 模型目錄路徑，如果未提供則使用預設目錄
    """
    if not model_dir:
        model_dir = "."
    
    try:
        dir_path = Path(model_dir)
        if not dir_path.exists():
            return []
        
        models = []
        for file in dir_path.rglob("*.gguf"):
            try:
                stat = file.stat()
                models.append(ModelInfo(
                    name=file.name,
                    path=str(file.absolute()),
                    size_mb=stat.st_size / (1024 * 1024),
                    modified_time=str(stat.st_mtime)
                ))
            except Exception as e:
                logger.warning(f"Failed to get info for {file}: {e}")
                continue
        
        # 按名稱排序
        models.sort(key=lambda x: x.name)
        return models
        
    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        raise HTTPException(status_code=500, detail=f"列出模型失敗: {str(e)}")

@router.post("/server/start")
async def start_server(config: ServerConfig, background_tasks: BackgroundTasks):
    """
    啟動 llama.cpp 伺服器
    """
    if llama_state.is_running:
        raise HTTPException(status_code=400, detail="伺服器已在執行中")
    
    # 重置就緒狀態
    llama_state.is_ready = False
    
    # 建立命令
    if not config.model_path:
        raise HTTPException(status_code=400, detail="未選擇模型")
        
    model_path = Path(config.model_path)
    if not model_path.exists():
        raise HTTPException(status_code=400, detail=f"模型文件不存在: {config.model_path}")
    
    # 尋找 llama-server 執行檔
    if config.server_exe:
        server_exe = Path(config.server_exe)
    else:
        # 預設路徑
        possible_paths = [
            # 嘗試使用 settings Based 路徑
            settings.BASE_DIR / "../llama/llama-server.exe",
            settings.BASE_DIR / "llama/llama-server.exe",
            # CWD 相對路徑
            Path("llama.cpp/bin/llama-server.exe"),
            Path("llama-server.exe"),
            Path("llama.cpp/llama-server.exe"),
            Path("../llama/llama-server.exe")
        ]
        server_exe = None
        for p in possible_paths:
            if p.exists():
                server_exe = p.resolve() # 獲取絕對路徑
                break
        
        if not server_exe:
            raise HTTPException(status_code=400, detail="找不到 llama-server.exe，請在設定中指定路徑或確認安裝位置")
    
    # 建構命令列參數
    cmd = [
        str(server_exe),
        "-m", str(model_path),
        "--host", config.host,
        "--port", str(config.port),
        "-c", str(config.n_ctx),
        "-ngl", str(config.n_gpu_layers),
        "-t", str(config.n_threads),
        "-np", str(config.n_parallel),
        "--top-k", str(config.top_k),
        "--top-p", str(config.top_p),
        "--temp", str(config.temp),
        "--repeat-penalty", str(config.repeat_penalty),
        "-n", str(config.n_predict)
    ]
    
    # 進階選項
    if config.flash_attn:
        cmd.extend(["--flash-attn", "on"])
    if config.no_mmap:
        cmd.append("--no-mmap")
    
    try:
        # 記錄完整命令
        logger.info(f"Starting Llama server with command: {' '.join(cmd)}")
        
        # 啟動子程序
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            text=True,    # 啟用文本模式
            bufsize=1,    # 行緩衝
            encoding='utf-8', 
            errors='replace'
        )
        
        # 啟動輸出讀取線程
        def log_output(pipe, prefix):
            try:
                for line in iter(pipe.readline, ''):
                    if line:
                        line_stripped = line.strip()
                        logger.info(f"[{prefix}] {line_stripped}")
                        
                        # 检测是否就绪
                        if "listening on" in line_stripped or "HTTP server listening" in line_stripped:
                            if not llama_state.is_ready:
                                logger.info("Llama server is ready to accept requests!")
                                llama_state.is_ready = True
                                
                pipe.close()
            except Exception as e:
                logger.error(f"Error reading {prefix}: {e}")

        import threading
        threading.Thread(target=log_output, args=(process.stdout, "Llama-Stdout"), daemon=True).start()
        threading.Thread(target=log_output, args=(process.stderr, "Llama-Stderr"), daemon=True).start()
        
        # 更新狀態
        llama_state.server_process = process
        llama_state.is_running = True
        llama_state.server_url = f"http://{config.host}:{config.port}"
        llama_state.current_model = Path(config.model_path).name
        
        return {
            "status": "started",
            "pid": process.pid,
            "url": llama_state.server_url
        }
        
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        # 確保清理
        if 'process' in locals() and process:
            process.kill()
        llama_state.is_running = False
        raise HTTPException(status_code=500, detail=f"伺服器啟動失敗: {str(e)}")

@router.post("/server/stop")
async def stop_server():
    """停止 llama.cpp 伺服器"""
    if not llama_state.is_running:
        raise HTTPException(status_code=400, detail="伺服器未執行")
    
    try:
        if llama_state.server_process:
            llama_state.server_process.terminate()
            try:
                llama_state.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                llama_state.server_process.kill()
        
        llama_state.server_process = None
        llama_state.is_running = False
        llama_state.is_ready = False  # 重置就緒狀態
        llama_state.server_url = None
        llama_state.current_model = None
        
        return {"status": "stopped"}
        
    except Exception as e:
        logger.error(f"Failed to stop server: {e}")
        raise HTTPException(status_code=500, detail=f"停止伺服器失敗: {str(e)}")


@router.get("/server/status", response_model=ServerStatus)
async def get_server_status():
    """獲取伺服器狀態"""
    return ServerStatus(
        is_running=llama_state.is_running,
        is_ready=llama_state.is_ready,  # 返回就緒狀態
        server_url=llama_state.server_url,
        current_model=llama_state.current_model,
        pid=llama_state.server_process.pid if llama_state.server_process else None
    )


@router.post("/inference")
async def inference(request: InferenceRequest):
    """
    執行推論（需要先啟動伺服器）
    
    Args:
        request: 推論請求參數
    """
    if not llama_state.is_running:
        raise HTTPException(status_code=400, detail="伺服器未啟動，請先啟動 llama 伺服器")
    
    try:
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{llama_state.server_url}/completion",
                json={
                    "prompt": request.prompt,
                    "n_predict": request.max_tokens,
                    "temperature": request.temperature,
                    "top_p": request.top_p,
                    "stop": request.stop or []
                },
                timeout=60.0
            )
            response.raise_for_status()
            result = response.json()
            
            return {
                "text": result.get("content", ""),
                "tokens_predicted": result.get("tokens_predicted", 0),
                "model": llama_state.current_model
            }
            
    except httpx.HTTPError as e:
        logger.error(f"推論請求失敗: {e}")
        raise HTTPException(status_code=500, detail=f"推論失敗: {str(e)}")


@router.post("/translate")
async def translate_with_llama(request: TranslateRequest):
    """
    使用 llama 進行翻譯
    
    Args:
        request: 翻譯請求參數
    """
    if not llama_state.is_running:
        raise HTTPException(status_code=400, detail="Llama 伺服器未啟動")
    
    # 建構翻譯提示詞
    prompt = f"""You are a professional translator. Translate the following text from {request.source_lang} to {request.target_lang}.
Only output the translated text without any explanation.

{f"Context: {request.context}" if request.context else ""}

Text to translate:
{request.text}

Translation:"""
    
    try:
        result = await inference(InferenceRequest(
            prompt=prompt,
            max_tokens=512,
            temperature=0.3,
            stop=["\n\n"]
        ))
        
        return {
            "original": request.text,
            "translated": result["text"].strip(),
            "model": llama_state.current_model
        }
        
    except Exception as e:
        logger.error(f"翻譯失敗: {e}")
        raise HTTPException(status_code=500, detail=f"翻譯失敗: {str(e)}")


# ==================== 健康檢查 ====================

@router.get("/health")
async def health_check():
    """健康檢查"""
    return {
        "status": "ok",
        "server_running": llama_state.is_running,
        "current_model": llama_state.current_model
    }


# ==================== 預設配置 ====================

PRESETS = {
    "VTuber 雜談（翻譯優化）": {
        "n_ctx": 2048,
        "n_gpu_layers": 99,
        "n_threads": 8,
        "n_parallel": 1,
        "flash_attn": True,
        "no_mmap": False,
        "top_k": 40,
        "top_p": 1.0,
        "temp": 0.1,
        "repeat_penalty": 1.05,
        "n_predict": 512
    },
    "小說/文本翻譯（精準模式）": {
        "n_ctx": 8192,
        "n_gpu_layers": 99,
        "n_threads": 8,
        "n_parallel": 1,
        "flash_attn": True,
        "no_mmap": False,
        "top_k": 20,
        "top_p": 0.9,
        "temp": 0.3,
        "repeat_penalty": 1.1,
        "n_predict": 2048
    },
    "遊戲同步翻譯（低延遲）": {
        "n_ctx": 1024,
        "n_gpu_layers": 99,
        "n_threads": 12,
        "n_parallel": 1,
        "flash_attn": True,
        "no_mmap": True,
        "top_k": 50,
        "top_p": 0.95,
        "temp": 0.5,
        "repeat_penalty": 1.0,
        "n_predict": 256
    }
}


@router.get("/presets")
async def get_presets():
    """獲取預設配置列表"""
    return {"presets": PRESETS}


# ==================== 自訂配置管理 ====================

@router.get("/presets/custom")
async def get_custom_presets():
    """獲取用戶自訂配置列表"""
    from backend.api.config import get_config_manager
    config = get_config_manager().get_config()
    return config.get('llama', {}).get('custom_presets', {})


@router.get("/presets/{preset_name}")
async def get_preset(preset_name: str):
    """獲取特定預設配置"""
    if preset_name not in PRESETS:
        raise HTTPException(status_code=404, detail=f"預設配置不存在: {preset_name}")
    return PRESETS[preset_name]

@router.post("/presets/custom/{name}")
async def save_custom_preset(name: str, config: ServerConfig):
    """保存用戶自訂配置"""
    from backend.api.config import get_config_manager
    config_manager = get_config_manager()
    
    # 獲取當前配置
    full_config = config_manager.get_config()
    if 'llama' not in full_config:
        full_config['llama'] = {}
    if 'custom_presets' not in full_config['llama']:
        full_config['llama']['custom_presets'] = {}
    
    # 保存新的自訂配置（包含模型路徑和服務器參數）
    full_config['llama']['custom_presets'][name] = {
        'model_path': config.model_path,  # 保存模型路徑
        'host': config.host,
        'port': config.port,
        'n_ctx': config.n_ctx,
        'n_gpu_layers': config.n_gpu_layers,
        'n_threads': config.n_threads,
        'n_parallel': config.n_parallel,
        'top_k': config.top_k,
        'top_p': config.top_p,
        'temp': config.temp,
        'repeat_penalty': config.repeat_penalty,
        'n_predict': config.n_predict,
        'flash_attn': config.flash_attn,
        'no_mmap': config.no_mmap
    }
    
    logger.info(f"Saved custom preset '{name}' with model: {config.model_path}")
    
    # 保存完整配置
    config_manager.update_section('llama', full_config['llama'])
    
    return {"status": "saved", "name": name}

@router.delete("/presets/custom/{name}")
async def delete_custom_preset(name: str):
    """刪除用戶自訂配置"""
    from backend.api.config import get_config_manager
    config_manager = get_config_manager()
    
    # 獲取當前配置
    full_config = config_manager.get_config()
    custom_presets = full_config.get('llama', {}).get('custom_presets', {})
    
    if name not in custom_presets:
        raise HTTPException(status_code=404, detail=f"自訂配置不存在: {name}")
    
    # 刪除配置
    del custom_presets[name]
    full_config['llama']['custom_presets'] = custom_presets
    
    # 保存
    config_manager.update_section('llama', full_config['llama'])
    
    return {"status": "deleted", "name": name}
