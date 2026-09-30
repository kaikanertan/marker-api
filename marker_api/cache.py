"""Conversion Cache: 按 Cache Key 保存 Conversion Result(JSON 文件)。

Cache Key = sha256(文件内容) + max_pages + start_page + 规范化后的 langs。
上传文件名和 batch_multiplier 不参与缓存键。
"""

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = "/data/cache"


def get_cache_dir() -> Path:
    return Path(os.environ.get("CACHE_DIR", DEFAULT_CACHE_DIR))


def normalize_langs(langs: Optional[str]) -> str:
    """去空白、转小写、去重并排序;None 与空字符串等价。"""
    if not langs:
        return ""
    parts = {p.strip().lower() for p in langs.split(",")}
    parts.discard("")
    return ",".join(sorted(parts))


def make_cache_key(
    content: bytes,
    max_pages: Optional[int],
    start_page: Optional[int],
    langs: Optional[str],
) -> str:
    content_hash = hashlib.sha256(content).hexdigest()
    # 用 JSON 编码各字段,避免不同字段拼接后产生歧义
    options = json.dumps(
        [max_pages, start_page, normalize_langs(langs)], separators=(",", ":")
    )
    options_hash = hashlib.sha256(options.encode("utf-8")).hexdigest()[:16]
    return f"{content_hash}-{options_hash}"


def _path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.json"


def load(key: str, cache_dir: Optional[Path] = None) -> Optional[dict]:
    """返回缓存的 Conversion Result;未命中或缓存文件损坏时返回 None。"""
    path = _path(cache_dir or get_cache_dir(), key)
    try:
        with open(path, "r", encoding="utf-8") as f:
            result = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        logger.warning(f"Ignoring unreadable cache file {path}: {e}")
        return None
    if not isinstance(result, dict):
        logger.warning(f"Ignoring malformed cache file {path}")
        return None
    return result


def save(key: str, result: dict, cache_dir: Optional[Path] = None) -> bool:
    """原子写入缓存。失败只记录日志并返回 False,不影响转换请求本身。"""
    cache_dir = cache_dir or get_cache_dir()
    path = _path(cache_dir, key)
    tmp_name = None
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        # 序列化放在创建临时文件之前,失败时不会留下垃圾文件
        data = json.dumps(result)
        fd, tmp_name = tempfile.mkstemp(dir=cache_dir, prefix=".tmp-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp_name, path)
        return True
    except (OSError, TypeError, ValueError) as e:
        logger.warning(f"Failed to save cache {path}: {e}")
        if tmp_name and os.path.exists(tmp_name):
            os.remove(tmp_name)
        return False
