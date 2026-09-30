import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from marker_api import cache

PDF_A = b"%PDF-1.4 content A"
PDF_B = b"%PDF-1.4 content B"


def key(content=PDF_A, max_pages=10, start_page=0, langs=None):
    return cache.make_cache_key(content, max_pages, start_page, langs)


# ---- Cache Key ----

def test_same_content_same_key():
    assert key() == key()


def test_different_content_different_key():
    assert key(PDF_A) != key(PDF_B)


@pytest.mark.parametrize(
    "a,b",
    [
        ("English,French", "french, english"),
        (" English ", "english"),
        ("en,en", "en"),
        (None, ""),
        (None, " , "),
    ],
)
def test_langs_normalized(a, b):
    assert key(langs=a) == key(langs=b)


def test_langs_differ():
    assert key(langs="English") != key(langs="French")
    assert key(langs=None) != key(langs="English")


def test_options_differ():
    assert key(max_pages=10) != key(max_pages=30)
    assert key(start_page=0) != key(start_page=5)
    assert key(max_pages=None) != key(max_pages=0)


def test_key_is_filename_safe():
    k = key()
    assert "/" not in k and " " not in k and ".." not in k


# ---- load / save ----

def test_miss_returns_none(tmp_path):
    assert cache.load(key(), tmp_path) is None


def test_roundtrip(tmp_path):
    result = {"filename": "a.pdf", "markdown": "# hi 你好", "images": {}}
    assert cache.save(key(), result, tmp_path) is True
    assert cache.load(key(), tmp_path) == result


def test_creates_nested_cache_dir(tmp_path):
    d = tmp_path / "a" / "b" / "cache"
    assert cache.save(key(), {"x": 1}, d)
    assert cache.load(key(), d) == {"x": 1}


def test_upload_name_with_directories_does_not_matter(tmp_path):
    """回归测试:上传名形如 data/<sha>/x y.pdf 曾导致 FileNotFoundError。
    文件名不参与缓存路径,因此不会再出现。"""
    k = key()
    assert cache.save(k, {"filename": "data/3d6a/Calibre xRC User Manual.pdf"}, tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == [f"{k}.json"]


def test_corrupted_file_is_a_miss(tmp_path):
    (tmp_path / f"{key()}.json").write_text("{not json")
    assert cache.load(key(), tmp_path) is None


def test_non_dict_json_is_a_miss(tmp_path):
    (tmp_path / f"{key()}.json").write_text("[1, 2]")
    assert cache.load(key(), tmp_path) is None


def test_empty_file_is_a_miss(tmp_path):
    (tmp_path / f"{key()}.json").write_text("")
    assert cache.load(key(), tmp_path) is None


def test_corrupted_file_is_overwritten(tmp_path):
    (tmp_path / f"{key()}.json").write_text("{not json")
    assert cache.save(key(), {"ok": True}, tmp_path)
    assert cache.load(key(), tmp_path) == {"ok": True}


def test_unserializable_result_leaves_no_files(tmp_path):
    assert cache.save(key(), {"x": object()}, tmp_path) is False
    assert list(tmp_path.iterdir()) == []


def test_unwritable_dir_returns_false(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    # cache_dir 的父级是普通文件,mkdir 必然失败,save 不应抛异常
    assert cache.save(key(), {"x": 1}, blocker / "cache") is False


def test_no_temp_files_left_after_save(tmp_path):
    cache.save(key(), {"x": 1}, tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == [f"{key()}.json"]


def test_concurrent_writes_same_key(tmp_path):
    k = key()
    payloads = [{"n": i, "pad": "x" * 200_000} for i in range(16)]
    stop = threading.Event()
    bad = []

    def reader():
        while not stop.is_set():
            path = tmp_path / f"{k}.json"
            if path.exists():
                # 读到的必须是完整 JSON,不能是写了一半的文件
                try:
                    json.loads(path.read_text())
                except FileNotFoundError:
                    pass
                except ValueError as e:
                    bad.append(e)

    t = threading.Thread(target=reader)
    t.start()
    with ThreadPoolExecutor(8) as pool:
        assert all(pool.map(lambda p: cache.save(k, p, tmp_path), payloads))
    stop.set()
    t.join()

    assert bad == []
    assert cache.load(k, tmp_path) in payloads
    assert [p.name for p in tmp_path.iterdir()] == [f"{k}.json"]


# ---- 环境变量 ----

def test_cache_dir_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "c"))
    assert cache.save(key(), {"x": 1})
    assert cache.load(key()) == {"x": 1}


def test_cache_dir_default(monkeypatch):
    monkeypatch.delenv("CACHE_DIR", raising=False)
    assert str(cache.get_cache_dir()) == "/data/cache"
