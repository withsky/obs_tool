#!/usr/bin/env python3
"""Chunk verification for resume logic."""
import os
import math
from typing import List

def scan_chunks(object_key: str, piece_size: int, local_dir: str) -> dict:
    base_name = os.path.basename(object_key.strip("/"))
    if not base_name:
        base_name = "object"
    total_size = None  # to be filled by caller if needed
    total_parts = None
    # If total_size is unknown, we can't determine part count reliably here.
    # Caller should provide total_size via task data and pass to this function if needed.
    # This function focuses on validating existing chunks.
    chunk_paths = []
    for fname in os.listdir(local_dir or "."):
        if fname.startswith(base_name) and ".part" in fname:
            try:
                idx = int(fname.split(".part")[1])
                chunk_paths.append((idx, os.path.join(local_dir, fname)))
            except Exception:
                continue
    chunk_paths.sort()
    need_download: List[int] = []
    valid_parts: List[int] = []
    if total_size is None or total_parts is None:
        # Cannot determine without total_size; return all as needed
        need_download = [idx for idx, _ in chunk_paths]
        return {"valid_parts": valid_parts, "need_download": need_download, "total_parts": len(chunk_paths)}
    for idx, p in chunk_paths:
        expected = min(piece_size, total_size - (idx - 1) * piece_size)
        if os.path.exists(p):
            if os.path.getsize(p) == expected:
                valid_parts.append(idx)
            else:
                need_download.append(idx)
        else:
            need_download.append(idx)
    return {
        "valid_parts": valid_parts,
        "need_download": need_download,
        "total_parts": total_parts if total_parts is not None else len(chunk_paths),
    }
