#!/usr/bin/env python3
"""Thread-safe JSON storage for tasks/history/favorites."""
import json
import os
import time
import fcntl
from typing import Any, Dict

DB_ROOT = "/data9/obs_tool/storage"
TASKS_FILE = os.path.join(DB_ROOT, "tasks_db.json")
HISTORY_FILE = os.path.join(DB_ROOT, "history.json")
FAVORITES_FILE = os.path.join(DB_ROOT, "favorites.json")
LOCK_FILE = os.path.join(DB_ROOT, ".db.lock")

def _acquire_lock() -> object:
    lock_fd = open(LOCK_FILE, "w")
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    return lock_fd

def _release_lock(lock_fd) -> None:
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
    except Exception:
        pass

def _load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default

def _save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_tasks() -> Dict[str, Any]:
    return _load_json(TASKS_FILE, {})

def update_task(task_id: str, updates: Dict[str, Any]) -> None:
    lock_fd = _acquire_lock()
    try:
        tasks = get_tasks()
        if task_id not in tasks:
            raise KeyError(f"Task {task_id} not found")
        tasks[task_id].update(updates)
        _save_json(TASKS_FILE, tasks)
    finally:
        _release_lock(lock_fd)

def add_task(task_id: str, data: Dict[str, Any]) -> None:
    lock_fd = _acquire_lock()
    try:
        tasks = get_tasks()
        tasks[task_id] = data
        _save_json(TASKS_FILE, tasks)
    finally:
        _release_lock(lock_fd)

def add_history(entry: Dict[str, Any]) -> None:
    lock_fd = _acquire_lock()
    try:
        history = _load_json(HISTORY_FILE, [])
        history.append(entry)
        _save_json(HISTORY_FILE, history)
    finally:
        _release_lock(lock_fd)

def get_history(limit: int = 100) -> list:
    history = _load_json(HISTORY_FILE, [])
    return history[-limit:][::-1]

def get_favorites() -> list:
    return _load_json(FAVORITES_FILE, [])

def add_favorite(name: str, path: str) -> None:
    favorites = get_favorites()
    favorites.append({"name": name, "path": path})
    _save_json(FAVORITES_FILE, favorites)
