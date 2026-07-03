#!/usr/bin/env python3
"""
AimiliVPN Prometheus Metrics Exporter

从 DATA_DIR 中的状态文件读取数据，以 Prometheus 文本格式暴露监控指标。
作为独立 sidecar 进程运行，不侵入主程序。

暴露端口: METRICS_PORT (默认 9798)
路径: /metrics
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("VPNGATE_DATA_DIR", "/opt/aimilivpn/vpngate_data"))
METRICS_PORT = int(os.environ.get("METRICS_PORT", "9798"))
METRICS_HOST = os.environ.get("METRICS_HOST", "0.0.0.0")
REFRESH_INTERVAL = int(os.environ.get("METRICS_REFRESH_INTERVAL", "15"))
_START_TIME = time.time()

_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()
_last_refresh = 0.0
_BUILD_INFO = {
    "version": os.environ.get("IMAGE_VERSION", "dev"),
    "build_date": os.environ.get("BUILD_DATE", "unknown"),
    "git_commit": os.environ.get("GIT_COMMIT", "unknown"),
}


def safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def escape_label(val: str) -> str:
    return val.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def tcp_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    af = socket.AF_INET6 if ":" in host else socket.AF_INET
    try:
        s = socket.socket(af, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def process_running(pattern: str) -> bool:
    try:
        res = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, timeout=2)
        return res.returncode == 0
    except Exception:
        return False


def read_proc_stat(pid: int) -> dict[str, int]:
    try:
        text = Path(f"/proc/{pid}/stat").read_text()
        # 进程名在括号中可能含空格，先提取括号后的内容再按空格分割
        m = re.match(r'^\d+ \((.*?)\) (.*)$', text)
        if m:
            parts = m.group(2).split()
        else:
            parts = text.split()
        return {
            "utime": int(parts[11]) if len(parts) > 11 else 0,
            "stime": int(parts[12]) if len(parts) > 12 else 0,
            "vsize": int(parts[20]) if len(parts) > 20 else 0,
            "rss": int(parts[21]) * 4096 if len(parts) > 21 else 0,
        }
    except Exception:
        return {"utime": 0, "stime": 0, "vsize": 0, "rss": 0}


def refresh_cache() -> None:
    global _last_refresh
    now = time.time()
    if now - _last_refresh < REFRESH_INTERVAL:
        return
    _last_refresh = now

    data: dict[str, Any] = {}

    # 状态文件
    state = read_json(DATA_DIR / "state.json", {})
    nodes = read_json(DATA_DIR / "nodes.json", [])

    # 进程存活
    data["manager_running"] = 1 if process_running("vpngate_manager.py") else 0
    data["openvpn_running"] = 1 if process_running("openvpn.*vpngate_data") else 0

    # 端口监听
    ui_port = safe_int(state.get("port") or os.environ.get("UI_PORT", "8787"))
    proxy_port = safe_int(state.get("proxy_port") or os.environ.get("LOCAL_PROXY_PORT", "7928"))
    proxy_host = os.environ.get("LOCAL_PROXY_HOST", "127.0.0.1")
    data["ui_port_open"] = 1 if tcp_port_open("127.0.0.1", ui_port) else 0
    data["proxy_port_open"] = 1 if tcp_port_open(proxy_host, proxy_port) else 0

    # TUN 设备
    data["tun0_exists"] = 1 if Path("/sys/class/net/tun0").exists() else 0

    # 连接状态
    is_connecting = state.get("is_connecting", False)
    active_id = state.get("active_openvpn_node_id", "")
    data["is_connecting"] = 1 if is_connecting else 0
    data["is_connected"] = 1 if active_id and not is_connecting else 0
    data["active_node_id"] = active_id

    # 代理健康
    data["proxy_ok"] = 1 if state.get("proxy_ok") else 0
    data["proxy_latency_ms"] = safe_float(state.get("proxy_latency_ms"))
    data["proxy_ip"] = state.get("proxy_ip", "")

    # 节点统计
    node_count_by_status: dict[str, int] = {}
    node_count_by_country: dict[str, int] = {}
    node_count_by_type: dict[str, int] = {}
    active_node_country = ""
    active_node_latency = 0.0
    active_node_score = 0

    if isinstance(nodes, list):
        for n in nodes:
            status = n.get("probe_status", "not_checked")
            node_count_by_status[status] = node_count_by_status.get(status, 0) + 1

            country = n.get("country", "未知")
            node_count_by_country[country] = node_count_by_country.get(country, 0) + 1

            ip_type = n.get("ip_type", "unknown")
            node_count_by_type[ip_type] = node_count_by_type.get(ip_type, 0) + 1

            if n.get("id") == active_id:
                active_node_country = country
                active_node_latency = safe_float(n.get("latency_ms"))
                active_node_score = safe_int(n.get("score"))

    data["node_count_total"] = len(nodes) if isinstance(nodes, list) else 0
    data["node_count_by_status"] = node_count_by_status
    data["node_count_by_country"] = node_count_by_country
    data["node_count_by_type"] = node_count_by_type
    data["active_node_country"] = active_node_country
    data["active_node_latency_ms"] = active_node_latency
    data["active_node_score"] = active_node_score
    data["blacklisted_nodes"] = safe_int(state.get("blacklisted_nodes"))

    # 获取主进程 PID 并读取资源使用
    try:
        res = subprocess.run(["pgrep", "-f", "vpngate_manager.py"], capture_output=True, text=True, timeout=2)
        if res.returncode == 0:
            pid = int(res.stdout.strip().splitlines()[0])
            proc_stat = read_proc_stat(pid)
            data["process_cpu_seconds"] = (proc_stat["utime"] + proc_stat["stime"]) / 100.0
            data["process_virtual_memory_bytes"] = proc_stat["vsize"]
            data["process_resident_memory_bytes"] = proc_stat["rss"]
    except Exception:
        pass

    # 系统信息
    data["uptime_seconds"] = time.time() - _START_TIME

    with _cache_lock:
        _cache.clear()
        _cache.update(data)


def generate_metrics() -> str:
    refresh_cache()
    with _cache_lock:
        d = dict(_cache)

    lines: list[str] = []

    # ── 构建信息 ──
    lines.append("# HELP aimilivpn_build_info Build information")
    lines.append("# TYPE aimilivpn_build_info gauge")
    labels = ",".join(f'{k}="{escape_label(v)}"' for k, v in _BUILD_INFO.items())
    lines.append(f"aimilivpn_build_info{{{labels}}} 1")
    lines.append("")

    # ── 进程存活 ──
    lines.append("# HELP aimilivpn_up Whether the service is running (1=yes)")
    lines.append("# TYPE aimilivpn_up gauge")
    lines.append(f"aimilivpn_up{{component=\"manager\"}} {d.get('manager_running', 0)}")
    lines.append(f"aimilivpn_up{{component=\"openvpn\"}} {d.get('openvpn_running', 0)}")
    lines.append(f"aimilivpn_up{{component=\"ui_port\"}} {d.get('ui_port_open', 0)}")
    lines.append(f"aimilivpn_up{{component=\"proxy_port\"}} {d.get('proxy_port_open', 0)}")
    lines.append(f"aimilivpn_up{{component=\"tun0\"}} {d.get('tun0_exists', 0)}")
    lines.append("")

    # ── 连接状态 ──
    lines.append("# HELP aimilivpn_connection_status Connection status (0=idle, 1=connecting, 2=connected)")
    lines.append("# TYPE aimilivpn_connection_status gauge")
    if d.get("is_connecting"):
        status = 1
    elif d.get("is_connected"):
        status = 2
    else:
        status = 0
    lines.append(f"aimilivpn_connection_status {status}")
    lines.append("")

    # ── 代理健康 ──
    lines.append("# HELP aimilivpn_proxy_healthy Whether the outbound proxy check passed (1=ok)")
    lines.append("# TYPE aimilivpn_proxy_healthy gauge")
    lines.append(f"aimilivpn_proxy_healthy {d.get('proxy_ok', 0)}")
    lines.append("")

    lines.append("# HELP aimilivpn_proxy_latency_ms Outbound proxy latency in milliseconds")
    lines.append("# TYPE aimilivpn_proxy_latency_ms gauge")
    lines.append(f"aimilivpn_proxy_latency_ms {d.get('proxy_latency_ms', 0)}")
    lines.append("")

    # ── 活动节点信息 ──
    active_id = d.get("active_node_id", "")
    if active_id:
        lines.append("# HELP aimilivpn_active_node_info Active node metadata")
        lines.append("# TYPE aimilivpn_active_node_info gauge")
        country = escape_label(d.get("active_node_country", ""))
        node_id = escape_label(active_id)
        lines.append(f'aimilivpn_active_node_info{{node_id="{node_id}",country="{country}"}} 1')
        lines.append("")

        lines.append("# HELP aimilivpn_active_node_latency_ms Active node latency in milliseconds")
        lines.append("# TYPE aimilivpn_active_node_latency_ms gauge")
        lines.append(f"aimilivpn_active_node_latency_ms {d.get('active_node_latency_ms', 0)}")
        lines.append("")

        lines.append("# HELP aimilivpn_active_node_score Active node score")
        lines.append("# TYPE aimilivpn_active_node_score gauge")
        lines.append(f"aimilivpn_active_node_score {d.get('active_node_score', 0)}")
        lines.append("")

    # ── 节点统计 ──
    lines.append("# HELP aimilivpn_nodes_total Total number of managed nodes")
    lines.append("# TYPE aimilivpn_nodes_total gauge")
    lines.append(f"aimilivpn_nodes_total {d.get('node_count_total', 0)}")
    lines.append("")

    lines.append("# HELP aimilivpn_nodes_by_status Number of nodes grouped by probe status")
    lines.append("# TYPE aimilivpn_nodes_by_status gauge")
    for status, count in d.get("node_count_by_status", {}).items():
        lines.append(f'aimilivpn_nodes_by_status{{status="{escape_label(status)}"}} {count}')
    lines.append("")

    lines.append("# HELP aimilivpn_nodes_by_type Number of nodes grouped by IP type")
    lines.append("# TYPE aimilivpn_nodes_by_type gauge")
    for ip_type, count in d.get("node_count_by_type", {}).items():
        lines.append(f'aimilivpn_nodes_by_type{{type="{escape_label(ip_type)}"}} {count}')
    lines.append("")

    lines.append("# HELP aimilivpn_blacklisted_nodes Number of blacklisted nodes")
    lines.append("# TYPE aimilivpn_blacklisted_nodes gauge")
    lines.append(f"aimilivpn_blacklisted_nodes {d.get('blacklisted_nodes', 0)}")
    lines.append("")

    # ── 进程资源 ──
    if "process_cpu_seconds" in d:
        lines.append("# HELP aimilivpn_process_cpu_seconds_total Total CPU seconds consumed")
        lines.append("# TYPE aimilivpn_process_cpu_seconds_total counter")
        lines.append(f"aimilivpn_process_cpu_seconds_total {d.get('process_cpu_seconds', 0)}")
        lines.append("")

        lines.append("# HELP aimilivpn_process_resident_memory_bytes Resident memory size in bytes")
        lines.append("# TYPE aimilivpn_process_resident_memory_bytes gauge")
        lines.append(f"aimilivpn_process_resident_memory_bytes {d.get('process_resident_memory_bytes', 0)}")
        lines.append("")

        lines.append("# HELP aimilivpn_process_virtual_memory_bytes Virtual memory size in bytes")
        lines.append("# TYPE aimilivpn_process_virtual_memory_bytes gauge")
        lines.append(f"aimilivpn_process_virtual_memory_bytes {d.get('process_virtual_memory_bytes', 0)}")
        lines.append("")

    # ── 运行时间 ──
    lines.append("# HELP aimilivpn_uptime_seconds Service uptime in seconds")
    lines.append("# TYPE aimilivpn_uptime_seconds gauge")
    lines.append(f"aimilivpn_uptime_seconds {d.get('uptime_seconds', 0)}")
    lines.append("")

    return "\n".join(lines) + "\n"


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/metrics":
            body = generate_metrics().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/health":
            refresh_cache()
            with _cache_lock:
                manager_ok = _cache.get("manager_running", 0)
            if manager_ok:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")
            else:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b"Manager process not running")
        elif self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"""<!DOCTYPE html>
<html><head><title>AimiliVPN Metrics</title></head><body>
<h1>AimiliVPN Prometheus Metrics Exporter</h1>
<p><a href="/metrics">/metrics</a> - Prometheus metrics endpoint</p>
<p><a href="/health">/health</a> - Health check endpoint</p>
</body></html>""")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass


class MetricsServer(ThreadingHTTPServer):
    """支持 IPv4/IPv6 双栈的 HTTP 服务器"""


def main() -> None:
    is_ipv6 = ":" in METRICS_HOST
    af = socket.AF_INET6 if is_ipv6 else socket.AF_INET
    MetricsServer.address_family = af
    server = MetricsServer((METRICS_HOST, METRICS_PORT), MetricsHandler)
    if is_ipv6:
        try:
            server.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except OSError:
            pass
    print(f"[metrics] AimiliVPN metrics exporter listening on {METRICS_HOST}:{METRICS_PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
