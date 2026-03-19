#!/usr/bin/env python3
"""OBS operations wrapper (Linux side)."""
import json
import os
from typing import List
from collections import defaultdict

from obs import ObsClient



class ObsWrapper:
    def __init__(self, access_key_id=None, secret_access_key=None, server=None,
                 proxy_host=None, proxy_port=None, proxy_username=None, proxy_password=None):

        self.client = ObsClient(
            access_key_id='HPUAZFDHXXLVJG1IDV9B',
            secret_access_key='1MdmEyU9yF5boNP2gOGy4W91PXyvvwHGHnOWX3OS',
            server='obs.cn-north-4.myhuaweicloud.com',
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
                self.client = ObsClient(
                    access_key_id='HPUAZFDHXXLVJG1IDV9B',
                    secret_access_key='1MdmEyU9yF5boNP2gOGy4W91PXyvvwHGHnOWX3OS',
                    server='obs.cn-north-4.myhuaweicloud.com',
                )
            except Exception:
                pass

        if self.client is None:
            return []

        try:
            resp = self.client.listObjects(bucket, prefix=prefix)  # type: ignore
            objs = []
            body = resp['body']
            if hasattr(body, 'contents'):
                contents = body.contents
            else:
                contents = body.get('contents', []) or []
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
                    if prefix:
                        if key.startswith(prefix):
                            relative_path = key[len(prefix):]
                        else:
                            relative_path = key
                    else:
                        relative_path = key
                    
                    # 去掉开头的/
                    if relative_path.startswith('/'):
                        relative_path = relative_path[1:]
                    
                    parts = relative_path.split('/')
                    
                    # 如果parts长度为1，说明是当前目录下的文件/文件夹
                    # 如果parts长度为2且第二个为空字符串（如"folder/"），说明是文件夹
                    if len(parts) == 1 or (len(parts) == 2 and parts[1] == ''):
                        is_folder = key.endswith('/')
                        objs.append({
                            "key": key,
                            "size": size,
                            "last_modified": lm,
                            "is_folder": is_folder
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
        # 规范化prefix（空字符串不需要加/）
        if prefix and not prefix.endswith('/'):
            prefix = prefix + '/'

        all_objects = self.list_objects(bucket, prefix, only_current_level=True)
        print('list_current_level', all_objects)

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
        print('get_directory_tree', bucket, prefix)
        objs = self.list_objects(bucket, prefix)
        print(objs)
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
                    current_path = '/'.join(parts[:i + 1])
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
