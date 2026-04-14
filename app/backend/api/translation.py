from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
import json
import asyncio
import copy
from backend.models.translation import StartTranslationRequest, TranslationTaskResponse, DeviceListResponse, AudioDevice
from backend.core.translator import active_translations, create_task, get_task, remove_task
from backend.core.config_manager import ConfigManager
from backend.core.app_sync import publish_app_event

router = APIRouter(prefix="/translation", tags=["translation"])
from backend.api.config import get_config_manager

@router.post("/start", response_model=TranslationTaskResponse)
async def start_translation(request: StartTranslationRequest, http_request: Request):
    """啟動翻譯任務"""
    try:
        if request.audio_source.value in ["url", "file"]:
            if not request.url or not request.url.strip():
                detail = "請提供直播 URL" if request.audio_source.value == "url" else "請提供檔案路徑"
                raise HTTPException(status_code=400, detail=detail)

        # 1. 取得當前全域配置的副本
        current_config = copy.deepcopy(get_config_manager().get_config())
        
        # 2. 根據請求參數覆蓋配置
        # 音訊來源覆蓋
        if request.audio_source:
            current_config['input']['audio_source'] = request.audio_source.value
        # device_index = None 代表使用系統預設設備，直接傳入底層
        current_config['input']['device_index'] = request.device_index
        
        # 輸入覆蓋
        if request.url:
            current_config['input']['url'] = request.url
            
        # 轉錄覆蓋
        if request.model:
            current_config['transcription']['model'] = request.model
        # 使用 transcription_engine 覆蓋轉錄後端（優先於 backend）
        if request.transcription_engine:
            current_config['transcription']['backend'] = request.transcription_engine
        elif request.backend:
            current_config['transcription']['backend'] = request.backend
        # Qwen3-ASR 模型覆蓋
        if request.qwen3_asr_model:
            current_config['transcription']['qwen3_asr_model'] = request.qwen3_asr_model
        # 🔧 新增: 覆蓋輸入語言
        if request.input_language:
            current_config['transcription']['language'] = request.input_language
            
        # 翻譯覆蓋
        # 🔧 新增: 根據 translation_enabled 決定是否啟用翻譯
        if not request.translation_enabled:
            # 關閉翻譯功能
            current_config['output_notification']['hide_transcribe_result'] = False
            # 不設定翻譯相關參數
            current_config['translation']['backend'] = 'none'
        else:
            # 啟用翻譯功能
            if request.target_language:
                current_config['translation']['target_language'] = request.target_language
            if request.gpt_model:
                current_config['translation']['gpt_model'] = request.gpt_model
            if request.translation_backend:
                current_config['translation']['backend'] = request.translation_backend
            
        # 進階覆蓋
        if request.override_config:
            # 遞迴合併邏輯簡單實作，假設 override_config 結構正確
            for section, values in request.override_config.items():
                if section in current_config and isinstance(values, dict):
                    current_config[section].update(values)
        
        # 3. 轉換為命令行參數
        cli_args = get_config_manager().to_main_args(current_config)
        
        # 4. 創建並啟動任務
        task_id = create_task(cli_args)
        
        context = get_task(task_id)
        if context:
            await context.start()
            
        response = {
            "success": True,
            "task_id": task_id,
            "sse_url": f"/api/translation/stream/{task_id}",
            "message": "Translation started"
        }
        await publish_app_event("translation.started", {
            "task_id": task_id,
            "url": getattr(context, 'url', '') if context else '',
            "source_client_id": http_request.headers.get("X-Client-Id", ""),
        })
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stream/{task_id}")
async def stream_subtitles(task_id: str):
    """SSE 端點：實時推送字幕"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"SSE connection started for task: {task_id}")
    
    context = get_task(task_id)
    if not context:
        logger.error(f"Task not found: {task_id}")
        raise HTTPException(status_code=404, detail="Task not found")
    
    logger.info(f"Task found, running={context.running}")
    
    async def event_generator():
        try:
            logger.info(f"Starting event generator for task {task_id}")
            event_count = 0
            async for event in context.stream_output():
                event_count += 1
                # SSE 格式: type(event) 和 data
                # 注意: SSE 標準格式是 `event: type\ndata: payload\n\n`
                if event["type"] == "ping":
                    yield ": ping\n\n" # comment keep-alive
                else:
                    # 詳細記錄每個事件
                    logger.info(f"[SSE] Sending event #{event_count} type={event['type']} data={event['data']}")
                    yield f"event: {event['type']}\n"
                    yield f"data: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
            logger.info(f"Event generator finished for task {task_id}, sent {event_count} events")
        except Exception as e:
            logger.error(f"Event generator error for task {task_id}: {e}", exc_info=True)
            yield f"event: error\n"
            yield f"data: {json.dumps({'message': f'Stream error: {str(e)}'}, ensure_ascii=False)}\n\n"
        finally:
            logger.info(f"Event generator cleanup for task {task_id}")
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )

@router.get("/status")
async def get_translation_status():
    """取得所有翻譯任務狀態"""
    tasks = []
    for task_id, context in active_translations.items():
        tasks.append({
            "task_id": task_id,
            "is_running": context.running,
            "url": getattr(context, 'url', ''),
        })
    
    return {
        "success": True,
        "active_tasks": len(tasks),
        "tasks": tasks
    }

@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """取得特定翻譯任務狀態"""
    context = get_task(task_id)
    if not context:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {
        "success": True,
        "task_id": task_id,
        "is_running": context.running,
        "url": getattr(context, 'url', ''),
    }

@router.delete("/stop/{task_id}")
async def stop_translation(task_id: str, request: Request):
    """停止翻譯任務"""
    context = get_task(task_id)
    if not context:
        raise HTTPException(status_code=404, detail="Task not found")
    
    await context.stop()
    remove_task(task_id)
    await publish_app_event("translation.stopped", {
        "task_id": task_id,
        "source_client_id": request.headers.get("X-Client-Id", ""),
    })
    
    return {"success": True, "task_id": task_id}

@router.get("/active-task")
async def get_active_task():
    """取得目前正在執行中的翻譯任務（供手機 PWA 使用）"""
    for task_id, context in active_translations.items():
        if context.running:
            return {"success": True, "task_id": task_id}
    return {"success": False, "task_id": None}

@router.get("/devices", response_model=DeviceListResponse)
async def list_audio_devices():
    """列出可用的音訊設備"""
    try:
        import sounddevice as sd
        import sys
        
        devices = {
            "microphones": [],
            "system_audio": []
        }
        
        # SoundDevice 設備 (麥克風)
        try:
            sd_devices = sd.query_devices()
            # 取得系統預設輸入設備索引
            try:
                default_input_index = sd.default.device[0]
            except Exception:
                default_input_index = -1
            for i, device in enumerate(sd_devices):
                if device['max_input_channels'] > 0:
                    devices["microphones"].append({
                        "index": i,
                        "name": device['name'],
                        "sample_rate": int(device['default_samplerate']),
                        "is_default": (i == default_input_index)
                    })
        except Exception as e:
            print(f"Error querying SoundDevice: {e}")
        
        # WASAPI Loopback 設備 (僅 Windows)
        if sys.platform == 'win32':
            try:
                import pyaudiowpatch as pyaudio
                p = pyaudio.PyAudio()
                wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
                first_loopback = True
                for i in range(wasapi_info.get('deviceCount')):
                    device = p.get_device_info_by_host_api_device_index(
                        wasapi_info.get('index'), i
                    )
                    if device.get('isLoopbackDevice', False):
                        # 嘗試用 pyaudiowpatch 取得預設輸出設備對應的 loopback
                        try:
                            default_output = p.get_default_wasapi_loopback()
                            is_def = (device.get('index') == default_output.get('index'))
                        except Exception:
                            # fallback: 第一個 loopback 設備視為預設
                            is_def = first_loopback
                        devices["system_audio"].append({
                            "index": device.get('index'),
                            "name": device.get('name'),
                            "sample_rate": int(device.get('defaultSampleRate')),
                            "is_default": is_def
                        })
                        first_loopback = False
                
                p.terminate()
            except ImportError:
                # pyaudiowpatch 未安裝
                pass
            except Exception as e:
                print(f"Error querying WASAPI devices: {e}")
        
        return {
            "success": True,
            "devices": devices
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
