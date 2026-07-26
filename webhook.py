#!/usr/bin/env python3
from __future__ import annotations
import json
import os
import threading
import time
import urllib.request
from typing import Any


WEBHOOK_URLS: list[str] = []
WEBHOOK_TIMEOUT = int(os.environ.get("WEBHOOK_TIMEOUT", "10"))
WEBHOOK_RETRIES = int(os.environ.get("WEBHOOK_RETRIES", "3"))
WEBHOOK_RETRY_DELAY = float(os.environ.get("WEBHOOK_RETRY_DELAY", "2.0"))

_queue: list[dict[str, Any]] = []
_queue_lock = threading.Lock()
_worker_started = False
_worker_event = threading.Event()


def _load_urls() -> list[str]:
    raw = os.environ.get("WEBHOOK_URLS", "")
    if not raw.strip():
        return []
    urls = [u.strip() for u in raw.split(",") if u.strip()]
    return urls


def _deliver(url: str, payload: dict[str, Any]) -> bool:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    for attempt in range(1, WEBHOOK_RETRIES + 1):
        try:
            resp = urllib.request.urlopen(req, timeout=WEBHOOK_TIMEOUT)
            if 200 <= resp.status < 300:
                return True
        except Exception:
            if attempt < WEBHOOK_RETRIES:
                time.sleep(WEBHOOK_RETRY_DELAY * attempt)
    return False


def _worker() -> None:
    global WEBHOOK_URLS
    while not _worker_event.is_set():
        item: dict[str, Any] | None = None
        with _queue_lock:
            if _queue:
                item = _queue.pop(0)
        if item is None:
            _worker_event.wait(1.0)
            continue
        urls = WEBHOOK_URLS or _load_urls()
        payload = item.get("payload", {})
        for url in urls:
            _deliver(url, payload)


def _ensure_worker() -> None:
    global _worker_started, WEBHOOK_URLS
    if not _worker_started:
        WEBHOOK_URLS = _load_urls()
        t = threading.Thread(target=_worker, daemon=True, name="webhook-worker")
        t.start()
        _worker_started = True


def enqueue(event_type: str, node_id: str | None = None, details: dict[str, Any] | None = None) -> None:
    _ensure_worker()
    if not WEBHOOK_URLS:
        return
    payload: dict[str, Any] = {
        "event_type": event_type,
        "timestamp": time.time(),
        "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if node_id:
        payload["node_id"] = node_id
    if details:
        payload["details"] = details
    with _queue_lock:
        _queue.append({"payload": payload, "enqueued_at": time.time()})


def notify_node_status(node_id: str, status: str, message: str, latency_ms: int = 0) -> None:
    enqueue("node.status_change", node_id=node_id, details={
        "status": status,
        "message": message,
        "latency_ms": latency_ms,
    })


def notify_proxy_health(ok: bool, ip: str = "", latency_ms: int = 0, error: str = "") -> None:
    enqueue("proxy.health_change", details={
        "ok": ok,
        "ip": ip,
        "latency_ms": latency_ms,
        "error": error,
    })


def notify_node_blacklisted(node_id: str, reason: str) -> None:
    enqueue("node.blacklisted", node_id=node_id, details={"reason": reason})


def notify_startup() -> None:
    enqueue("proxy.startup")


def get_webhook_status() -> dict[str, Any]:
    with _queue_lock:
        queue_size = len(_queue)
    return {
        "urls": WEBHOOK_URLS,
        "queue_size": queue_size,
        "worker_running": _worker_started,
        "config": {
            "timeout": WEBHOOK_TIMEOUT,
            "retries": WEBHOOK_RETRIES,
            "retry_delay": WEBHOOK_RETRY_DELAY,
        },
    }
