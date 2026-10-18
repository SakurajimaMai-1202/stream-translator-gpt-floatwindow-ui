import subprocess
import sys
from pathlib import Path

# Mirrors the excludes in app/packaging/stream-translator-llm-gui.spec: the GUI
# backend runs test translations in-process without the ML stack.
GUI_EXCLUDED = ["torch", "faster_whisper", "transformers", "onnxruntime", "scipy", "numpy", "librosa", "yt_dlp"]

SCRIPT = """
import sys
blocked = set(sys.argv[1:])
class Block:
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in blocked:
            raise ImportError('excluded from the GUI exe: ' + name)
sys.meta_path.insert(0, Block())
from stream_translator_gpt.llm_translator import LLMClient, normalize_translation_output
from stream_translator_gpt.common import TranslationTask
task = TranslationTask(None, (0, 0))
print('ok')
"""


def test_preview_path_imports_without_ml_stack():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-c", SCRIPT, *GUI_EXCLUDED], cwd=root,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
