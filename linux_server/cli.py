#!/usr/bin/env python3
"""Linux side helper CLI for Windows-downloader.
Supports browsing Linux directories to aid path selection on Windows.
"""
import json
import os
import argparse
import sys


def browse_dir(path: str):
    if not os.path.exists(path):
        return {"error": "Path does not exist"}
    if not os.path.isdir(path):
        return {"error": "Path is not a directory"}
    dirs = []
    files = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_dir():
                    dirs.append(entry.name)
                elif entry.is_file():
                    st = entry.stat()
                    files.append({
                        "name": entry.name,
                        "size": st.st_size,
                        "mtime": int(st.st_mtime)
                    })
    except PermissionError:
        return {"error": "Permission denied"}
    return {
        "path": path,
        "dirs": sorted(dirs),
        "files": sorted(files, key=lambda x: x["name"])
    }


def _generate_task_id():
    import time, random
    return f"task_{int(time.time())}_{random.randint(1000,9999)}"

def main():
    parser = argparse.ArgumentParser(description="Linux-side helper CLI for Windows downloader")
    sub = parser.add_subparsers(dest="cmd", required=True)
    browse = sub.add_parser("browse-dir", help="List contents of a directory on the Linux host")
    browse.add_argument("--path", required=True, help="Directory path to browse")
    # List OBS objects with last_modified
    list_obs = sub.add_parser("list-obs", help="List OBS objects with last_modified")
    list_obs.add_argument("--bucket", required=True, help="OBS bucket name")
    list_obs.add_argument("--prefix", default="", help="OBS prefix to list")
    # Sync folder with optional time filter
    sync_folder = sub.add_parser("sync-folder", help="Sync OBS folder with optional time filter")
    sync_folder.add_argument("--bucket", required=True, help="OBS bucket name")
    sync_folder.add_argument("--prefix", required=True, help="OBS prefix to sync")
    sync_folder.add_argument("--target-dir", required=True, help="Local Linux target directory for downloads")
    sync_folder.add_argument("--after", type=int, default=None, help="Only download files modified after this UNIX timestamp (seconds)")
    sync_folder.add_argument("--created-by", default="windows_user", help="Created by identifier")

    args = parser.parse_args()
    if args.cmd == "browse-dir":
        res = browse_dir(args.path)
        print(json.dumps(res))
        sys.exit(0)
    if args.cmd == "list-obs":
        # Lazy import to avoid circular deps in some environments
        from linux_server.obs_operator import ObsWrapper
        obs = ObsWrapper()
        bucket = getattr(args, 'bucket')
        prefix = getattr(args, 'prefix', '')
        objs = obs.list_objects(bucket, prefix)
        print(json.dumps(objs))
        sys.exit(0)
    if args.cmd == "sync-folder":
        from linux_server.folder_sync import batch_create_tasks
        bucket = getattr(args, 'bucket')
        prefix = getattr(args, 'prefix')
        target_dir = getattr(args, 'target_dir')
        after = getattr(args, 'after', None)
        created_by = getattr(args, 'created_by', 'windows_user')
        task_ids = batch_create_tasks(bucket, prefix, target_dir, created_by, after_ts=after)
        print(json.dumps({"tasks": task_ids}))
        sys.exit(0)
    # Additional commands for task management (needed for multi-user sync)
    if args.cmd == "download":
        object_key = getattr(args, 'object_key', None)
        target_dir = getattr(args, 'target_dir', None)
        created_by = getattr(args, 'created_by', 'windows_user')
        if not object_key or not target_dir:
            print(json.dumps({"error": "object_key and target_dir are required"}))
            sys.exit(2)
        from linux_server.task_manager import TaskManager
        tm = TaskManager()
        task_id = _generate_task_id()
        data = {
            "id": task_id,
            "type": "single_file",
            "object_key": object_key,
            "target_dir": target_dir,
            "bucket": "tfds-ht",
            "created_by": created_by,
            "created_at": __import__('time').time(),
            "status": "pending",
            "total_size": 0,
            "piece_size": 4 * 1024 * 1024,
            "progress": {"downloaded": 0, "total": 0, "percentage": 0},
        }
        tm.add_task(task_id, data)
        print(json.dumps({"task_id": task_id, "status": "pending"}))
        sys.exit(0)
    if args.cmd == "status":
        task_id = getattr(args, 'task_id', None)
        if task_id is None:
            print(json.dumps({"error": "task_id required"}))
            sys.exit(2)
        from linux_server.task_manager import TaskManager
        tm = TaskManager()
        status = tm.get_status(task_id)
        print(json.dumps(status or {"error": "not found"}))
        sys.exit(0)
    if args.cmd == "list":
        from linux_server.task_manager import TaskManager
        tm = TaskManager()
        tasks = tm.list_tasks()
        print(json.dumps(tasks))
        sys.exit(0)
    if args.cmd == "pause":
        task_id = getattr(args, 'task_id', None)
        if task_id is None:
            print(json.dumps({"error": "task_id required"}))
            sys.exit(2)
        from linux_server.task_manager import TaskManager
        tm = TaskManager()
        tm.pause_task(task_id)
        print(json.dumps({"task_id": task_id, "status": "paused"}))
        sys.exit(0)
    if args.cmd == "resume":
        task_id = getattr(args, 'task_id', None)
        if task_id is None:
            print(json.dumps({"error": "task_id required"}))
            sys.exit(2)
        from linux_server.task_manager import TaskManager
        tm = TaskManager()
        tm.resume_task(task_id)
        print(json.dumps({"task_id": task_id, "status": "resumed"}))
        sys.exit(0)
    if args.cmd == "cancel":
        task_id = getattr(args, 'task_id', None)
        if task_id is None:
            print(json.dumps({"error": "task_id required"}))
            sys.exit(2)
        from linux_server.task_manager import TaskManager
        tm = TaskManager()
        tm.cancel_task(task_id)
        print(json.dumps({"task_id": task_id, "status": "cancelled"}))
        sys.exit(0)
    if args.cmd == "history":
        from linux_server.status_db import get_history
        limit = int(getattr(args, 'limit', 50))
        hist = get_history(limit)
        print(json.dumps(hist))
        sys.exit(0)
    if args.cmd == "favorites":
        from linux_server.status_db import get_favorites, add_favorite
        action = getattr(args, 'action', 'list')
        if action == 'add':
            name = getattr(args, 'name', '')
            path = getattr(args, 'path', '')
            add_favorite(name, path)
            print(json.dumps({"status": "added"}))
        else:
            print(json.dumps(get_favorites()))
        sys.exit(0)
    if args.cmd == "browse-obs":
        # 获取OBS目录树结构
        bucket = getattr(args, 'bucket', 'tfds-ht')
        prefix = getattr(args, 'prefix', '')
        try:
            from linux_server.obs_operator import ObsWrapper
            obs = ObsWrapper()
            tree = obs.get_directory_tree(bucket, prefix)
            print(json.dumps(tree))
        except Exception as e:
            print(json.dumps({"error": str(e)}))
        sys.exit(0)
    else:
        print(json.dumps({"error": "Unknown command"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
