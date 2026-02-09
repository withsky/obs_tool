#!/usr/bin/env python3
"""Folder synchronization helper: convert OBS folder into tasks."""
import json
import os
from typing import List

try:
    from linux_server.obs_operator import ObsWrapper
except Exception:
    ObsWrapper = None  # type: ignore

from linux_server.status_db import add_task
from linux_server.task_manager import TaskManager  # type: ignore
from linux_server.obs_operator import ObsWrapper  # type: ignore
from linux_server.config import load_config  # type: ignore

def batch_create_tasks(bucket: str, obs_prefix: str, target_dir: str, created_by: str, after_ts=None) -> List[str]:
    """List OBS objects under prefix and create a separate task per object after after_ts.
    Returns a list of created task IDs.
    """
    task_ids = []
    if ObsWrapper is None:
        return task_ids
    obs = ObsWrapper()
    objs = obs.list_objects(bucket, obs_prefix)
    tm = TaskManager()
    import time
    for obj in objs:
        last_mod = obj.get("last_modified")
        if last_mod is None:
            last_mod = obj.get("LastModified")
        # Normalize last_mod to int seconds since epoch
        if isinstance(last_mod, str):
            try:
                last_mod = int(last_mod)
            except Exception:
                last_mod = 0
        elif isinstance(last_mod, (int, float)):
            last_mod = int(last_mod)
        else:
            last_mod = 0
        if after_ts is not None and last_mod <= int(after_ts):
            continue
        task_id = tm._generate_task_id()
        data = {
            "id": task_id,
            "type": "single_file",
            "object_key": obj.get("key"),
            "target_dir": target_dir,
            "bucket": bucket,
            "created_by": created_by,
            "created_at": int(time.time()),
            "status": "pending",
            "total_size": int(obj.get("size", 0)),
            "piece_size": 4 * 1024 * 1024,
            "progress": {"downloaded": 0, "total": int(obj.get("size", 0)), "percentage": 0},
        }
        tm.add_task(task_id, data)
        task_ids.append(task_id)
    return task_ids
