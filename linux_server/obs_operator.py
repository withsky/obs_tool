#!/usr/bin/env python3
"""OBS operations wrapper (Linux side)."""
import os
from typing import List
from collections import defaultdict

try:
    from obs import ObsClient
except Exception:  # pragma: no cover
    ObsClient = None  # type: ignore

class ObsWrapper:
    def __init__(self, access_key_id=None, secret_access_key=None, server=None,
                 proxy_host=None, proxy_port=None, proxy_username=None, proxy_password=None):
        if ObsClient is None:
            self.client = None
        else:
            self.client = ObsClient(
                access_key_id=access_key_id,
                secret_access_key=secret_access_key,
                server=server,
                proxy_host=proxy_host,
                proxy_port=proxy_port,
                proxy_username=proxy_username,
                proxy_password=proxy_password
            )

    def is_available(self) -> bool:
        return self.client is not None

    def get_object_size(self, bucket: str, key: str) -> int:
        if self.client is None:
            raise RuntimeError("OBS client not available")
        try:
            if hasattr(self.client, "headObject"):
                resp = self.client.headObject(bucket, key)  # type: ignore
                if hasattr(resp, 'headers') and resp.headers:
                    cl = resp.headers.get('Content-Length')
                    if cl is not None:
                        return int(cl)
        except Exception:
            pass
        # Fallback: try to fetch a small range to infer size
        try:
            headers = type('H', (), {})()
            setattr(headers, 'range', '0-0')
            resp = self.client.getObject(bucket, key, loadStreamInMemory=True, headers=headers)  # type: ignore
            if getattr(resp, 'status', 500) < 300:
                hdrs = getattr(resp, 'headers', {}) or {}
                cr = hdrs.get('Content-Range')
                if cr:
                    return int(cr.split('/')[-1])
        except Exception:
            pass
        return None  # type: ignore

    def list_objects(self, bucket: str, prefix: str = "") -> List[dict]:
        if self.client is None:
            raise RuntimeError("OBS client not available")
        try:
            resp = self.client.listObjects(bucket, prefix=prefix)  # type: ignore
            objs = []
            contents = getattr(resp, 'contents', []) or []
            for obj in contents:
                key = getattr(obj, 'key', None) or getattr(obj, 'name', None)
                size = getattr(obj, 'size', None)
                
                # Try to extract last_modified with multiple possible attribute names
                lm = None
                for attr in ('lastModified', 'LastModified', 'last_modified', 'mtime'):
                    if hasattr(obj, attr):
                        val = getattr(obj, attr)
                        if isinstance(val, (int, float)):
                            lm = int(val)
                        elif isinstance(val, str):
                            try:
                                from datetime import datetime
                                lm = int(datetime.fromisoformat(val).timestamp())
                            except Exception:
                                lm = None
                        break
                if lm is None:
                    lm = 0
                
                # 计算目录结构信息
                depth = 0
                parent_dir = ""
                is_in_folder = False
                
                if key:
                    # 计算层级深度
                    key_without_prefix = key[len(prefix):] if key.startswith(prefix) else key
                    if key_without_prefix.startswith('/'):
                        key_without_prefix = key_without_prefix[1:]
                    
                    parts = key_without_prefix.split('/')
                    depth = len(parts) - 1  # 减1是因为最后一个是文件名
                    
                    if depth > 0:
                        is_in_folder = True
                        parent_dir = '/'.join(parts[:-1])
                    else:
                        is_in_folder = False
                        parent_dir = ""
                
                objs.append({
                    "key": key, 
                    "size": size, 
                    "last_modified": lm,
                    "depth": depth,
                    "parent_dir": parent_dir,
                    "is_in_folder": is_in_folder
                })
            return objs
        except Exception:
            return []

    def get_directory_tree(self, bucket: str, prefix: str = "") -> dict:
        """获取目录树结构，便于Windows端展示"""
        objs = self.list_objects(bucket, prefix)
        
        # 构建目录树
        tree = defaultdict(lambda: {"files": [], "subdirs": set()})
        root_files = []
        
        for obj in objs:
            key = obj.get("key", "")
            parent_dir = obj.get("parent_dir", "")
            
            if parent_dir:
                # 这个文件在某个目录下
                tree[parent_dir]["files"].append(obj)
                
                # 构建父目录层级关系
                parts = parent_dir.split('/')
                for i in range(len(parts)):
                    current_path = '/'.join(parts[:i+1])
                    if i > 0:
                        parent_path = '/'.join(parts[:i])
                        tree[parent_path]["subdirs"].add(current_path)
                    else:
                        tree[""]["subdirs"].add(current_path)
            else:
                # 根目录下的文件
                root_files.append(obj)
        
        tree[""]["files"] = root_files
        
        # 转换set为list以便JSON序列化
        for dir_path in tree:
            tree[dir_path]["subdirs"] = sorted(list(tree[dir_path]["subdirs"]))
        
        return dict(tree)

    def download_range(self, bucket: str, key: str, start: int, end: int) -> bytes:
        if self.client is None:
            raise RuntimeError("OBS client not available")
        headers = type('H', (), {})()
        setattr(headers, 'range', f"{start}-{end}")
        resp = self.client.getObject(bucket, key, loadStreamInMemory=True, headers=headers)  # type: ignore
        if getattr(resp, 'status', 500) >= 300:
            raise RuntimeError(f"HTTP error {getattr(resp, 'status', 500)} for range {start}-{end}")
        data = getattr(resp, 'body', None)
        if data and hasattr(data, 'buffer'):
            return data.buffer
        return b""
