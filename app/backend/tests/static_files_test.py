import ast
from pathlib import Path

import pytest
from backend.static_files import resolve_static_file


@pytest.fixture
def static_root(tmp_path):
    root = tmp_path / "static"
    root.mkdir()
    (root / "index.html").write_text("SPA index", encoding="utf-8")
    (root / "file.txt").write_text("static content", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("outside secret", encoding="utf-8")
    return root


def test_resolve_static_file_serves_normal_file(static_root):
    assert resolve_static_file(static_root, "file.txt") == (static_root / "file.txt").resolve()


@pytest.mark.parametrize("full_path", [
    "..%2Foutside.txt", "../outside.txt", "..\\outside.txt",
    "C:/outside.txt", "C:outside.txt", "/outside.txt",
    "\\outside.txt", "\\\\server\\share\\outside.txt", "missing/route", "", "bad\0path",
])
def test_resolve_static_file_falls_back(static_root, full_path):
    candidate = resolve_static_file(static_root, full_path)
    assert candidate is None
    assert (candidate or static_root / "index.html").read_text(encoding="utf-8") == "SPA index"


def test_resolve_static_file_rejects_actual_absolute_path(static_root):
    assert resolve_static_file(static_root, str(static_root.parent / "outside.txt")) is None


@pytest.mark.parametrize("module_name", ["main.py", "public_app.py"])
def test_spa_fallback_requests(static_root, module_name):
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse
    from fastapi.testclient import TestClient

    # 擷取實際 handler，避免匯入完整應用啟動模型、設定或背景服務。
    source = Path(__file__).resolve().parents[1] / module_name
    tree = ast.parse(source.read_text(encoding="utf-8"))
    handler = next(node for node in ast.walk(tree)
                   if isinstance(node, ast.AsyncFunctionDef) and node.name == "spa_fallback")
    handler.decorator_list = []
    namespace = {
        "static_root": static_root,
        "index_file": static_root / "index.html",
        "FileResponse": FileResponse,
        "HTTPException": HTTPException,
        "resolve_static_file": resolve_static_file,
    }
    exec(compile(ast.Module(body=[handler], type_ignores=[]), str(source), "exec"), namespace)
    app = FastAPI()
    app.add_api_route("/{full_path:path}", namespace["spa_fallback"], methods=["GET"])
    with TestClient(app) as client:
        static_response = client.get("/file.txt")
        assert static_response.text == "static content"
        assert "cache-control" not in static_response.headers
        assert client.get("/index.html").headers["cache-control"] == "no-cache"
        for url in ["/..%2Foutside.txt", "/../outside.txt", "/..%5Coutside.txt",
                    "/C:/outside.txt", "/desktop"]:
            response = client.get(url)
            assert response.status_code == 200
            assert response.text == "SPA index"
            assert response.headers["cache-control"] == "no-cache"
        if module_name == "public_app.py":
            assert client.get("/api/unknown").status_code == 404


def test_main_index_requires_revalidation(static_root):
    import asyncio
    from fastapi.responses import FileResponse

    source = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    handler = next(node for node in ast.walk(tree)
                   if isinstance(node, ast.AsyncFunctionDef) and node.name == "serve_index")
    handler.decorator_list = []
    namespace = {"index_file": static_root / "index.html", "FileResponse": FileResponse}
    exec(compile(ast.Module(body=[handler], type_ignores=[]), str(source), "exec"), namespace)
    response = asyncio.run(namespace["serve_index"]())
    assert response.headers["cache-control"] == "no-cache"
