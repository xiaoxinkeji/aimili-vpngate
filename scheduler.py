#!/usr/bin/env python3
"""轻量级定时任务调度器 — 单线程周期性任务执行。"""

from __future__ import annotations
import threading
import time
import traceback
from typing import Any, Callable


class ScheduledTask:
    def __init__(self, name: str, interval_seconds: float, func: Callable[[], Any]) -> None:
        self.name = name
        self.interval_seconds = interval_seconds
        self.func = func
        self.last_run: float = 0.0
        self.last_status: str = "pending"
        self.last_error: str = ""
        self.run_count: int = 0
        self.last_duration_ms: float = 0.0

    def due(self, now: float) -> bool:
        return now - self.last_run >= self.interval_seconds

    def run(self) -> None:
        start = time.monotonic()
        try:
            self.func()
            self.last_status = "ok"
            self.last_error = ""
        except Exception as e:
            self.last_status = "error"
            self.last_error = str(e)
            traceback.print_exc()
        finally:
            self.last_run = time.time()
            self.last_duration_ms = round((time.monotonic() - start) * 1000, 2)
            self.run_count += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "interval_seconds": self.interval_seconds,
            "last_run": self.last_run,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "run_count": self.run_count,
            "last_duration_ms": self.last_duration_ms,
            "next_run_in": max(0.0, self.interval_seconds - (time.time() - self.last_run)) if self.last_run else 0.0,
        }


class TaskScheduler:
    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def register(self, name: str, interval_seconds: float, func: Callable[[], Any]) -> None:
        with self._lock:
            self._tasks[name] = ScheduledTask(name, interval_seconds, func)

    def unregister(self, name: str) -> None:
        with self._lock:
            self._tasks.pop(name, None)

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            now = time.time()
            with self._lock:
                due_tasks = [t for t in self._tasks.values() if t.due(now)]
            for task in due_tasks:
                task.run()
            self._stop_event.wait(5.0)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="task-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"tasks": [t.snapshot() for t in self._tasks.values()]}

    def trigger(self, name: str) -> bool:
        with self._lock:
            task = self._tasks.get(name)
        if task is None:
            return False
        task.run()
        return True


scheduler = TaskScheduler()
