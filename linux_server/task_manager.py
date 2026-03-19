#!/usr/bin/env python3
"""Task management for Linux OBS downloader daemon (simplified)."""
import time
from linux_server.status_db import add_task, get_tasks, update_task

class TaskManager:
    def __init__(self):
        pass

    def _generate_task_id(self) -> str:
        import time, random
        return f"task_{int(time.time())}_{random.randint(1000,9999)}"

    def add_task(self, task_id: str, data: dict) -> None:
        """添加任务到数据库"""
        add_task(task_id, data)  # type: ignore

    def get_status(self, task_id: str):
        tasks = get_tasks()
        return tasks.get(task_id)

    def list_tasks(self):
        return get_tasks()

    def pause_task(self, task_id: str):
        update_task(task_id, {"status": "paused"})

    def resume_task(self, task_id: str):
        update_task(task_id, {"status": "pending"})

    def cancel_task(self, task_id: str):
        update_task(task_id, {"status": "cancelled"})

    def _existing_or_new_id(self):
        return self._generate_task_id()
