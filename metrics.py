#!/usr/bin/env python3
"""Prometheus 指标导出 — 将内部状态转换为 Prometheus text 格式。"""

from __future__ import annotations
import time
from typing import Any


STARTUP_TS = time.time()

_HELP = {
    "aimili_uptime_seconds": "代理服务运行时长",
    "aimili_proxy_healthy": "代理健康状态 (1=ok, 0=error)",
    "aimili_traffic_bytes_total": "累计流量字节 (direction=in|out)",
    "aimili_traffic_throughput_mbps": "当前吞吐量 Mbps (direction=in|out)",
    "aimili_connections_total": "累计连接数",
    "aimili_connections_active": "当前活跃连接数",
    "aimili_sessions_active": "当前活跃会话数",
    "aimili_sessions_total": "累计会话数 (含已关闭)",
    "aimili_nodes_total": "节点总数",
    "aimili_nodes_available": "可用节点数",
    "aimili_node_latency_ms": "节点延迟毫秒",
    "aimili_dns_cache_size": "DNS 缓存条目数",
    "aimili_dns_blocked_total": "累计 DNS 阻断数",
    "aimili_rate_limit_tokens": "当前限流 token 数",
    "aimili_geoip_cache_size": "GeoIP 缓存条目数",
}


def _escape_label_value(v: str) -> str:
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _G(v: Any) -> str:
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        if v != v:
            return "NaN"
        return f"{v:.6g}"
    return str(v)


class _MetricFamily:
    """收集同一指标名下的所有样本，确保 HELP/TYPE 只输出一次。"""

    def __init__(self) -> None:
        self._families: dict[str, list[tuple[dict[str, str] | None, float]]] = {}
        self._order: list[str] = []

    def add(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        if name not in self._families:
            self._families[name] = []
            self._order.append(name)
        self._families[name].append((labels, value))

    def blank(self) -> None:
        self._order.append("")

    def render(self) -> str:
        lines: list[str] = []
        for name in self._order:
            if name == "":
                lines.append("")
                continue
            samples = self._families.get(name)
            if not samples:
                continue
            if name in _HELP:
                lines.append(f"# HELP {name} {_HELP[name]}")
            lines.append(f"# TYPE {name} gauge")
            for labels, value in samples:
                if labels:
                    label_str = ",".join(f'{k}="{_escape_label_value(v)}"' for k, v in labels.items())
                    lines.append(f"{name}{{{label_str}}} {_G(value)}")
                else:
                    lines.append(f"{name} {_G(value)}")
        return "\n".join(lines)


def generate_metrics(
    proxy_ok: bool,
    traffic: dict[str, Any],
    sessions: dict[str, Any],
    nodes: list[dict[str, Any]],
    rate_limits: dict[str, Any] | None = None,
    dns_stats: dict[str, Any] | None = None,
    geoip_stats: dict[str, Any] | None = None,
) -> str:
    now = time.time()
    mf = _MetricFamily()

    mf.add("aimili_uptime_seconds", now - STARTUP_TS)
    mf.add("aimili_proxy_healthy", 1 if proxy_ok else 0)
    mf.blank()

    mf.add("aimili_traffic_bytes_total", traffic.get("bytes_in", 0), {"direction": "in"})
    mf.add("aimili_traffic_bytes_total", traffic.get("bytes_out", 0), {"direction": "out"})
    mf.add("aimili_traffic_throughput_mbps", traffic.get("throughput_in_mbps", 0), {"direction": "in"})
    mf.add("aimili_traffic_throughput_mbps", traffic.get("throughput_out_mbps", 0), {"direction": "out"})
    mf.add("aimili_connections_total", traffic.get("total_connections", 0))
    mf.add("aimili_connections_active", traffic.get("active_connections", 0))
    mf.blank()

    mf.add("aimili_sessions_active", sessions.get("active", 0))
    mf.add("aimili_sessions_total", sessions.get("total", 0))
    mf.blank()

    mf.add("aimili_nodes_total", len(nodes))
    mf.add("aimili_nodes_available", sum(1 for n in nodes if n.get("probe_status") == "available"))

    for n in nodes:
        if n.get("probe_status") == "available" and n.get("latency_ms", 0) > 0:
            nid = str(n.get("id") or "")[:32]
            mf.add("aimili_node_latency_ms", n["latency_ms"], {"node_id": nid})

    if dns_stats:
        mf.blank()
        mf.add("aimili_dns_cache_size", dns_stats.get("cache_size", 0))
        mf.add("aimili_dns_blocked_total", dns_stats.get("blocked_count", 0))

    if rate_limits:
        mf.blank()
        for path, info in rate_limits.get("paths", {}).items():
            safe_path = path.replace("/", "_").lstrip("_") or "root"
            mf.add("aimili_rate_limit_tokens", info.get("tokens", 0), {"path": safe_path})

    if geoip_stats:
        mf.blank()
        mf.add("aimili_geoip_cache_size", geoip_stats.get("cache_size", 0))

    content = mf.render()
    content += f"\n# EOF {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}"
    return content
