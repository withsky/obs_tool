#!/usr/bin/env python3
"""OBS operations wrapper (Linux side)."""
import json
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

    def list_objects(self, bucket: str, prefix: str = "", only_current_level: bool = True) -> List[dict]:
        """
        列出OBS对象
        
        Args:
            bucket: OBS桶名
            prefix: 前缀路径
            only_current_level: 如果为True，只返回当前层级的文件和文件夹
        """
        if self.client is None:
            try:
                config_path = "/data9/obs_tool/config.json"
                if os.path.exists(config_path):
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    
                    ak = config.get('accessKeyId') or os.environ.get('OBS_ACCESS_KEY', '')
                    sk = config.get('secretAccessKey') or os.environ.get('OBS_SECRET_KEY', '')
                    server = config.get('server', 'https://obs.cn-north-4.myhuaweicloud.com')
                    
                    if ak and sk:
                        self.client = ObsClient(
                            access_key_id=ak,
                            secret_access_key=sk,
                            server=server
                        )
                    else:
                        return []
            except Exception:
                pass
        
        if self.client is None:
            return []
        
        try:
            resp = self.client.listObjects(bucket, prefix=prefix)  # type: ignore
            objs = []
            contents = getattr(resp, 'contents', []) or []
            
            for obj in contents:
                key = getattr(obj, 'key', None) or getattr(obj, 'name', None)
                size = getattr(obj, 'size', None)
                
                # 提取 last_modified
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
                
                if only_current_level:
                    # 只返回当前层级
                    # 计算相对于prefix的路径
                    relative_path = key[len(prefix):] if key.startswith(prefix) else key
                    if relative_path.startswith('/'):
                        relative_path = relative_path[1:]
                    
                    parts = relative_path.split('/')
                    
                    if len(parts) == 1:
                        # 直接在当前目录下
                        objs.append({
                            "key": key,
                            "size": size,
                            "last_modified": lm,
                            "is_folder": key.endswith('/') if len(parts) == 1 else False
                        })
                    # else: 子目录中的文件，不返回
                else:
                    # 返回所有层级（原有逻辑）
                    key_without_prefix = key[len(prefix):] if key.startswith(prefix) else key
                    if key_without_prefix.startswith('/'):
                        key_without_prefix = key_without_prefix[1:]
                    
                    parts = key_without_prefix.split('/')
                    depth = len(parts) - 1
                    
                    parent_dir = '/'.join(parts[:-1]) if depth > 0 else ""
                    
                    objs.append({
                        "key": key,
                        "size": size,
                        "last_modified": lm,
                        "depth": depth,
                        "parent_dir": parent_dir,
                        "is_in_folder": depth > 0
                    })
            
            return objs
        except Exception:
            return []
    
    def list_current_level(self, bucket: str, prefix: str = "") -> List[dict]:
        """
        只列出当前层级的文件和文件夹
        返回格式: {"folders": [...], "files": [...]}
        """
        # 规范化prefix
        if prefix and not prefix.endswith('/'):
            prefix = prefix + '/'
        
        all_objects = self.list_objects(bucket, prefix, only_current_level=True)
        
        folders = []
        files = []
        
        for obj in all_objects:
            key = obj.get('key', '')
            if key.endswith('/'):
                # 文件夹
                folder_name = key.rstrip('/').split('/')[-1]
                folders.append({
                    "key": key.rstrip('/'),
                    "name": folder_name,
                    "last_modified": obj.get('last_modified', 0)
                })
            else:
                # 文件
                file_name = key.split('/')[-1]
                files.append({
                    "key": key,
                    "name": file_name,
                    "size": obj.get('size', 0),
                    "last_modified": obj.get('last_modified', 0)
                })
        
        # 按名称排序
        folders.sort(key=lambda x: x['name'])
        files.sort(key=lambda x: x['name'])
        
        return {"folders": folders, "files": files}
    
    def get_parent_path(self, path: str) -> str:
        """获取父路径"""
        if not path:
            return ""
        parts = path.rstrip('/').split('/')
        if len(parts) == 1:
            return ""
        return '/'.join(parts[:-1])

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
