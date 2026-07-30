#!/usr/bin/env python3
from __future__ import annotations
import base64
import os
import secrets
import select
import socket
import threading
import urllib.parse
import time
from pathlib import Path
from typing import Any

def parse_positive_int(value: str | None, default: int) -> int:
    try:
        return max(1, int(value or default))
    except (TypeError, ValueError):
        return default

MAX_PROXY_CONNECTIONS = parse_positive_int(os.environ.get("LOCAL_PROXY_MAX_CONNECTIONS"), 256)
RELAY_BUFFER_MAX = parse_positive_int(os.environ.get("LOCAL_PROXY_RELAY_BUFFER_KB"), 256) * 1024
proxy_connection_sem = threading.BoundedSemaphore(MAX_PROXY_CONNECTIONS)

_acl_allow: list[str] = [a.strip() for a in os.environ.get("PER_CLIENT_ALLOW_IPS", "").split(",") if a.strip()]
_acl_deny: list[str] = [a.strip() for a in os.environ.get("PER_CLIENT_DENY_IPS", "").split(",") if a.strip()]
_acl_blocked_count: int = 0
_acl_lock = threading.Lock()


def _check_acl(client_ip: str) -> bool:
    global _acl_blocked_count
    if not _acl_allow and not _acl_deny:
        return True
    if _acl_allow:
        if client_ip in _acl_allow:
            return True
        with _acl_lock:
            _acl_blocked_count += 1
        return False
    if client_ip in _acl_deny:
        with _acl_lock:
            _acl_blocked_count += 1
        return False
    return True


def get_acl_status() -> dict[str, Any]:
    with _acl_lock:
        return {
            "allow_ips": _acl_allow,
            "deny_ips": _acl_deny,
            "blocked_count": _acl_blocked_count,
            "mode": "none" if not _acl_allow and not _acl_deny else ("allowlist" if _acl_allow else "denylist"),
        }


class TrafficStats:
    """线程安全的代理流量统计器。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.bytes_in: int = 0
        self.bytes_out: int = 0
        self.total_connections: int = 0
        self.active_connections: int = 0
        self._window: list[tuple[float, int, int]] = []

    def add_connection(self) -> None:
        with self._lock:
            self.total_connections += 1
            self.active_connections += 1

    def remove_connection(self) -> None:
        with self._lock:
            self.active_connections = max(0, self.active_connections - 1)

    def add_bytes(self, in_bytes: int, out_bytes: int) -> None:
        now = time.time()
        with self._lock:
            self.bytes_in += in_bytes
            self.bytes_out += out_bytes
            self._window.append((now, in_bytes, out_bytes))
            cutoff = now - 5.0
            self._window = [(t, bi, bo) for t, bi, bo in self._window if t > cutoff]

    def throughput(self) -> tuple[float, float]:
        """返回最近 5 秒内的平均吞吐量 (bytes/s)。"""
        with self._lock:
            if not self._window:
                return 0.0, 0.0
            now = time.time()
            cutoff = now - 5.0
            total_in = 0
            total_out = 0
            for t, bi, bo in self._window:
                if t > cutoff:
                    total_in += bi
                    total_out += bo
            duration = now - self._window[0][0] if self._window else 5.0
            if duration <= 0:
                return 0.0, 0.0
            return total_in / duration, total_out / duration

    def snapshot(self) -> dict[str, Any]:
        in_rate, out_rate = self.throughput()
        with self._lock:
            return {
                "bytes_in": self.bytes_in,
                "bytes_out": self.bytes_out,
                "bytes_in_mb": round(self.bytes_in / (1024 * 1024), 2),
                "bytes_out_mb": round(self.bytes_out / (1024 * 1024), 2),
                "throughput_in_mbps": round(in_rate * 8 / 1_000_000, 2),
                "throughput_out_mbps": round(out_rate * 8 / 1_000_000, 2),
                "total_connections": self.total_connections,
                "active_connections": self.active_connections,
            }


_traffic = TrafficStats()
get_traffic_stats = _traffic.snapshot


class SessionTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._counter: int = 0

    def create(self, src_ip: str, target: str, protocol: str) -> str:
        sid = f"s{int(time.time()*1000):x}-{self._counter:x}"
        self._counter += 1
        entry: dict[str, Any] = {
            "id": sid,
            "src_ip": src_ip,
            "target": target,
            "protocol": protocol,
            "started_at": time.time(),
            "bytes_in": 0,
            "bytes_out": 0,
            "alive": True,
        }
        with self._lock:
            self._sessions[sid] = entry
        _traffic.add_connection()
        return sid

    def add_bytes(self, sid: str, in_bytes: int, out_bytes: int) -> None:
        with self._lock:
            s = self._sessions.get(sid)
            if s:
                s["bytes_in"] += in_bytes
                s["bytes_out"] += out_bytes

    def close(self, sid: str) -> None:
        with self._lock:
            s = self._sessions.get(sid)
            if s:
                s["alive"] = False
                s["ended_at"] = time.time()
        _traffic.remove_connection()

    def list_active(self) -> list[dict[str, Any]]:
        with self._lock:
            return [s for s in self._sessions.values() if s["alive"]]

    def get(self, sid: str) -> dict[str, Any] | None:
        with self._lock:
            return self._sessions.get(sid)

    def cleanup(self, max_age: float = 3600.0) -> int:
        now = time.time()
        removed = 0
        with self._lock:
            stale = [sid for sid, s in self._sessions.items()
                     if not s["alive"] and now - s.get("ended_at", now) > max_age]
            for sid in stale:
                del self._sessions[sid]
                removed += 1
        return removed

    def stats(self) -> dict[str, Any]:
        with self._lock:
            alive = sum(1 for s in self._sessions.values() if s["alive"])
            total = len(self._sessions)
        return {"active": alive, "total": total}


_sessions = SessionTracker()
get_sessions = _sessions.list_active
get_session = _sessions.get


class ClientRateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[float, float, float]] = {}  # ip -> (tokens_in, tokens_out, last_refill)
        self._limit_kbps = max(0.0, float(os.environ.get("PER_CLIENT_LIMIT_KBPS", "0")))
        self._burst_kb = max(0.0, float(os.environ.get("PER_CLIENT_BURST_KB", "0")))

    @property
    def enabled(self) -> bool:
        return self._limit_kbps > 0

    def consume(self, client_ip: str, in_bytes: int, out_bytes: int) -> float:
        if not self.enabled:
            return 0.0
        kb_total = (in_bytes + out_bytes) / 1024.0
        now = time.monotonic()
        with self._lock:
            tokens, _, last = self._buckets.get(client_ip, (self._burst_kb or self._limit_kbps, 0.0, now))
            elapsed = now - last
            tokens = min(self._burst_kb or self._limit_kbps, tokens + elapsed * self._limit_kbps)
            wait = max(0.0, (kb_total - tokens) / self._limit_kbps) if self._limit_kbps > 0 else 0.0
            tokens = max(0.0, tokens - kb_total)
            self._buckets[client_ip] = (tokens, 0.0, now)
            return wait

    def cleanup(self, max_age: float = 300.0) -> int:
        now = time.monotonic()
        removed = 0
        with self._lock:
            stale = [ip for ip, (_, _, last) in self._buckets.items() if now - last > max_age]
            for ip in stale:
                del self._buckets[ip]
                removed += 1
        return removed

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.enabled,
                "limit_kbps": self._limit_kbps,
                "burst_kb": self._burst_kb,
                "active_clients": len(self._buckets),
            }


_client_limiter = ClientRateLimiter()
get_client_limit_status = _client_limiter.status


class UserTrafficAccountant:
    """线程安全的按用户流量统计器，持久化到 JSON 文件。"""

    def __init__(self, data_dir: str = "") -> None:
        self._lock = threading.Lock()
        self._users: dict[str, dict[str, int]] = {}
        self._file = Path(data_dir) / "user_traffic.json" if data_dir else Path("user_traffic.json")
        self._dirty = False
        self._load()

    def _load(self) -> None:
        try:
            if self._file.exists():
                import json as _json
                data = _json.loads(self._file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, dict):
                            self._users[k] = {
                                "bytes_in": int(v.get("bytes_in", 0)),
                                "bytes_out": int(v.get("bytes_out", 0)),
                                "connections": int(v.get("connections", 0)),
                            }
        except Exception as e:
            print(f"[计费] 加载流量统计文件失败: {e}", flush=True)

    def flush(self) -> None:
        if not self._dirty:
            return
        with self._lock:
            try:
                self._file.parent.mkdir(parents=True, exist_ok=True)
                import json as _json
                self._file.write_text(_json.dumps(self._users, ensure_ascii=False, indent=2), encoding="utf-8")
                self._dirty = False
            except Exception as e:
                print(f"[计费] 保存流量统计文件失败: {e}", flush=True)

    def add_bytes(self, username: str, in_bytes: int, out_bytes: int) -> None:
        if not username:
            username = "anonymous"
        with self._lock:
            entry = self._users.setdefault(username, {"bytes_in": 0, "bytes_out": 0, "connections": 0})
            entry["bytes_in"] += in_bytes
            entry["bytes_out"] += out_bytes
            self._dirty = True

    def add_connection(self, username: str) -> None:
        if not username:
            username = "anonymous"
        with self._lock:
            entry = self._users.setdefault(username, {"bytes_in": 0, "bytes_out": 0, "connections": 0})
            entry["connections"] += 1
            self._dirty = True

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            result = []
            for username, entry in self._users.items():
                result.append({
                    "username": username,
                    "bytes_in": entry["bytes_in"],
                    "bytes_out": entry["bytes_out"],
                    "bytes_in_mb": round(entry["bytes_in"] / (1024 * 1024), 2),
                    "bytes_out_mb": round(entry["bytes_out"] / (1024 * 1024), 2),
                    "connections": entry["connections"],
                })
            result.sort(key=lambda x: x["bytes_in"] + x["bytes_out"], reverse=True)
            return result

    def reset(self) -> None:
        with self._lock:
            self._users.clear()
            self._dirty = True
        self.flush()


_user_traffic = UserTrafficAccountant(os.environ.get("VPNGATE_DATA_DIR", ""))
get_user_traffic = _user_traffic.snapshot
reset_user_traffic = _user_traffic.reset
flush_user_traffic = _user_traffic.flush


def _counted_relay(left: socket.socket, right: socket.socket, session_id: str = "", client_ip: str = "", username: str = "") -> None:
    """带流量统计的数据中继，行为同 relay()。"""
    left.setblocking(False)
    right.setblocking(False)
    sockets = [left, right]
    write_bufs: dict[socket.socket, bytearray] = {}
    in_bytes = 0
    out_bytes = 0
    try:
        while True:
            read_list = [s for s in sockets if s not in write_bufs or len(write_bufs[s]) < RELAY_BUFFER_MAX]
            write_list = [s for s in sockets if s in write_bufs and len(write_bufs[s]) > 0]
            if not read_list and not write_list:
                read_list = sockets[:]
            readable, writable, errored = select.select(read_list, write_list, sockets, 30)
            if errored:
                return
            if not readable and not writable:
                continue
            for sock in writable:
                buf = write_bufs.get(sock)
                if not buf:
                    continue
                try:
                    sent = sock.send(bytes(buf))
                    if sent > 0:
                        del buf[:sent]
                    if len(buf) == 0:
                        del write_bufs[sock]
                except (BlockingIOError, InterruptedError):
                    pass
                except OSError:
                    return
            for sock in readable:
                other = right if sock is left else left
                try:
                    data = sock.recv(65536)
                    if not data:
                        _traffic.add_bytes(in_bytes, out_bytes)
                        if session_id:
                            _sessions.add_bytes(session_id, in_bytes, out_bytes)
                        if username:
                            _user_traffic.add_bytes(username, in_bytes, out_bytes)
                        in_bytes = 0
                        out_bytes = 0
                        return
                    target_buf = write_bufs.setdefault(other, bytearray())
                    target_buf.extend(data)
                    if sock is left:
                        in_bytes += len(data)
                    else:
                        out_bytes += len(data)
                    if client_ip and _client_limiter.enabled and in_bytes + out_bytes >= 65536:
                        wait = _client_limiter.consume(client_ip, in_bytes, out_bytes)
                        in_bytes = 0
                        out_bytes = 0
                        if wait > 0:
                            time.sleep(min(wait, 1.0))
                except (BlockingIOError, InterruptedError):
                    pass
                except OSError:
                    _traffic.add_bytes(in_bytes, out_bytes)
                    if session_id:
                        _sessions.add_bytes(session_id, in_bytes, out_bytes)
                    if username:
                        _user_traffic.add_bytes(username, in_bytes, out_bytes)
                    in_bytes = 0
                    out_bytes = 0
                    return
    finally:
        if in_bytes > 0 or out_bytes > 0:
            _traffic.add_bytes(in_bytes, out_bytes)
            if session_id:
                _sessions.add_bytes(session_id, in_bytes, out_bytes)
            if username:
                _user_traffic.add_bytes(username, in_bytes, out_bytes)

def parse_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

def recv_exact(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("Unexpected disconnect.")
        data += chunk
    return data

def parse_host_port(authority: str, default_port: int) -> tuple[str, int]:
    authority = authority.strip()
    if authority.startswith("["):
        host_part, sep, rest = authority.partition("]")
        host = host_part.lstrip("[")
        port = default_port
        if sep and rest.startswith(":"):
            port_text = rest[1:]
            port = parse_int(port_text) or default_port
        return host, port
    if authority.count(":") == 1:
        host, _, port_text = authority.rpartition(":")
        return host, parse_int(port_text) or default_port
    return authority, default_port

_cached_credentials: list[tuple[str | None, str | None] | None] = [None]
_users: list[tuple[str, str]] = []
_users_lock = threading.Lock()
_users_file = os.environ.get("LOCAL_PROXY_USERS_FILE", "")
_users_mtime: float = 0.0
_users_loaded: bool = False


def _is_auth_disabled() -> bool:
    user = os.environ.get("LOCAL_PROXY_USER") or os.environ.get("LOCAL_PROXY_USERNAME")
    password = os.environ.get("LOCAL_PROXY_PASS") or os.environ.get("LOCAL_PROXY_PASSWORD")
    return user is None and password is None and not _users_file


def _load_users_file() -> list[tuple[str, str]]:
    if not _users_file:
        return []
    try:
        fpath = Path(_users_file)
        if not fpath.exists():
            return []
        mtime = fpath.stat().st_mtime
        global _users_mtime, _users, _users_loaded
        if mtime == _users_mtime and _users_loaded:
            return list(_users)
        import json as _json
        data = _json.loads(fpath.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        entries: list[tuple[str, str]] = []
        for item in data:
            if isinstance(item, dict):
                u = str(item.get("username", "")).strip()
                p = str(item.get("password", "")).strip()
                if u and p:
                    entries.append((u, p))
        if entries:
            _users_mtime = mtime
            _users = entries
            _users_loaded = True
            print(f"[代理认证] 从 {_users_file} 加载了 {len(entries)} 个用户", flush=True)
        return entries
    except Exception as e:
        print(f"[代理认证] 加载用户文件失败 ({_users_file}): {e}", flush=True)
        return []


def get_proxy_credentials() -> tuple[str | None, str | None]:
    if _cached_credentials[0] is not None:
        return _cached_credentials[0]
    user = os.environ.get("LOCAL_PROXY_USER") or os.environ.get("LOCAL_PROXY_USERNAME")
    password = os.environ.get("LOCAL_PROXY_PASS") or os.environ.get("LOCAL_PROXY_PASSWORD")
    if user is None and password is None and not _users_file:
        _cached_credentials[0] = (None, None)
    elif user is not None or password is not None:
        _cached_credentials[0] = (user or "", password or "")
    else:
        _cached_credentials[0] = ("__file__", "__file__")
    return _cached_credentials[0]


def proxy_auth_enabled() -> bool:
    if _is_auth_disabled():
        return False
    return True


def parse_http_basic_auth(lines: list[str]) -> tuple[str | None, str | None]:
    for line in lines:
        name, sep, value = line.partition(":")
        if not sep or name.strip().lower() != "proxy-authorization":
            continue
        scheme, _, token = value.strip().partition(" ")
        if scheme.lower() != "basic" or not token:
            return None, None
        try:
            decoded = base64.b64decode(token, validate=True).decode("utf-8", errors="replace")
        except Exception:
            return None, None
        username, sep, password = decoded.partition(":")
        if not sep:
            return None, None
        return username, password
    return None, None


def _check_single_user(username: str | None, password: str | None) -> bool:
    expected_user, expected_pass = get_proxy_credentials()
    if expected_user is None or expected_pass is None:
        return True
    if expected_user == "__file__":
        return False
    return secrets.compare_digest(username or "", expected_user) and secrets.compare_digest(password or "", expected_pass)


def check_credentials(username: str | None, password: str | None) -> bool:
    if _is_auth_disabled():
        return True

    if _check_single_user(username, password):
        return True

    entries = _load_users_file()
    if entries:
        u = username or ""
        p = password or ""
        for stored_u, stored_p in entries:
            if secrets.compare_digest(u, stored_u) and secrets.compare_digest(p, stored_p):
                return True

    return False


def get_users_list() -> list[dict[str, str]]:
    """获取所有用户列表 (不含密码)。"""
    result: list[dict[str, str]] = []
    env_user = os.environ.get("LOCAL_PROXY_USER") or os.environ.get("LOCAL_PROXY_USERNAME")
    if env_user:
        result.append({"username": env_user, "source": "env"})
    for u, _ in _load_users_file():
        if not any(r["username"] == u for r in result):
            result.append({"username": u, "source": "file"})
    return result

def dns_query_over_tun0(host: str, qtype: int, dns_server: str, timeout: float) -> str | None:
    import random
    sock = None
    try:
        tx_id = random.getrandbits(16).to_bytes(2, "big")
        flags = b"\x01\x00"
        questions = b"\x00\x01"
        rrs = b"\x00\x00\x00\x00\x00\x00"

        qname = b""
        for part in host.split("."):
            if not part:
                continue
            part_bytes = part.encode("idna")
            if len(part_bytes) > 63:
                return None
            qname += len(part_bytes).to_bytes(1, "big") + part_bytes
        qname += b"\x00"

        qtype_qclass = qtype.to_bytes(2, "big") + b"\x00\x01"
        packet = tx_id + flags + questions + rrs + qname + qtype_qclass

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b"tun0")
        except OSError as e:
            if "operation not permitted" in str(e).lower() or e.errno == 1:
                print("[DNS 绑定失败] [错误代码 3006] DNS 解析绑定 tun0 权限不足，请确保程序以 root 权限运行！", flush=True)
            elif "no such device" in str(e).lower() or e.errno == 19:
                print("[DNS 绑定失败] [错误代码 3004] DNS 解析绑定 tun0 失败，网卡设备不存在，请检查 VPN 连接！", flush=True)
            return None
        sock.sendto(packet, (dns_server, 53))
        resp, _ = sock.recvfrom(4096)
    except Exception:
        return None
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    try:
        if len(resp) < 12 or resp[:2] != tx_id:
            return None
        rcode = resp[3] & 0x0F
        if rcode != 0:
            return None

        offset = 12
        while offset < len(resp):
            length = resp[offset]
            if length == 0:
                offset += 1
                break
            if (length & 0xC0) == 0xC0:
                offset += 2
                break
            offset += 1 + length

        offset += 4
        answers_count = int.from_bytes(resp[6:8], "big")
        for _ in range(answers_count):
            if offset >= len(resp):
                break
            while offset < len(resp):
                length = resp[offset]
                if length == 0:
                    offset += 1
                    break
                if (length & 0xC0) == 0xC0:
                    offset += 2
                    break
                offset += 1 + length
            if offset + 10 > len(resp):
                break
            atype = int.from_bytes(resp[offset : offset + 2], "big")
            aclass = int.from_bytes(resp[offset + 2 : offset + 4], "big")
            rdlength = int.from_bytes(resp[offset + 8 : offset + 10], "big")
            offset += 10
            if offset + rdlength > len(resp):
                break
            record = resp[offset : offset + rdlength]
            if atype == qtype and aclass == 1:
                if qtype == 1 and rdlength == 4:
                    return socket.inet_ntoa(record)
                if qtype == 28 and rdlength == 16:
                    return socket.inet_ntop(socket.AF_INET6, record)
            offset += rdlength
    except Exception:
        return None
    return None

_dns_cache: dict[str, tuple[str, float]] = {}
_dns_cache_lock = threading.Lock()


def resolve_dns_over_tun0(host: str, dns_server: str = "8.8.8.8", timeout: float = 3.0) -> str | None:
    try:
        socket.inet_aton(host)
        return host
    except OSError:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, host)
        return host
    except OSError:
        pass

    now = time.time()
    with _dns_cache_lock:
        entry = _dns_cache.get(host)
        if entry is not None and now - entry[1] < 300:
            return entry[0]

    result = dns_query_over_tun0(host, 1, dns_server, timeout) or dns_query_over_tun0(host, 28, dns_server, timeout)

    if result is not None:
        with _dns_cache_lock:
            _dns_cache[host] = (result, time.time())
            if len(_dns_cache) > 512:
                for key in sorted(_dns_cache.keys()):
                    if len(_dns_cache) <= 384:
                        break
                    del _dns_cache[key]

    return result

def _optimize_socket(sock: socket.socket) -> None:
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except OSError:
        pass
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
    except (OSError, AttributeError):
        pass
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
    except (OSError, AttributeError):
        pass
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
    except (OSError, AttributeError):
        pass
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_QUICKACK, 1)
    except (OSError, AttributeError):
        pass


def create_connection(address: tuple[str, int], timeout: float = 20) -> socket.socket:
    host, port = address
    resolved_ip = resolve_dns_over_tun0(host)
    if resolved_ip:
        host = resolved_ip

    err = None
    # Fallback to system DNS is intentional: tun0 may not be ready for all hosts
    for res in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
        af, socktype, proto, canonname, sa = res
        sock = None
        try:
            sock = socket.socket(af, socktype, proto)
            sock.settimeout(timeout)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b"tun0")
            sock.connect(sa)
            _optimize_socket(sock)
            return sock
        except OSError as e:
            err = e
            if "operation not permitted" in str(e).lower() or e.errno == 1:
                err = OSError("[错误代码 3006] [ERR_PROXY_BIND_TUN_PERM_DENIED] 绑定虚拟网卡 tun0 失败，权限不足！必须以 root 权限运行，或者进程缺少 CAP_NET_RAW 权限。")
            elif "no such device" in str(e).lower() or e.errno == 19:
                err = OSError("[错误代码 3004] [ERR_ROUTE_DEV_NOT_FOUND] 绑定虚拟网卡 tun0 失败，找不到设备！这通常是因为 OpenVPN 核心未能成功连接或已被异常终止。")
            if sock is not None:
                sock.close()
    if err is not None:
        raise err
    else:
        raise OSError("getaddrinfo returns empty list")

def relay(left: socket.socket, right: socket.socket) -> None:
    left.setblocking(False)
    right.setblocking(False)
    sockets = [left, right]
    write_bufs: dict[socket.socket, bytearray] = {}
    while True:
        read_list = [s for s in sockets if s not in write_bufs or len(write_bufs[s]) < RELAY_BUFFER_MAX]
        write_list = [s for s in sockets if s in write_bufs and len(write_bufs[s]) > 0]
        if not read_list and not write_list:
            read_list = sockets[:]
        readable, writable, errored = select.select(read_list, write_list, sockets, 30)
        if errored:
            return
        if not readable and not writable:
            continue
        for sock in writable:
            buf = write_bufs.get(sock)
            if not buf:
                continue
            try:
                sent = sock.send(bytes(buf))
                if sent > 0:
                    del buf[:sent]
                if len(buf) == 0:
                    del write_bufs[sock]
            except (BlockingIOError, InterruptedError):
                pass
            except OSError:
                return
        for sock in readable:
            other = right if sock is left else left
            try:
                data = sock.recv(65536)
                if not data:
                    return
                target_buf = write_bufs.setdefault(other, bytearray())
                target_buf.extend(data)
            except (BlockingIOError, InterruptedError):
                pass
            except OSError:
                return

def _socks5_address_bytes(host: str) -> tuple[int, bytes]:
    try:
        packed = socket.inet_aton(host)
        return 1, packed
    except OSError:
        pass
    try:
        packed = socket.inet_pton(socket.AF_INET6, host)
        return 4, packed
    except OSError:
        pass
    host_enc = host.encode("idna")
    if len(host_enc) > 255:
        raise ValueError("hostname too long")
    return 3, bytes([len(host_enc)]) + host_enc


def _create_udp_outbound_socket(timeout: float = 5.0) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, b"tun0")
    except OSError:
        pass
    return sock


def _udp_associate_reply(bind_addr: str, bind_port: int) -> bytes:
    atype, addr_bytes = _socks5_address_bytes(bind_addr)
    return b"\x05\x00\x00" + bytes([atype]) + addr_bytes + bind_port.to_bytes(2, "big")


def socks5_udp_relay(relay_sock: socket.socket, client_addr: tuple[str, int],
                     shutdown_event: threading.Event, timeout: float = 5.0) -> None:
    while not shutdown_event.is_set():
        try:
            data, addr = relay_sock.recvfrom(65536)
        except socket.timeout:
            continue
        except OSError:
            if shutdown_event.is_set():
                break
            continue

        if not data or len(data) < 10:
            continue

        _rsv = data[0:2]
        frag = data[2]
        atype = data[3]

        if frag != 0:
            continue

        offset = 4
        if atype == 1:
            if offset + 4 > len(data):
                continue
            dst_host = socket.inet_ntoa(data[offset:offset + 4])
            offset += 4
        elif atype == 3:
            if offset + 1 > len(data):
                continue
            name_len = data[offset]
            offset += 1
            if offset + name_len > len(data):
                continue
            dst_host = data[offset:offset + name_len].decode("idna", errors="replace")
            offset += name_len
        elif atype == 4:
            if offset + 16 > len(data):
                continue
            dst_host = socket.inet_ntop(socket.AF_INET6, data[offset:offset + 16])
            offset += 16
        else:
            continue

        if offset + 2 > len(data):
            continue
        dst_port = int.from_bytes(data[offset:offset + 2], "big")
        offset += 2
        payload = data[offset:]

        resolved_ip = resolve_dns_over_tun0(dst_host)
        if resolved_ip is None:
            continue

        out_sock = _create_udp_outbound_socket(timeout)
        try:
            out_sock.sendto(payload, (resolved_ip, dst_port))
            try:
                resp_data, resp_addr = out_sock.recvfrom(65536)
                resp_host = resp_addr[0]
                resp_port = resp_addr[1]
                atype_r, addr_bytes_r = _socks5_address_bytes(resp_host)
                response = b"\x00\x00\x00" + bytes([atype_r]) + addr_bytes_r
                response += resp_port.to_bytes(2, "big") + resp_data
                relay_sock.sendto(response, addr)
            except socket.timeout:
                pass
        except Exception:
            pass
        finally:
            try:
                out_sock.close()
            except Exception:
                pass


def socks5_client(client: socket.socket, first_byte: bytes) -> None:
    upstream = None
    udp_relay_sock = None
    socks5_username = "anonymous"
    try:
        methods_count = recv_exact(client, 1)[0]
        methods = recv_exact(client, methods_count)
        if proxy_auth_enabled():
            if 2 not in methods:
                client.sendall(b"\x05\xff")
                return
            client.sendall(b"\x05\x02")
            auth_version = recv_exact(client, 1)[0]
            if auth_version != 1:
                client.sendall(b"\x01\x01")
                return
            username = recv_exact(client, recv_exact(client, 1)[0]).decode("utf-8", errors="replace")
            password = recv_exact(client, recv_exact(client, 1)[0]).decode("utf-8", errors="replace")
            if not check_credentials(username, password):
                client.sendall(b"\x01\x01")
                return
            socks5_username = username
            client.sendall(b"\x01\x00")
        else:
            client.sendall(b"\x05\x00")
        version, command, _, address_type = recv_exact(client, 4)
        if version != 5:
            client.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
            return

        # Parse destination address (shared by CONNECT and UDP ASSOCIATE)
        if address_type == 1:
            host = socket.inet_ntoa(recv_exact(client, 4))
        elif address_type == 3:
            host = recv_exact(client, recv_exact(client, 1)[0]).decode("idna")
        elif address_type == 4:
            host = socket.inet_ntop(socket.AF_INET6, recv_exact(client, 16))
        else:
            client.sendall(b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00")
            return
        port = int.from_bytes(recv_exact(client, 2), "big")

        if command == 3:
            # UDP ASSOCIATE — allocate UDP relay socket
            udp_relay_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_relay_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                udp_relay_sock.bind(("0.0.0.0", 0))
            except OSError:
                client.sendall(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")
                return
            relay_host, relay_port = udp_relay_sock.getsockname()
            client_addr = client.getpeername()

            # Send UDP ASSOCIATE success reply
            reply = _udp_associate_reply("0.0.0.0", relay_port)
            client.sendall(reply)

            # Start UDP relay thread
            shutdown_event = threading.Event()
            relay_thread = threading.Thread(
                target=socks5_udp_relay,
                args=(udp_relay_sock, client_addr, shutdown_event),
                daemon=True,
            )
            relay_thread.start()

            # Keep TCP control connection alive
            try:
                client.settimeout(300)
                while True:
                    chunk = client.recv(1)
                    if not chunk:
                        break
            except Exception:
                pass
            finally:
                shutdown_event.set()
            return

        if command != 1:
            client.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
            return

        # CONNECT — existing logic
        try:
            upstream = create_connection((host, port), timeout=20)
        except Exception as e:
            print(f"[SOCKS5 代理失败] 目标 {host}:{port} 连接失败: {e}", flush=True)
            try:
                client.sendall(b"\x05\x04\x00\x01\x00\x00\x00\x00\x00\x00")
            except OSError:
                pass
            raise
        client.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
        try:
            client_addr = client.getpeername()[0]
        except Exception:
            client_addr = "unknown"
        sid = _sessions.create(client_addr, f"{host}:{port}", "socks5")
        _user_traffic.add_connection(socks5_username)
        try:
            _counted_relay(client, upstream, sid, client_addr, socks5_username)
        finally:
            _sessions.close(sid)
    finally:
        client.close()
        if upstream:
            upstream.close()
        if udp_relay_sock:
            try:
                udp_relay_sock.close()
            except OSError:
                pass

def read_http_header(client: socket.socket, first_byte: bytes) -> bytes:
    data = first_byte
    while b"\r\n\r\n" not in data and len(data) < 65536:
        chunk = client.recv(4096)
        if not chunk:
            break
        data += chunk
    return data

def http_client(client: socket.socket, first_byte: bytes) -> None:
    upstream = None
    http_username = "anonymous"
    try:
        header = read_http_header(client, first_byte)
        if b"\r\n\r\n" not in header:
            client.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
            return
        head, rest = header.split(b"\r\n\r\n", 1)
        lines = head.decode("iso-8859-1", errors="replace").split("\r\n")
        try:
            method, target, version = lines[0].split(" ", 2)
        except ValueError:
            client.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
            return
        if not version.startswith("HTTP/"):
            client.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
            return
        if proxy_auth_enabled():
            username, password = parse_http_basic_auth(lines[1:])
            if not check_credentials(username, password):
                client.sendall(
                    b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                    b"Proxy-Authenticate: Basic realm=\"AimiliVPN Proxy\"\r\n"
                    b"Content-Length: 0\r\n\r\n"
                )
                return
            http_username = username or "anonymous"
        if method.upper() == "CONNECT":
            host, port = parse_host_port(target, 443)
            upstream = create_connection((host, port), timeout=20)
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            if rest:
                upstream.sendall(rest)
            try:
                client_addr = client.getpeername()[0]
            except Exception:
                client_addr = "unknown"
            sid = _sessions.create(client_addr, f"{host}:{port}", "http_connect")
            _user_traffic.add_connection(http_username)
            try:
                _counted_relay(client, upstream, sid, client_addr, http_username)
            finally:
                _sessions.close(sid)
            return

        try:
            parsed = urllib.parse.urlsplit(target)
        except ValueError:
            client.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
            return
        hostname = parsed.hostname
        port = parsed.port
        scheme = parsed.scheme
        if not hostname:
            # Fallback to Host header
            for line in lines[1:]:
                if line.lower().startswith("host:"):
                    host_val = line.split(":", 1)[1].strip()
                    if "[" in host_val and "]" in host_val:
                        host_part, _, port_part = host_val.rpartition("]")
                        hostname = host_part.lstrip("[")
                        if port_part.startswith(":"):
                            p_val = port_part.lstrip(":")
                            port = int(p_val) if p_val.isdigit() else None
                        else:
                            port = None
                    else:
                        hostname, parsed_port = parse_host_port(host_val, 0)
                        port = parsed_port or None
                    break
        if not hostname:
            client.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
            return
        port = port or (443 if scheme == "https" else 80)
        path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        headers = [line for line in lines[1:] if not line.lower().startswith(("proxy-connection:", "connection:", "proxy-authorization:"))]
        request = f"{method} {path} {version}\r\n" + "\r\n".join(headers) + "\r\nConnection: close\r\n\r\n"
        upstream = create_connection((hostname, port), timeout=20)
        upstream.sendall(request.encode("iso-8859-1") + rest)
        try:
            client_addr = client.getpeername()[0]
        except Exception:
            client_addr = "unknown"
        sid = _sessions.create(client_addr, f"{hostname}:{port}", "http")
        _user_traffic.add_connection(http_username)
        try:
            _counted_relay(client, upstream, sid, client_addr, http_username)
        finally:
            _sessions.close(sid)
    except Exception as e:
        print(f"[HTTP 代理失败] 代理请求目标连接失败: {e}", flush=True)
        try:
            client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        except OSError:
            pass
    finally:
        client.close()
        if upstream:
            upstream.close()

def proxy_client(client: socket.socket, address: tuple[str, int]) -> None:
    entered = False
    client_ip = address[0]
    if not _check_acl(client_ip):
        try:
            client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
        except OSError:
            pass
        return
    try:
        client.settimeout(30)
        first = recv_exact(client, 1)
        entered = True
        if first == b"\x05":
            socks5_client(client, first)
        else:
            http_client(client, first)
    except Exception as e:
        err_msg = str(e)
        if "[错误代码" in err_msg:
            print(f"[代理客户端连接失败] 客户端 {address} 遭遇系统性阻碍: {err_msg}", flush=True)
        if not entered:
            try:
                client.close()
            except OSError:
                pass

def start_proxy_server(host: str, port: int) -> None:
    is_ipv6 = ":" in host or host == ""
    af = socket.AF_INET6 if is_ipv6 else socket.AF_INET
    server = None
    try:
        server = socket.socket(af, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if is_ipv6:
            try:
                server.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            except OSError:
                pass
        server.bind((host, port))
        server.listen(256)
        print(f"HTTP/SOCKS5 proxy listening on {host}:{port}", flush=True)
    except Exception as e:
        if server is not None:
            try:
                server.close()
            except Exception:
                pass
        if is_ipv6 and host in ("::", ""):
            print(f"[警告] 绑定 IPv6 {host}:{port} 失败 ({e})，正在尝试回退至 IPv4 0.0.0.0 ...", flush=True)
            try:
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind(("0.0.0.0", port))
                server.listen(256)
                print(f"HTTP/SOCKS5 proxy listening on 0.0.0.0:{port} (仅 IPv4)", flush=True)
            except Exception as ex:
                import vpn_utils
                diag = vpn_utils.diagnose_local_obstructions(port, host="0.0.0.0")
                diag_msg = diag[1] if diag else str(ex)
                print(f"[ERROR] Failed to start HTTP/SOCKS5 proxy on 0.0.0.0:{port}: {diag_msg}", flush=True)
                return
        elif is_ipv6 and host == "::1":
            print(f"[警告] 绑定 IPv6 {host}:{port} 失败 ({e})，正在尝试回退至 IPv4 127.0.0.1 ...", flush=True)
            try:
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind(("127.0.0.1", port))
                server.listen(256)
                print(f"HTTP/SOCKS5 proxy listening on 127.0.0.1:{port} (仅 IPv4)", flush=True)
            except Exception as ex:
                import vpn_utils
                diag = vpn_utils.diagnose_local_obstructions(port, host="127.0.0.1")
                diag_msg = diag[1] if diag else str(ex)
                print(f"[ERROR] Failed to start HTTP/SOCKS5 proxy on 127.0.0.1:{port}: {diag_msg}", flush=True)
                return
        else:
            import vpn_utils
            diag = vpn_utils.diagnose_local_obstructions(port, host=host)
            diag_msg = diag[1] if diag else str(e)
            print(f"[ERROR] Failed to start HTTP/SOCKS5 proxy on {host}:{port}: {diag_msg}", flush=True)
            return

    while True:
        try:
            client, address = server.accept()
            if not proxy_connection_sem.acquire(blocking=False):
                print(f"[代理限流] 当前连接数已达到上限 {MAX_PROXY_CONNECTIONS}，拒绝客户端 {address}", flush=True)
                try:
                    client.close()
                except OSError:
                    pass
                continue

            def run_client() -> None:
                try:
                    proxy_client(client, address)
                finally:
                    proxy_connection_sem.release()

            threading.Thread(target=run_client, daemon=True).start()
        except Exception as e:
            print(f"[ERROR] Proxy accept failed: {e}", flush=True)
            time.sleep(0.5)
