#!/usr/bin/env python3
"""离线 GeoIP 查询模块 — 本地 IP 范围数据库 + 内存二分查找。

支持 DB-IP Lite CSV 格式 (https://db-ip.com/db/lite.php):
  start_ip,end_ip,country_code,country_name

纯 Python 标准库实现，无需外部依赖。

Usage:
    import geoip
    geoip.load_database("/path/to/dbip-country-lite.csv")
    result = geoip.lookup("8.8.8.8")
    # {"country_code": "US", "country_name": "United States"}
"""
from __future__ import annotations

import bisect
import ipaddress
import os
import threading
from pathlib import Path
from typing import Any

_db: list[tuple[int, int, str, str]] = []
_db_loaded = False
_db_lock = threading.Lock()

# 配置
GEOIP_DB_PATH = os.environ.get("GEOIP_DB_PATH", "")


def _ip_to_int(ip: str) -> int:
    try:
        return int(ipaddress.IPv4Address(ip))
    except Exception:
        return 0


def load_database(filepath: str | Path) -> bool:
    """从 CSV 文件加载 IP 范围数据库。

    CSV 格式:
        start_ip,end_ip,country_code,country_name

    Args:
        filepath: CSV 文件路径

    Returns:
        True 如果加载成功，False 如果失败
    """
    global _db, _db_loaded
    filepath = Path(filepath)
    if not filepath.exists():
        return False

    new_db: list[tuple[int, int, str, str]] = []
    try:
        content = filepath.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",")
            if len(parts) < 4:
                continue
            try:
                start_int = _ip_to_int(parts[0])
                end_int = _ip_to_int(parts[1])
                country_code = parts[2].strip().upper()
                country_name = parts[3].strip()
                if start_int > 0 and end_int >= start_int and country_code:
                    new_db.append((start_int, end_int, country_code, country_name))
            except (ValueError, IndexError):
                continue
    except Exception:
        return False

    if not new_db:
        return False

    new_db.sort(key=lambda x: x[0])

    merged: list[tuple[int, int, str, str]] = []
    if new_db:
        cur = list(new_db[0])
        for start_int, end_int, cc, cn in new_db[1:]:
            if cc == cur[2] and cn == cur[3] and start_int <= cur[1] + 1:
                cur[1] = max(cur[1], end_int)
            else:
                merged.append((cur[0], cur[1], cur[2], cur[3]))
                cur = [start_int, end_int, cc, cn]
        merged.append((cur[0], cur[1], cur[2], cur[3]))

    with _db_lock:
        _db = merged
        _db_loaded = True

    print(f"[GeoIP] 已加载 {len(merged)} 条 IP 范围记录 (来自 {filepath.name})", flush=True)
    return True


def lookup(ip: str) -> dict[str, str] | None:
    """查找 IP 地址所属国家。

    Args:
        ip: IPv4 地址字符串

    Returns:
        包含 country_code 和 country_name 的字典，未找到返回 None
    """
    if not _db_loaded:
        return None

    try:
        ip_int = int(ipaddress.IPv4Address(ip.strip()))
    except Exception:
        return None

    with _db_lock:
        if not _db:
            return None

        starts = [r[0] for r in _db]
        idx = bisect.bisect_right(starts, ip_int) - 1
        if idx < 0 or idx >= len(_db):
            return None

        start_int, end_int, country_code, country_name = _db[idx]
        if start_int <= ip_int <= end_int:
            return {"country_code": country_code, "country_name": country_name}

    return None


def is_loaded() -> bool:
    return _db_loaded


def get_stats() -> dict[str, Any]:
    return {
        "loaded": _db_loaded,
        "records": len(_db),
        "db_path": GEOIP_DB_PATH or "not configured",
    }


def auto_init(data_dir: Path | None = None) -> bool:
    """自动初始化 GeoIP 数据库。

    查找顺序:
    1. GEOIP_DB_PATH 环境变量
    2. <data_dir>/geoip.csv
    """
    if _db_loaded:
        return True

    paths = []
    if GEOIP_DB_PATH:
        paths.append(GEOIP_DB_PATH)
    if data_dir:
        paths.append(str(Path(data_dir) / "geoip.csv"))

    for p in paths:
        if load_database(p):
            return True

    return False
