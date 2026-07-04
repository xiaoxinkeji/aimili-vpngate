#!/usr/bin/env python3
"""AimiliVPN 自更新模块 — 仅用 Python 标准库"""

import json
import os
import platform
import re
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

GITHUB_REPO = "xiaoxinkeji/aimili-vpngate"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CHECK_INTERVAL = 3600 * 6  # 每 6 小时检查一次

_latest_version: str | None = None
_latest_url: str | None = None
_last_check: float = 0.0
_check_lock = threading.Lock()

try:
    from _version import VERSION, GIT_COMMIT, BUILD_DATE
except ImportError:
    VERSION = os.environ.get("IMAGE_VERSION", "dev")
    GIT_COMMIT = os.environ.get("GIT_COMMIT", "unknown")
    BUILD_DATE = os.environ.get("BUILD_DATE", "unknown")


def _parse_version(tag: str) -> tuple[int, ...]:
    """从 v1.2.3 格式的 tag 中提取版本号元组"""
    m = re.search(r"(\d+(?:\.\d+)*)", tag)
    if not m:
        return (0,)
    return tuple(int(x) for x in m.group(1).split("."))


def _is_newer(latest_tag: str, current_tag: str) -> bool:
    """比较版本号，latest > current 返回 True"""
    try:
        return _parse_version(latest_tag) > _parse_version(current_tag)
    except Exception:
        return False


def check_update() -> dict[str, str | None]:
    """检查 GitHub 是否有新版本。返回 {"latest": tag, "url": download_url} 或空。"""
    global _latest_version, _latest_url, _last_check

    now = time.time()
    with _check_lock:
        if now - _last_check < CHECK_INTERVAL and _latest_version:
            return {"latest": _latest_version, "url": _latest_url}
        _last_check = now

    try:
        req = urllib.request.Request(GITHUB_API, headers={"User-Agent": "aimilivpn-updater"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {"latest": None, "url": None}

    latest_tag = data.get("tag_name", "")
    if not latest_tag or not _is_newer(latest_tag, VERSION):
        return {"latest": None, "url": None}

    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch = "amd64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    else:
        return {"latest": latest_tag, "url": None}

    pattern = f"aimilivpn-linux-{arch}.tar.gz"
    download_url = None
    for asset in data.get("assets", []):
        if asset.get("name") == pattern:
            download_url = asset.get("browser_download_url")
            break

    with _check_lock:
        _latest_version = latest_tag
        _latest_url = download_url

    return {"latest": latest_tag, "url": download_url}


def do_update() -> bool:
    """下载新版本并替换当前二进制文件。返回是否成功。"""
    info = check_update()
    if not info["url"]:
        print(f"[更新] 当前已是最新版本 ({VERSION})", flush=True)
        return False

    current_bin = Path(sys.executable).resolve()
    print(f"[更新] 发现新版本 {info['latest']}，正在下载...", flush=True)

    try:
        req = urllib.request.Request(info["url"], headers={"User-Agent": "aimilivpn-updater"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            tarball = resp.read()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tar_path = tmp_path / "update.tar.gz"
            tar_path.write_bytes(tarball)

            import tarfile
            with tarfile.open(tar_path, "r:gz") as tar:
                tar.extractall(tmp_path)

            new_bin = tmp_path / "aimilivpn"
            if not new_bin.exists():
                print("[更新] 下载的压缩包中未找到 aimilivpn 二进制", flush=True)
                return False

            # 备份当前二进制
            backup = current_bin.with_suffix(current_bin.suffix + ".bak")
            current_bin.rename(backup)

            # 替换
            new_bin.rename(current_bin)
            current_bin.chmod(0o755)

            print(f"[更新] 已更新到 {info['latest']}，备份保留在 {backup}", flush=True)
            print("[更新] 请手动重启服务以生效", flush=True)
            return True

    except Exception as e:
        print(f"[更新] 下载失败: {e}", flush=True)
        return False


def start_update_checker() -> None:
    """在后台线程中定期检查更新，有新版本时打印提示"""

    def _checker() -> None:
        time.sleep(30)  # 启动后 30 秒再检查
        while True:
            try:
                info = check_update()
                if info["latest"]:
                    print(f"[更新] 发现新版本 {info['latest']}，运行 aimilivpn --update 更新", flush=True)
            except Exception:
                pass
            time.sleep(CHECK_INTERVAL)

    t = threading.Thread(target=_checker, daemon=True)
    t.start()
