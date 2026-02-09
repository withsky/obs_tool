#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
obs_chunk_downloader.py
A self-contained Linux-friendly OBS chunk-downloader with resume, retry/backoff,
heartbeat progress, and final file assembly.

Design goals:
- Download a target object in 4MB chunks (configurable) from Huawei OBS.
- Each chunk is saved as <objectKey basename>.part{index} in a local directory.
- Support resuming: if a chunk file already exists, reuse it and skip re-download.
- Robust retry with exponential backoff and jitter on transient errors.
- Periodic heartbeat / progress output to keep users informed.
- After all chunks are downloaded, merge them in order into the final file
  named after the object basename, and clean up the temporary chunk files.
- Configuration lives in a root-level config.json for easy reuse; the script
  optionally accepts an OBS_DL_CONFIG env var to override the path.

Notes:
- Requires Huawei OBS Python SDK (obs-python-sdk). Install via:
  pip install obs-python-sdk
- The script uses range requests (GET with Range header) to fetch chunks.
- Proxy and authentication/region details are configurable.
- This module is designed to be simple and script-friendly for automation.
"""

import os
import sys
import json
import math
import time
import threading
import traceback
import random

try:
    from obs import ObsClient, GetObjectHeader
except Exception:  # pragma: no cover
    # Import error handling: allow the script to be imported for tooling or tests
    ObsClient = None  # type: ignore
    GetObjectHeader = object  # type: ignore


CONFIG_FILE_DEFAULT = "./config.json"


def load_config(path: str) -> dict:
    """Load JSON config from path."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dir(path: str) -> None:
    """Ensure directory exists."""
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


class Heartbeat(threading.Thread):
    """Background thread that periodically prints download progress."""

    def __init__(self, total_size: int, local_dir: str, base_name: str, piece_size: int, interval_sec: float = 30.0):
        super().__init__(daemon=True)
        self.total_size = total_size
        self.local_dir = local_dir
        self.base_name = base_name
        self.piece_size = piece_size
        self.interval = max(1.0, float(interval_sec))
        self._stop = threading.Event()
        self._start_time = time.time()

    def stop(self):
        self._stop.set()
        self.join()

    def get_downloaded_bytes(self) -> int:
        """Compute total downloaded bytes by summing existing chunk files."""
        total_parts = (self.total_size + self.piece_size - 1) // self.piece_size
        downloaded = 0
        for idx in range(1, int(total_parts) + 1):
            part_path = os.path.join(self.local_dir, f"{self.base_name}.part{idx}")
            if os.path.exists(part_path):
                downloaded += os.path.getsize(part_path)
        return downloaded

    def run(self):
        while not self._stop.is_set():
            downloaded = self.get_downloaded_bytes()
            elapsed = time.time() - self._start_time
            speed = downloaded / elapsed if elapsed > 0 else 0
            remaining = max(self.total_size - downloaded, 0)
            eta = (remaining / speed) if speed > 0 else None
            eta_str = time.strftime("%H:%M:%S", time.gmtime(eta)) if eta is not None else "Unknown"
            print(f"[Heartbeat] {downloaded}/{self.total_size} bytes | speed {speed:.2f} B/s | ETA {eta_str}")
            time.sleep(self.interval)


def get_total_size(obs_client, bucket, key):
    """Attempt to determine object size via HEAD; fall back to Content-Range parsing."""
    # Best effort: use headObject if available
    try:
        if hasattr(obs_client, "headObject"):
            resp = obs_client.headObject(bucket, key)  # type: ignore[attr-defined]
            if hasattr(resp, "headers") and resp.headers:
                cl = resp.headers.get("Content-Length")
                if cl is not None:
                    return int(cl)
    except Exception:
        pass

    # Fallback: request a tiny range and read Content-Range
    try:
        headers = GetObjectHeader()
        if hasattr(headers, 'range'):
            headers.range = '0-0'
        resp = obs_client.getObject(bucket, key, loadStreamInMemory=True, headers=headers)  # type: ignore[arg-type]
        if getattr(resp, "status", 500) < 300:
            hdrs = getattr(resp, "headers", {}) or {}
            cr = hdrs.get("Content-Range")
            if cr:
                return int(cr.split('/')[-1])
            if hasattr(resp, "body") and getattr(resp.body, "buffer", None):
                return len(resp.body.buffer)
    except Exception:
        pass

    return None


def download_range(obs_client, bucket, key, start, end, part_path):
    """Download a single byte range [start, end] and write to part_path. Returns bytes written."""
    headers = GetObjectHeader()
    if hasattr(headers, 'range'):
        headers.range = f"{start}-{end}"
    resp = obs_client.getObject(bucket, key, loadStreamInMemory=True, headers=headers)  # type: ignore[arg-type]
    if getattr(resp, "status", 500) >= 300:
        msg = getattr(resp, "errorMessage", "") or "Unknown error"
        raise RuntimeError(f"HTTP {resp.status} error for range {start}-{end}: {msg}")
    data = resp.body.buffer if hasattr(resp, "body") and resp.body and hasattr(resp.body, "buffer") else b""
    with open(part_path, "wb") as f:
        f.write(data)
    return len(data)


def main():
    # 1) 读取配置：优先从环境变量 OBS_DL_CONFIG 指定的路径，其次使用默认配置文件
    cfg_path = os.environ.get("OBS_DL_CONFIG", CONFIG_FILE_DEFAULT)
    if not os.path.exists(cfg_path):
        print(f"Config file not found: {cfg_path}")
        print("Please provide a valid config.json with required fields.")
        sys.exit(1)

    cfg = load_config(cfg_path)

    # 2) 基本参数与默认值
    bucket = cfg.get("bucketName", "tfds-ht")
    objectKey = cfg.get("objectKey")
    if not objectKey:
        print("Configuration error: 'objectKey' must be specified in config.json")
        sys.exit(1)
    localDir = cfg.get("localDir", "./obs_downloads")
    pieceSize = int(cfg.get("pieceSize", 4 * 1024 * 1024))  # 4MB by default
    maxRetries = int(cfg.get("maxRetries", 6))
    backoffBase = float(cfg.get("backoffBaseSec", 2.0))
    heartbeatInterval = float(cfg.get("heartbeatIntervalSec", 30.0))
    server = cfg.get("server", "https://obs.cn-north-4.myhuaweicloud.com")

    proxy = cfg.get("proxy", {})
    ak = cfg.get("accessKeyId") or os.environ.get("OBS_ACCESS_KEY")
    sk = cfg.get("secretAccessKey") or os.environ.get("OBS_SECRET_KEY")

    proxy_host = proxy.get("host") or None
    proxy_port = proxy.get("port")
    proxy_username = proxy.get("username") or None
    proxy_password = proxy.get("password") or None

    ensure_dir(localDir)

    # 3) 初始化 ObsClient（需要 obs-python-sdk）
    if ObsClient is None:
        print("OBS SDK not available. Install via: pip install obs-python-sdk")
        sys.exit(1)
    try:
        obsClient = ObsClient(
            access_key_id=ak,
            secret_access_key=sk,
            server=server,
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            proxy_username=proxy_username,
            proxy_password=proxy_password
        )
    except Exception as e:  # pragma: no cover
        print("Failed to initialize ObsClient:", e)
        traceback.print_exc()
        sys.exit(1)

    # 4) 计算对象总大小
    total_size = get_total_size(obsClient, bucket, objectKey)
    if total_size is None:
        print("Could not determine object size. Aborting.")
        sys.exit(1)
    print(f"Total size: {total_size} bytes")

    # 5) 目标分片命名、分片数量、已存在分片检查
    base_name = os.path.basename(objectKey.strip("/"))
    if not base_name:
        base_name = "object"
    total_parts = (total_size + pieceSize - 1) // pieceSize
    part_paths = [os.path.join(localDir, f"{base_name}.part{idx}") for idx in range(1, total_parts + 1)]

    # 6) 计算从哪一段开始下载（若分片已存在则跳过）
    start_index = 1
    for idx, p in enumerate(part_paths, start=1):
        if not os.path.exists(p):
            start_index = idx
            break
    else:
        start_index = total_parts + 1  # 所有分片已存在

    hb = Heartbeat(total_size, localDir, base_name, pieceSize, heartbeatInterval)
    hb.start()

    final_path = os.path.join(localDir, base_name)

    try:
        downloaded_so_far = 0
        for idx in range(1, start_index):
            p = part_paths[idx - 1]
            if os.path.exists(p):
                downloaded_so_far += os.path.getsize(p)

        # 逐分片下载，带重试和退避
        for idx in range(start_index, total_parts + 1):
            start = (idx - 1) * pieceSize
            end = min(start + pieceSize - 1, total_size - 1)
            part_path = part_paths[idx - 1]

            attempt = 0
            while True:
                attempt += 1
                try:
                    print(f"Downloading part {idx}/{total_parts} (range {start}-{end})")
                    downloaded = download_range(obsClient, bucket, objectKey, start, end, part_path)
                    expected = end - start + 1
                    if downloaded != expected:
                        raise RuntimeError(f"Downloaded {downloaded} bytes, expected {expected} bytes")
                    downloaded_so_far += downloaded
                    break
                except Exception as e:
                    if attempt >= maxRetries:
                        print(f"Part {idx} failed after {attempt} attempts: {e}")
                        raise
                    backoff = backoffBase * (2 ** (attempt - 1))
                    jitter = random.uniform(0.5, 1.5)
                    wait = max(0.5, backoff * jitter)
                    print(f"Part {idx} failed: {e}. Retry {attempt}/{maxRetries} after {wait:.1f}s")
                    time.sleep(wait)

        # 7) 合并分片为最终文件
        with open(final_path, "wb") as fout:
            for i in range(1, total_parts + 1):
                p = os.path.join(localDir, f"{base_name}.part{i}")
                with open(p, "rb") as fin:
                    fout.write(fin.read())
        print(f"Download completed. Final file: {final_path}")

        # 8) 清理分片文件（可选）
        for p in part_paths:
            if os.path.exists(p):
                os.remove(p)
        print("Temporary parts cleaned up.")

    except KeyboardInterrupt:
        print("Download interrupted by user.")
    except Exception as e:
        print("Download failed:", e)
        traceback.print_exc()
    finally:
        hb.stop()


if __name__ == "__main__":  # pragma: no cover
    main()
