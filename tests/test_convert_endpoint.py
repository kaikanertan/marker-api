"""/convert 端点的集成测试。marker / gradio 被 stub,只验证缓存行为。"""
import sys
from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("multipart")

from fastapi.testclient import TestClient  # noqa: E402

for name in ["marker", "marker.logger", "marker.models", "marker.convert", "gradio",
             "marker_api.demo", "marker_api.utils", "marker_api.routes", "art"]:
    sys.modules.setdefault(name, MagicMock())
# mount_gradio_app 原样返回 FastAPI app,否则 server.app 会变成 MagicMock
sys.modules["gradio"].mount_gradio_app = lambda app, *a, **k: app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    import importlib

    import server

    importlib.reload(server)
    calls = []

    def fake_process(file, filename, model_list, **kw):
        calls.append((filename, kw))
        return {"filename": filename, "markdown": f"md-{len(calls)}",
                "metadata": {}, "images": {}, "status": "ok", "time": 1.0}

    monkeypatch.setattr(server, "process_pdf_file", fake_process)
    c = TestClient(server.app)
    c.calls = calls
    c.cache_dir = tmp_path / "cache"
    return c


def post(client, name, content=b"%PDF A", **params):
    return client.post("/convert", params=params, files={"pdf_file": (name, content)})


def test_upload_name_with_directories_and_spaces(client):
    """回归:filename 形如 data/<sha>/Calibre xRC User Manual.pdf 曾导致 500。"""
    r = post(client, "data/3d6ab194/Calibre xRC User Manual.pdf", max_pages=30)
    assert r.status_code == 200, r.text
    assert r.json()["result"]["markdown"] == "md-1"
    assert len(list(client.cache_dir.glob("*.json"))) == 1


def test_hit_after_rename_returns_new_filename(client):
    post(client, "a.pdf")
    r = post(client, "renamed.pdf")
    assert len(client.calls) == 1
    assert r.json()["result"]["filename"] == "renamed.pdf"
    assert r.json()["result"]["markdown"] == "md-1"


def test_batch_multiplier_does_not_affect_hit(client):
    post(client, "a.pdf", batch_multiplier=2)
    post(client, "a.pdf", batch_multiplier=8)
    assert len(client.calls) == 1


def test_different_content_or_options_miss(client):
    post(client, "a.pdf")
    post(client, "a.pdf", content=b"%PDF B")
    post(client, "a.pdf", max_pages=30)
    post(client, "a.pdf", langs="English")
    assert len(client.calls) == 4


def test_corrupted_cache_reconverts(client):
    post(client, "a.pdf")
    (f,) = client.cache_dir.glob("*.json")
    f.write_text("{broken")
    r = post(client, "a.pdf")
    assert r.status_code == 200
    assert len(client.calls) == 2


def test_unwritable_cache_still_returns_result(client, monkeypatch, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    monkeypatch.setenv("CACHE_DIR", str(blocker / "cache"))
    r = post(client, "a.pdf")
    assert r.status_code == 200
