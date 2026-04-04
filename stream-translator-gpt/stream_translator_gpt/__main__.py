import sys
import os
import functools

# 設定 Windows 控制台 UTF-8 編碼並禁用緩衝
if sys.platform == 'win32':
    # 設定環境變數
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONUTF8'] = '1'
    os.environ['PYTHONUNBUFFERED'] = '1'
    
    # 重新配置 stdout/stderr 使用 UTF-8 並設為行緩衝 (line_buffering=True)
    import io
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    except AttributeError:
        # Python < 3.7
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    
    # 包裝 print 函式強制 flush
    _original_print = print
    @functools.wraps(_original_print)
    def _flushing_print(*args, **kwargs):
        kwargs.setdefault('flush', True)
        return _original_print(*args, **kwargs)
    import builtins
    builtins.print = _flushing_print

from .main import cli

if __name__ == '__main__':
    cli()