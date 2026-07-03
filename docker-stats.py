#!/usr/bin/env python3
"""AimiliVPN 容器内快速状态查看工具"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

DATA_DIR = Path(os.environ.get("VPNGATE_DATA_DIR", "/opt/aimilivpn/vpngate_data"))
UI_PORT = int(os.environ.get("UI_PORT", "8787"))
PROXY_PORT = int(os.environ.get("LOCAL_PROXY_PORT", "7928"))
PROXY_HOST = os.environ.get("LOCAL_PROXY_HOST", "127.0.0.1")

GREEN = "\033[1;32m"
RED = "\033[1;31m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
RESET = "\033[0m"


def check_port(host, port, timeout=1.0):
    af = socket.AF_INET6 if ":" in host else socket.AF_INET
    try:
        s = socket.socket(af, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def main():
    print(f"{CYAN}╔══════════════════════════════════════════════════╗{RESET}")
    print(f"{CYAN}║{BOLD}         AimiliVPN Container Status                {CYAN}║{RESET}")
    print(f"{CYAN}╚══════════════════════════════════════════════════╝{RESET}")
    print()

    # 进程状态
    mgr_ok = False
    try:
        res = subprocess.run(["pgrep", "-f", "vpngate_manager.py"], capture_output=True, text=True)
        mgr_ok = res.returncode == 0
    except Exception:
        pass
    print(f"  Manager 进程:  {GREEN}运行中{RESET}" if mgr_ok else f"  Manager 进程:  {RED}未运行{RESET}")

    # 端口监听
    web_ok = check_port("127.0.0.1", UI_PORT)
    print(f"  Web UI ({UI_PORT}): {GREEN}监听中{RESET}" if web_ok else f"  Web UI ({UI_PORT}): {RED}未监听{RESET}")

    proxy_ok = check_port(PROXY_HOST, PROXY_PORT)
    print(f"  代理 ({PROXY_HOST}:{PROXY_PORT}): {GREEN}监听中{RESET}" if proxy_ok else f"  代理: {RED}未监听{RESET}")

    # OpenVPN 状态
    openvpn_ok = False
    try:
        res = subprocess.run(["pgrep", "-f", "openvpn.*vpngate_data"], capture_output=True, text=True)
        openvpn_ok = res.returncode == 0
    except Exception:
        pass

    tun_exists = Path("/sys/class/net/tun0").exists()
    print(f"  OpenVPN 进程: {GREEN}运行中{RESET}" if openvpn_ok else f"  OpenVPN 进程: {YELLOW}未运行{RESET}")
    print(f"  虚拟网卡 tun0: {GREEN}存在{RESET}" if tun_exists else f"  虚拟网卡 tun0: {YELLOW}不存在{RESET}")

    print()

    # 读取状态文件
    state = read_json(DATA_DIR / "state.json", {})
    if not state:
        print(f"  {BOLD}连接状态:{RESET} {YELLOW}状态文件为空或不存在{RESET}")
    else:
        active_id = state.get("active_openvpn_node_id", "")
        is_connecting = state.get("is_connecting", False)
        latency = state.get("active_node_latency", "-")
        proxy_ip = state.get("proxy_ip", "-")
        proxy_latency = state.get("proxy_latency_ms", 0)

        if is_connecting:
            print(f"  {BOLD}连接状态:{RESET} {YELLOW}切换中...{RESET}")
        elif active_id:
            print(f"  {BOLD}活动节点:{RESET} {GREEN}{active_id}{RESET}")
            print(f"  {BOLD}节点延迟:{RESET} {latency}")
            print(f"  {BOLD}出口 IP:{RESET} {proxy_ip}")
            if proxy_latency:
                print(f"  {BOLD}代理延迟:{RESET} {proxy_latency} ms")
        else:
            print(f"  {BOLD}连接状态:{RESET} {YELLOW}无活动连接{RESET}")

    # 路由表
    try:
        res = subprocess.run(["ip", "rule", "show", "table", "100"], capture_output=True, text=True, timeout=2)
        if res.stdout.strip():
            print(f"\n  {BOLD}策略路由 (table 100):{RESET}")
            for line in res.stdout.strip().splitlines():
                print(f"    {line}")
    except Exception:
        pass

    print()

    # 最近日志
    log_dir = DATA_DIR / "logs"
    if log_dir.exists():
        today = time.strftime("%Y-%m-%d")
        today_log = log_dir / f"{today}.json"
        if today_log.exists():
            entries = []
            total_count = 0
            try:
                lines_data = today_log.read_text(encoding="utf-8").strip().splitlines()
                total_count = len(lines_data)
                entries = [json.loads(l) for l in lines_data[-5:] if l.strip()]
            except Exception:
                entries = []
                total_count = 0
        else:
            entries = []
    else:
        entries = []

    if entries:
        count_info = f"共 {total_count} 条" if total_count else f"{len(entries)} 条"
        print(f"  {BOLD}最近日志 ({count_info}, 显示最近 {len(entries)} 条):{RESET}")
        for entry in entries[-5:]:
            ts = entry.get("timestamp", "")
            level = entry.get("level", "INFO")
            module = entry.get("module", "")
            msg = entry.get("message", "")
            color = RED if level == "ERROR" else (YELLOW if level == "WARNING" else RESET)
            print(f"    {color}[{ts}] [{level}] [{module}] {msg}{RESET}")

    print(f"\n{CYAN}══════════════════════════════════════════════════{RESET}")
    web_url = f"http://localhost:{UI_PORT}/"
    print(f"  Web 管理后台: {web_url}")
    print(f"  代理地址:     http://{PROXY_HOST}:{PROXY_PORT}")
    print(f"  容器日志:     docker logs -f aimilivpn")
    print(f"{CYAN}══════════════════════════════════════════════════{RESET}")


if __name__ == "__main__":
    main()
