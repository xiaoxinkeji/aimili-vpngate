#!/usr/bin/env python3
"""DNS Forwarder - 内置 DNS 转发器，通过 VPN 隧道转发 DNS 查询。

监听本地 UDP 端口，接收客户端 DNS 请求，通过 tun0 转发到上游 DNS 服务器，
返回响应给客户端。消除 SOCKS5/HTTP 代理客户端的 DNS 泄漏风险。

参考 RFC 1035 (DNS) 和 dnslib (https://github.com/paulc/dnslib) 的设计理念，
完全用 Python 标准库实现。
"""
from __future__ import annotations

import os
import random
import select
import socket
import struct
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any


def _check_tun() -> bool:
    try:
        fd = os.open("/dev/net/tun", os.O_RDWR)
        os.close(fd)
        return True
    except OSError:
        return False


TUN_AVAILABLE = _check_tun()


def _env_int(name: str, default: int, min_v: int | None = None, max_v: int | None = None) -> int:
    try:
        v = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default
    if min_v is not None and v < min_v:
        return default
    if max_v is not None and v > max_v:
        return default
    return v


# 配置
DNS_FORWARDER_HOST = os.environ.get("DNS_FORWARDER_HOST", "127.0.0.1")
DNS_FORWARDER_PORT = _env_int("DNS_FORWARDER_PORT", 5353, 1, 65535)
DNS_UPSTREAM_SERVERS = os.environ.get(
    "DNS_UPSTREAM_SERVERS", "8.8.8.8,1.1.1.1,8.8.4.4"
).split(",")
DNS_FORWARDER_TIMEOUT = _env_int("DNS_FORWARDER_TIMEOUT", 5, 1, 60)
DNS_FORWARDER_CACHE_SIZE = _env_int("DNS_FORWARDER_CACHE_SIZE", 512, 1, 8192)
DNS_FORWARDER_CACHE_TTL = _env_int("DNS_FORWARDER_CACHE_TTL", 300, 1, 86400)
DNS_BLOCKLIST_PATH = os.environ.get("DNS_BLOCKLIST_PATH", "")
DNS_BLOCKLIST_ENABLED = os.environ.get("DNS_BLOCKLIST_ENABLED", "true").lower() != "false"

# 内置广告/追踪域名黑名单 (常用广告平台)
_BUILTIN_BLOCKLIST: set[str] = set()

def _load_builtin_blocklist() -> set[str]:
    domains = {
        # Google Ads / Analytics
        "doubleclick.net", "googlesyndication.com", "googleadservices.com",
        "google-analytics.com", "googletagmanager.com", "googletagservices.com",
        "adservice.google.com", "pagead2.googlesyndication.com",
        # Facebook
        "facebook.com/tr", "connect.facebook.net",
        # 国内广告
        "pos.baidu.com", "cpro.baidu.com", "hm.baidu.com",
        "eiv.baidu.com", "sohu.com/ppp", "tanx.com",
        "allyes.com", "mmstat.com", "cnzz.com",
        # 通用追踪
        "adsrvr.org", "adnxs.com", "criteo.com", "criteo.net",
        "outbrain.com", "taboola.com", "scorecardresearch.com",
        "quantserve.com", "addthis.com", "sharethis.com",
        # 恶意/钓鱼
        "click.hugedomains.com",
    }
    return domains


def _load_blocklist_file(filepath: str) -> set[str]:
    domains: set[str] = set()
    try:
        content = Path(filepath).read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("0.0.0.0 ") or line.startswith("127.0.0.1 "):
                line = line.split(maxsplit=1)[1]
            domain = line.strip().lower().rstrip(".")
            if domain and not domain.startswith("#"):
                domains.add(domain)
    except Exception:
        pass
    return domains


_blocklist: set[str] = set()
_blocklist_lock = threading.Lock()
_blocked_count: int = 0
_blocklist_loaded = False


def _init_blocklist() -> None:
    global _blocklist, _blocklist_loaded
    if not DNS_BLOCKLIST_ENABLED:
        _blocklist_loaded = True
        return

    domains = _load_builtin_blocklist()

    if DNS_BLOCKLIST_PATH:
        file_domains = _load_blocklist_file(DNS_BLOCKLIST_PATH)
        domains.update(file_domains)

    with _blocklist_lock:
        _blocklist = domains
        _blocklist_loaded = True

    loaded = "内置规则" if not DNS_BLOCKLIST_PATH else f"内置规则 + {DNS_BLOCKLIST_PATH}"
    print(f"[DNS 过滤] 黑名单已加载: {len(domains)} 条规则 ({loaded})", flush=True)


def _is_blocked(hostname: str) -> bool:
    if not DNS_BLOCKLIST_ENABLED or not _blocklist_loaded:
        return False
    hostname_lower = hostname.lower().rstrip(".")
    with _blocklist_lock:
        if hostname_lower in _blocklist:
            return True
    parts = hostname_lower.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[i:])
        with _blocklist_lock:
            if parent in _blocklist:
                return True
    return False


def _build_blocked_response(query_data: bytes) -> bytes:
    """返回 NXDOMAIN 或 127.0.0.1 阻断响应。"""
    if len(query_data) < 12:
        return b""
    tx_id = query_data[:2]
    flags = struct.unpack_from("!H", query_data, 2)[0]
    flags = (flags & 0xFFF0) | 3  # NXDOMAIN
    flags |= 0x8000
    header = tx_id + struct.pack("!H", flags) + query_data[4:12]
    return header

# DNS 记录类型
TYPE_A = 1
TYPE_AAAA = 28
TYPE_CNAME = 5
TYPE_NS = 2
TYPE_SOA = 6
TYPE_PTR = 12
TYPE_MX = 15
TYPE_TXT = 16

# DNS 类别
CLASS_IN = 1

# RFC 1035 DNS 头部结构
DNS_HEADER_FMT = "!HHHHHH"

# 压缩指针标志
COMPRESSION_MASK = 0xC0

# 最大 DNS 消息大小
MAX_DNS_SIZE = 4096


class DNSCache:
    def __init__(self, max_size: int = 512, default_ttl: int = 300):
        self._cache: OrderedDict[str, tuple[bytes, float]] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = threading.Lock()

    def _make_key(self, qname: str, qtype: int) -> str:
        return f"{qname}:{qtype}"

    def get(self, qname: str, qtype: int) -> bytes | None:
        key = self._make_key(qname, qtype)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            data, expires = entry
            if time.time() > expires:
                self._cache.pop(key, None)
                return None
            self._cache.move_to_end(key)
            return data

    def set(self, qname: str, qtype: int, data: bytes, ttl: int | None = None) -> None:
        key = self._make_key(qname, qtype)
        ttl_val = ttl if ttl is not None and ttl > 0 else self._default_ttl
        expires = time.time() + ttl_val
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (data, expires)
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)


_dns_cache = DNSCache(DNS_FORWARDER_CACHE_SIZE, DNS_FORWARDER_CACHE_TTL)


def _parse_qname(data: bytes, offset: int) -> tuple[str, int]:
    parts: list[str] = []
    jumped = False
    original_offset = offset
    max_hops = 20

    for _ in range(max_hops):
        if offset >= len(data):
            break
        length = data[offset]
        if length == 0:
            offset += 1
            break
        if (length & COMPRESSION_MASK) == COMPRESSION_MASK:
            if offset + 2 > len(data):
                break
            pointer = struct.unpack_from("!H", data, offset)[0] & 0x3FFF
            offset += 2
            if not jumped:
                original_offset = offset
                jumped = True
            offset = pointer
            continue
        offset += 1
        if offset + length > len(data):
            break
        try:
            parts.append(data[offset : offset + length].decode("ascii"))
        except UnicodeDecodeError as e:
            print(f"[DNS 转发器] 解析域名标签失败: {e}", flush=True)
            break
        offset += length

    qname = ".".join(parts)
    final_offset = original_offset if jumped else offset
    return qname, final_offset


def _parse_dns_header(data: bytes) -> dict[str, int]:
    if len(data) < 12:
        return {"error": 1}
    tx_id, flags, qdcount, ancount, nscount, arcount = struct.unpack_from(
        DNS_HEADER_FMT, data, 0
    )
    return {
        "tx_id": tx_id,
        "flags": flags,
        "qr": (flags >> 15) & 1,
        "opcode": (flags >> 11) & 0xF,
        "rcode": flags & 0xF,
        "qdcount": qdcount,
        "ancount": ancount,
        "nscount": nscount,
        "arcount": arcount,
    }


def _parse_dns_question(data: bytes, offset: int) -> tuple[str, int, int, int] | None:
    qname, offset = _parse_qname(data, offset)
    if offset + 4 > len(data):
        return None
    qtype, qclass = struct.unpack_from("!HH", data, offset)
    return qname, qtype, qclass, offset + 4


def _extract_ttl_from_response(data: bytes) -> int:
    header = _parse_dns_header(data)
    if header.get("error"):
        return DNS_FORWARDER_CACHE_TTL
    offset = 12
    for _ in range(header.get("qdcount", 0)):
        result = _parse_dns_question(data, offset)
        if result is None:
            return DNS_FORWARDER_CACHE_TTL
        offset = result[3]
    min_ttl = 86400
    ancount = header.get("ancount", 0)
    for _ in range(ancount):
        if offset + 10 > len(data):
            break
        _, offset = _parse_qname(data, offset)
        if offset + 10 > len(data):
            break
        atype, aclass, ttl, rdlength = struct.unpack_from("!HHIH", data, offset)
        offset += 10
        if offset + rdlength > len(data):
            break
        offset += rdlength
        if ttl > 0 and ttl < min_ttl:
            min_ttl = ttl
    if min_ttl == 86400:
        return DNS_FORWARDER_CACHE_TTL
    return min(min_ttl, DNS_FORWARDER_CACHE_TTL)


def _build_dns_error_response(query_data: bytes, rcode: int = 2) -> bytes:
    if len(query_data) < 12:
        return b""
    tx_id = query_data[:2]
    flags = struct.unpack_from("!H", query_data, 2)[0]
    flags = (flags & 0xFFF0) | rcode
    flags |= 0x8000  # QR = 1 (response)
    return tx_id + struct.pack("!H", flags) + query_data[4:12]


def _forward_dns_query(query_data: bytes) -> bytes | None:
    upstreams = [s.strip() for s in DNS_UPSTREAM_SERVERS if s.strip()]
    if not upstreams:
        upstreams = ["8.8.8.8"]

    random.shuffle(upstreams)

    for server in upstreams:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(DNS_FORWARDER_TIMEOUT)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b"tun0")
            except OSError:
                pass
            sock.sendto(query_data, (server, 53))
            resp, _ = sock.recvfrom(MAX_DNS_SIZE)
            if len(resp) >= 12:
                return resp
        except Exception:
            continue
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
    return None


def handle_dns_query(data: bytes, client_addr: tuple[str, int]) -> bytes | None:
    if len(data) < 12:
        return None

    header = _parse_dns_header(data)
    if header.get("error") or header.get("qr") == 1:
        return None

    if header.get("opcode") != 0:
        return _build_dns_error_response(data, 4)

    offset = 12
    queries: list[tuple[str, int, int]] = []
    for _ in range(header.get("qdcount", 0)):
        result = _parse_dns_question(data, offset)
        if result is None:
            break
        qname, qtype, qclass, offset = result
        queries.append((qname, qtype, qclass))

    if not queries:
        return _build_dns_error_response(data, 1)

    # 域名黑名单检查
    if _is_blocked(queries[0][0]):
        global _blocked_count
        _blocked_count += 1
        return _build_blocked_response(data)

    cached = _dns_cache.get(queries[0][0], queries[0][1])
    if cached is not None:
        tx_id = data[:2]
        resp = tx_id + cached[2:]
        return resp

    response = _forward_dns_query(data)
    if response is None:
        return _build_dns_error_response(data, 2)

    ttl = _extract_ttl_from_response(response)
    for qname, qtype, _ in queries:
        _dns_cache.set(qname, qtype, response, ttl)

    return response


def start_dns_forwarder(host: str = DNS_FORWARDER_HOST, port: int = DNS_FORWARDER_PORT) -> None:
    _init_blocklist()

    is_ipv6 = ":" in host or host == ""
    af = socket.AF_INET6 if is_ipv6 else socket.AF_INET
    sock = None

    try:
        sock = socket.socket(af, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if is_ipv6:
            try:
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            except OSError as e:
                print(f"[DNS 转发器] 设置 IPV6_V6ONLY 失败: {e}", flush=True)
        sock.bind((host, port))
        print(f"[DNS 转发器] 监听 {host}:{port}，上游服务器: {', '.join(DNS_UPSTREAM_SERVERS)}", flush=True)
        print(f"[DNS 转发器] 缓存大小: {DNS_FORWARDER_CACHE_SIZE} 条，默认 TTL: {DNS_FORWARDER_CACHE_TTL}s", flush=True)
    except OSError as e:
        if is_ipv6 and host in ("::", ""):
            print(f"[DNS 转发器] IPv6 绑定失败 ({e})，尝试 IPv4 回退...", flush=True)
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("0.0.0.0", port))
                print(f"[DNS 转发器] 监听 0.0.0.0:{port} (IPv4 回退)", flush=True)
            except OSError as e2:
                print(f"[DNS 转发器] 启动失败: {e2}", flush=True)
                return
        else:
            print(f"[DNS 转发器] 启动失败: {e}", flush=True)
            return

    if not TUN_AVAILABLE:
        print("[DNS 转发器] 警告: /dev/net/tun 不可用，DNS 转发可能使用默认路由", flush=True)

    try:
        while True:
            readable, _, _ = select.select([sock], [], [], 1.0)
            if sock in readable:
                try:
                    data, client_addr = sock.recvfrom(MAX_DNS_SIZE)
                    if len(data) < 12:
                        continue

                    def _handle(data: bytes = data, client_addr: tuple[str, int] = client_addr) -> None:
                        try:
                            resp = handle_dns_query(data, client_addr)
                            if resp is not None:
                                sock.sendto(resp, client_addr)
                        except Exception as ex:
                            print(f"[DNS 转发器] 处理查询异常: {ex}", flush=True)

                    threading.Thread(target=_handle, daemon=True).start()
                except Exception as ex:
                    print(f"[DNS 转发器] 接收异常: {ex}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            sock.close()
        except Exception:
            pass


def get_dns_stats() -> dict[str, Any]:
    return {
        "cache_size": _dns_cache.size,
        "cache_limit": DNS_FORWARDER_CACHE_SIZE,
        "upstream_servers": DNS_UPSTREAM_SERVERS,
        "listen_host": DNS_FORWARDER_HOST,
        "listen_port": DNS_FORWARDER_PORT,
        "blocklist_enabled": DNS_BLOCKLIST_ENABLED,
        "blocklist_rules": len(_blocklist) if _blocklist_loaded else 0,
        "blocked_count": _blocked_count,
    }
