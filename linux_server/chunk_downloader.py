#!/usr/bin/env python3
"""Linux side chunk downloader (wrapper around OBS)."""
from typing import Tuple
import os

def download_and_merge(obs_client, bucket: str, key: str, local_dir: str, piece_size: int, total_size: int, start_part: int, end_part: int, part_filename_prefix: str = None) -> Tuple[int, int]:
    """Download a range of chunks and append to local chunk files. Returns (downloaded_bytes, total_bytes).
    This is a simplified wrapper; in real usage it will call obs_client.getObject with Range headers.
    """
    if part_filename_prefix is None:
        base_name = os.path.basename(key.strip("/")) or "object"
    else:
        base_name = part_filename_prefix
    downloaded = 0
    for idx in range(start_part, end_part + 1):
        start = (idx - 1) * piece_size
        end = min(start + piece_size - 1, total_size - 1)
        part_path = os.path.join(local_dir, f"{base_name}.part{idx}")
        # If piece already exists and size correct, skip
        expected = min(piece_size, total_size - (idx - 1) * piece_size)
        if os.path.exists(part_path) and os.path.getsize(part_path) == expected:
            downloaded += expected
            continue
        # Here we should call OBS to download the range. For placeholder, create empty or dummy data
        # For real usage, replace with obs_client.download_range(bucket, key, start, end) etc.
        dummy = b"0" * int(expected)
        with open(part_path, "wb") as f:
            f.write(dummy)
        downloaded += len(dummy)
    return downloaded, total_size
