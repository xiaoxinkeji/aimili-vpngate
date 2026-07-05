#!/usr/bin/env python3
"""publicvpnlist.com 节点抓取器 — 仅用 Python 标准库"""

import html.parser
import json
import re
import sys
import time
import urllib.request
from typing import Any

BASE_URL = "https://publicvpnlist.com"
COUNTRY_SLUGS = [
    "japan", "south-korea", "russia", "usa", "thailand", "vietnam",
    "canada", "australia", "lao-people-s-democratic-republic", "uk",
    "belarus", "emirates", "france", "hungary", "india", "indonesia",
    "mexico", "myanmar", "philippines", "romania", "saudi-arabia",
    "south-africa", "ukraine", "venezuela",
]


class PVLRowParser(html.parser.HTMLParser):
    """从 <tr data-ssr-row=...> 中提取 data-* 属性"""

    def __init__(self):
        super().__init__()
        self.rows: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "tr":
            return
        attr_dict = dict(attrs)
        if attr_dict.get("data-ssr-row") != "1":
            return
        row: dict[str, str] = {}
        for k in ("data-id", "data-country", "data-country-name",
                   "data-host", "data-ip", "data-speed", "data-latency",
                   "data-port", "data-proto", "data-checked-at"):
            val = attr_dict.get(k)
            if val:
                row[k.replace("data-", "")] = val
        if row.get("id"):
            self.rows.append(row)


def _fetch(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "aimilivpn-scraper/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_pvl_nodes() -> list[dict[str, Any]]:
    """从 publicvpnlist.com 获取所有节点"""
    seen: set[str] = set()
    nodes: list[dict[str, Any]] = []

    urls = [BASE_URL + "/"] + [f"{BASE_URL}/country/{s}/" for s in COUNTRY_SLUGS]

    for i, url in enumerate(urls):
        try:
            html_text = _fetch(url)
            parser = PVLRowParser()
            parser.feed(html_text)
            for row in parser.rows:
                sid = row["id"]
                if sid in seen:
                    continue
                seen.add(sid)

                speed_raw = float(row.get("speed", "0") or "0")
                latency_raw = float(row.get("latency", "0") or "0")
                port_raw = int(row.get("port", "0") or "0")

                country_name = row.get("country-name", "")
                country_short = (row.get("country", "") or "").upper()

                nodes.append({
                    "id": f"pvl_{sid}",
                    "country": _map_country_name(country_name),
                    "country_short": country_short,
                    "host_name": row.get("host", ""),
                    "ip": row.get("ip", ""),
                    "score": round(speed_raw * 100),
                    "ping": latency_raw,
                    "speed": int(speed_raw * 1_000_000),
                    "sessions": 0,
                    "owner": "",
                    "asn": "",
                    "as_name": "",
                    "location": "",
                    "ip_type": "",
                    "quality": "",
                    "latency_ms": 0,
                    "config_file": "",
                    "config_url": f"{BASE_URL}/download/{sid}/",
                    "config_text": "",
                    "proto": row.get("proto", "tcp").lower(),
                    "remote_host": row.get("host", ""),
                    "remote_port": port_raw,
                    "fetched_at": time.time(),
                    "probe_status": "not_checked",
                    "probe_message": "",
                    "probed_at": 0,
                    "source": "publicvpnlist",
                })
            print(f"[PVL] {url} -> {len(parser.rows)} 条 (累计 {len(nodes)})", flush=True)
        except Exception as e:
            print(f"[PVL] {url} 抓取失败: {e}", flush=True)
        time.sleep(0.5)

    return nodes


_CN_MAP: dict[str, str] = {
    "japan": "日本", "south korea": "韩国", "russia": "俄罗斯",
    "usa": "美国", "thailand": "泰国", "vietnam": "越南",
    "canada": "加拿大", "australia": "澳大利亚",
    "lao people's democratic republic": "老挝", "uk": "英国",
    "belarus": "白俄罗斯", "emirates": "阿联酋", "france": "法国",
    "hungary": "匈牙利", "india": "印度", "indonesia": "印度尼西亚",
    "mexico": "墨西哥", "myanmar": "缅甸", "philippines": "菲律宾",
    "romania": "罗马尼亚", "saudi arabia": "沙特阿拉伯",
    "south africa": "南非", "ukraine": "乌克兰", "venezuela": "委内瑞拉",
}


def _map_country_name(name: str) -> str:
    return _CN_MAP.get(name.lower().strip(), name)


if __name__ == "__main__":
    result = fetch_pvl_nodes()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n总计: {len(result)} 个节点", file=sys.stderr)
