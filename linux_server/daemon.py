#!/usr/bin/env python3
"""
OBS下载守护进程 - 带并发控制和数据一致性保护

特性：
- 最大并发数限制（默认5个）
- 跨用户写锁保护
- 任务队列管理
- 心跳监控
- 信号处理支持systemd
"""
import json
import os
import time
import threading
import fcntl
import signal
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional
from datetime import datetime
import traceback

# 配置
CONFIG_PATH = "/data9/obs_tool/config.json"
STORAGE_DIR = "/data9/obs_tool/storage"
LOCK_FILE = os.path.join(STORAGE_DIR, ".daemon.lock")
TASKS_FILE = os.path.join(STORAGE_DIR, "tasks_db.json")
LOG_FILE = "/data9/obs_tool/logs/daemon.log"
MAX_CONCURRENCY = 5

class WriteLock:
    """跨进程写锁 - 使用文件锁实现"""
    def __init__(self, lock_path: str):
        self.lock_path = lock_path
        self.lock_fd = None
    
    def acquire(self, blocking: bool = True) -> bool:
        """获取锁"""
        try:
            self.lock_fd = open(self.lock_path, 'w')
            if blocking:
                fcntl.flock(self.lock_fd, fcntl.LOCK_EX)
            else:
                fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except IOError:
            if self.lock_fd:
                self.lock_fd.close()
                self.lock_fd = None
            return False
    
    def release(self):
        """释放锁"""
        if self.lock_fd:
            fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
            self.lock_fd.close()
            self.lock_fd = None
    
    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

class DatabaseManager:
    """数据库管理器 - 带写锁保护，确保多进程/多线程安全"""
    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self.tasks_file = os.path.join(storage_dir, "tasks_db.json")
        self.history_file = os.path.join(storage_dir, "history.json")
        self.favorites_file = os.path.join(storage_dir, "favorites.json")
        self.lock = WriteLock(os.path.join(storage_dir, ".db.lock"))
        
        # 确保目录存在
        os.makedirs(storage_dir, exist_ok=True)
    
    def _read_json(self, filepath: str, default=None):
        """读取JSON文件"""
        if default is None:
            default = {}
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            log(f"读取文件失败 {filepath}: {e}")
        return default
    
    def _write_json(self, filepath: str, data):
        """写入JSON文件（带锁和原子操作）"""
        try:
            # 先写入临时文件
            temp_file = filepath + '.tmp'
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            
            # 原子重命名
            os.rename(temp_file, filepath)
            return True
        except Exception as e:
            log(f"写入文件失败 {filepath}: {e}")
            return False
    
    def get_tasks(self) -> Dict:
        """获取所有任务（读取操作不需要锁，但建议使用锁保持一致性）"""
        return self._read_json(self.tasks_file, {})
    
    def update_task(self, task_id: str, updates: Dict) -> bool:
        """更新任务（带写锁保护）"""
        with self.lock:
            try:
                tasks = self.get_tasks()
                if task_id not in tasks:
                    log(f"任务 {task_id} 不存在")
                    return False
                
                tasks[task_id].update(updates)
                tasks[task_id]['updated_at'] = int(time.time())
                
                if self._write_json(self.tasks_file, tasks):
                    log(f"任务 {task_id} 已更新: {updates.get('status', 'unknown')}")
                    return True
                return False
            except Exception as e:
                log(f"更新任务 {task_id} 失败: {e}")
                return False
    
    def add_task(self, task_id: str, data: Dict) -> bool:
        """添加任务（带写锁保护）"""
        with self.lock:
            try:
                tasks = self.get_tasks()
                tasks[task_id] = data
                
                if self._write_json(self.tasks_file, tasks):
                    log(f"任务 {task_id} 已添加")
                    return True
                return False
            except Exception as e:
                log(f"添加任务 {task_id} 失败: {e}")
                return False
    
    def delete_task(self, task_id: str) -> bool:
        """删除任务（带写锁保护）"""
        with self.lock:
            try:
                tasks = self.get_tasks()
                if task_id in tasks:
                    del tasks[task_id]
                    if self._write_json(self.tasks_file, tasks):
                        log(f"任务 {task_id} 已删除")
                        return True
                return False
            except Exception as e:
                log(f"删除任务 {task_id} 失败: {e}")
                return False
    
    def add_history(self, entry: Dict) -> bool:
        """添加历史记录（带写锁保护）"""
        with self.lock:
            try:
                history = self._read_json(self.history_file, [])
                entry['completed_at'] = int(time.time())
                history.append(entry)
                
                # 只保留最近100条
                if len(history) > 100:
                    history = history[-100:]
                
                return self._write_json(self.history_file, history)
            except Exception as e:
                log(f"添加历史记录失败: {e}")
                return False

class TaskExecutor:
    """任务执行器 - 管理并发执行"""
    def __init__(self, db_manager: DatabaseManager, max_workers: int = 5):
        self.db = db_manager
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.running_tasks = {}  # task_id -> future
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
    
    def submit_task(self, task_id: str, task_data: Dict) -> bool:
        """提交任务到线程池"""
        with self._lock:
            # 检查并发数
            if len(self.running_tasks) >= self.max_workers:
                log(f"并发数已达上限 {self.max_workers}，任务 {task_id} 等待中")
                return False
            
            # 检查任务是否已在运行
            if task_id in self.running_tasks:
                log(f"任务 {task_id} 已在运行中")
                return False
            
            # 提交任务
            future = self.executor.submit(self._execute_task_wrapper, task_id, task_data)
            self.running_tasks[task_id] = {
                'future': future,
                'start_time': time.time()
            }
            
            log(f"任务 {task_id} 已提交，当前运行: {len(self.running_tasks)}/{self.max_workers}")
            return True
    
    def _execute_task_wrapper(self, task_id: str, task_data: Dict):
        """任务执行包装器（处理异常和清理）"""
        try:
            self._execute_task(task_id, task_data)
        except Exception as e:
            log(f"任务 {task_id} 执行异常: {e}")
            log(traceback.format_exc())
            self.db.update_task(task_id, {
                'status': 'failed',
                'error': str(e),
                'failed_at': int(time.time())
            })
        finally:
            with self._lock:
                if task_id in self.running_tasks:
                    del self.running_tasks[task_id]
    
    def _execute_task(self, task_id: str, task_data: Dict):
        """实际执行OBS下载任务"""
        import random
        
        object_key = task_data.get('object_key')
        bucket = task_data.get('bucket', 'tfds-ht')
        target_dir = task_data.get('target_dir', '/railway-efs/000-tfds/')
        piece_size = task_data.get('piece_size', 4 * 1024 * 1024)
        max_retries = task_data.get('maxRetries', 6)
        backoff_base = task_data.get('backoffBaseSec', 2.0)
        
        log(f"任务 {task_id} 开始下载: {object_key}")
        
        # 加载OBS配置
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    obs_config = json.load(f)
                ak = obs_config.get('accessKeyId') or os.environ.get('OBS_ACCESS_KEY')
                sk = obs_config.get('secretAccessKey') or os.environ.get('OBS_SECRET_KEY')
                server = obs_config.get('server', 'https://obs.cn-north-4.myhuaweicloud.com')
            else:
                ak = os.environ.get('OBS_ACCESS_KEY', '')
                sk = os.environ.get('OBS_SECRET_KEY', '')
                server = os.environ.get('OBS_SERVER', 'https://obs.cn-north-4.myhuaweicloud.com')
        except Exception as e:
            log(f"任务 {task_id} 加载配置失败: {e}")
            self.db.update_task(task_id, {'status': 'failed', 'error': str(e)})
            return
        
        # 初始化OBS客户端
        try:
            from obs import ObsClient, GetObjectHeader
            obs_client = ObsClient(
                access_key_id=ak,
                secret_access_key=sk,
                server=server
            )
        except Exception as e:
            log(f"任务 {task_id} OBS客户端初始化失败: {e}")
            self.db.update_task(task_id, {'status': 'failed', 'error': f"OBS SDK不可用: {e}"})
            return
        
        # 更新状态为运行中
        self.db.update_task(task_id, {
            'status': 'running',
            'started_at': int(time.time())
        })
        
        # 确保目标目录存在
        os.makedirs(target_dir, exist_ok=True)
        
        # 获取文件总大小
        if task_data.get('total_size', 0) == 0:
            # 尝试获取文件大小
            try:
                resp = obs_client.headObject(bucket, object_key)
                if hasattr(resp, 'headers') and resp.headers:
                    total_size = int(resp.headers.get('Content-Length', 0))
                else:
                    total_size = 0
            except Exception:
                total_size = 0
        else:
            total_size = task_data.get('total_size', 0)
        
        if total_size == 0:
            log(f"任务 {task_id} 无法获取文件大小")
            self.db.update_task(task_id, {'status': 'failed', 'error': '无法获取文件大小'})
            return
        
        log(f"任务 {task_id} 文件大小: {total_size} bytes")
        
        # 计算分片信息
        chunks = (total_size + piece_size - 1) // piece_size
        base_name = os.path.basename(object_key)
        chunks_dir = os.path.join(target_dir, f".{task_id}_chunks")
        os.makedirs(chunks_dir, exist_ok=True)
        
        # 扫描已存在的分片（断点续传）
        valid_parts = []
        need_download = []
        
        for i in range(1, chunks + 1):
            part_path = os.path.join(chunks_dir, f"{base_name}.part{i}")
            expected_size = min(piece_size, total_size - (i - 1) * piece_size)
            
            if os.path.exists(part_path):
                actual_size = os.path.getsize(part_path)
                if actual_size == expected_size:
                    valid_parts.append(i)
                else:
                    # 分片损坏，删除后重新下载
                    try:
                        os.remove(part_path)
                        log(f"任务 {task_id} 分片 {i} 大小不符，已删除")
                    except:
                        pass
                    need_download.append(i)
            else:
                need_download.append(i)
        
        log(f"任务 {task_id} 已完成 {len(valid_parts)}/{chunks} 个分片")
        
        # 逐分片下载
        downloaded = sum(
            min(piece_size, total_size - (p - 1) * piece_size)
            for p in valid_parts
        )
        
        for i in need_download:
            # 检查是否被取消
            if self._stop_event.is_set():
                log(f"任务 {task_id} 被中断")
                self.db.update_task(task_id, {'status': 'cancelled'})
                return
            
            # 检查任务状态（可能被外部暂停或取消）
            current_task = self.db.get_tasks().get(task_id, {})
            if current_task.get('status') == 'cancelled':
                log(f"任务 {task_id} 已被取消")
                return
            
            if current_task.get('status') == 'paused':
                log(f"任务 {task_id} 已暂停，等待恢复...")
                while not self._stop_event.is_set():
                    time.sleep(1)
                    current_task = self.db.get_tasks().get(task_id, {})
                    if current_task.get('status') != 'paused':
                        break
            
            # 下载分片
            start = (i - 1) * piece_size
            end = min(start + piece_size - 1, total_size - 1)
            part_path = os.path.join(chunks_dir, f"{base_name}.part{i}")
            
            attempt = 0
            success = False
            
            while attempt < max_retries and not success:
                attempt += 1
                try:
                    headers = GetObjectHeader()
                    headers.range = f"{start}-{end}"
                    
                    resp = obs_client.getObject(bucket, object_key, 
                                               loadStreamInMemory=True, 
                                               headers=headers)
                    
                    if getattr(resp, 'status', 500) >= 300:
                        raise RuntimeError(f"HTTP {getattr(resp, 'status', 500)}")
                    
                    data = getattr(resp, 'body', None)
                    if data and hasattr(data, 'buffer'):
                        data = data.buffer
                    else:
                        data = b''
                    
                    with open(part_path, 'wb') as f:
                        f.write(data)
                    
                    # 验证分片大小
                    actual_size = os.path.getsize(part_path)
                    expected = end - start + 1
                    if actual_size != expected:
                        raise RuntimeError(f"分片大小不匹配: {actual_size} != {expected}")
                    
                    success = True
                    
                except Exception as e:
                    if attempt >= max_retries:
                        log(f"任务 {task_id} 分片 {i} 下载失败，已重试 {attempt} 次: {e}")
                        self.db.update_task(task_id, {
                            'status': 'failed',
                            'error': f"分片 {i} 下载失败: {e}"
                        })
                        return
                    
                    # 指数退避
                    backoff = backoff_base * (2 ** (attempt - 1))
                    jitter = random.uniform(0.5, 1.5)
                    wait = max(0.5, backoff * jitter)
                    
                    log(f"任务 {task_id} 分片 {i} 重试 {attempt}/{max_retries}，等待 {wait:.1f}s")
                    time.sleep(wait)
            
            # 更新进度
            downloaded += (end - start + 1)
            progress = int(downloaded * 100 / total_size)
            
            self.db.update_task(task_id, {
                'progress': {
                    'downloaded': downloaded,
                    'total': total_size,
                    'percentage': progress
                }
            })
            
            log(f"任务 {task_id} 进度: {progress}%")
        
        # 心跳监控：定期打印状态
        if progress % 10 == 0 or progress == 100:
            speed = 0
            elapsed = time.time() - task_data.get('started_at', time.time())
            if elapsed > 0 and downloaded > 0:
                speed = downloaded / elapsed
            log(f"[Heartbeat] 任务 {task_id}: {downloaded}/{total_size} bytes | speed {speed:.2f} B/s")
        
        # 合并分片文件
        log(f"任务 {task_id} 正在合并分片...")
        final_path = os.path.join(target_dir, base_name)
        
        try:
            with open(final_path, 'wb') as fout:
                for i in range(1, chunks + 1):
                    part_path = os.path.join(chunks_dir, f"{base_name}.part{i}")
                    if os.path.exists(part_path):
                        with open(part_path, 'rb') as fin:
                            fout.write(fin.read())
                        # 删除分片文件
                        try:
                            os.remove(part_path)
                        except:
                            pass
                    else:
                        raise RuntimeError(f"分片 {i} 不存在")
            
            # 删除分片目录
            try:
                os.rmdir(chunks_dir)
            except:
                pass
            
            log(f"任务 {task_id} 分片合并完成: {final_path}")
            
        except Exception as e:
            log(f"任务 {task_id} 分片合并失败: {e}")
            self.db.update_task(task_id, {
                'status': 'failed',
                'error': f"分片合并失败: {e}"
            })
            return
        
        # 任务完成
        self.db.update_task(task_id, {
            'status': 'completed',
            'completed_at': int(time.time()),
            'progress': {
                'downloaded': total_size,
                'total': total_size,
                'percentage': 100
            }
        })
        
        # 添加到历史记录
        self.db.add_history({
            'task_id': task_id,
            'object_key': object_key,
            'final_path': os.path.join(
                target_dir,
                os.path.basename(object_key)
            ),
            'size': total_size,
            'created_by': task_data.get('created_by', 'unknown')
        })
        
        log(f"任务 {task_id} 完成")
    
    def pause_task(self, task_id: str) -> bool:
        """暂停任务"""
        return self.db.update_task(task_id, {'status': 'paused'})
    
    def resume_task(self, task_id: str) -> bool:
        """恢复任务"""
        task = self.db.get_tasks().get(task_id)
        if not task:
            return False
        
        if task.get('status') == 'paused':
            # 检查是否已在运行
            with self._lock:
                if task_id in self.running_tasks:
                    log(f"任务 {task_id} 已在运行中")
                    return True
            
            # 重新提交
            return self.submit_task(task_id, task)
        
        return False
    
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        with self._lock:
            if task_id in self.running_tasks:
                # 取消正在运行的任务
                task_info = self.running_tasks[task_id]
                task_info['future'].cancel()
                del self.running_tasks[task_id]
        
        return self.db.update_task(task_id, {'status': 'cancelled'})
    
    def get_running_count(self) -> int:
        """获取正在运行的任务数"""
        with self._lock:
            return len(self.running_tasks)
    
    def cleanup(self):
        """清理资源"""
        log("正在停止任务执行器...")
        self._stop_event.set()
        
        # 取消所有正在运行的任务
        with self._lock:
            for task_id, task_info in list(self.running_tasks.items()):
                task_info['future'].cancel()
                self.db.update_task(task_id, {
                    'status': 'cancelled',
                    'cancelled_at': int(time.time())
                })
            self.running_tasks.clear()
        
        # 关闭线程池
        self.executor.shutdown(wait=False)
        log("任务执行器已停止")

class DownloadDaemon:
    """下载守护进程主类"""
    def __init__(self):
        self.db = DatabaseManager(STORAGE_DIR)
        self.executor = TaskExecutor(self.db, max_workers=MAX_CONCURRENCY)
        self.running = True
        self.daemon_lock = WriteLock(LOCK_FILE)
        
        # 确保只有一个实例在运行
        if not self.daemon_lock.acquire(blocking=False):
            raise RuntimeError("守护进程已经在运行中！")
        
        # 设置信号处理
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGHUP, self.handle_signal)
    
    def handle_signal(self, signum, frame):
        """处理系统信号"""
        sig_name = {
            signal.SIGTERM: 'SIGTERM',
            signal.SIGINT: 'SIGINT',
            signal.SIGHUP: 'SIGHUP'
        }.get(signum, str(signum))
        
        log(f"接收到信号 {sig_name}，正在关闭...")
        self.running = False
    
    def process_pending_tasks(self):
        """处理待处理的任务队列"""
        try:
            tasks = self.db.get_tasks()
            
            # 统计各状态任务数
            status_count = {}
            for task in tasks.values():
                status = task.get('status', 'unknown')
                status_count[status] = status_count.get(status, 0) + 1
            
            if status_count:
                log(f"任务统计 - 运行中: {status_count.get('running', 0)}, "
                    f"待处理: {status_count.get('pending', 0)}, "
                    f"暂停: {status_count.get('paused', 0)}")
            
            # 计算可用槽位
            running_count = self.executor.get_running_count()
            available_slots = MAX_CONCURRENCY - running_count
            
            if available_slots <= 0:
                return
            
            # 获取待处理任务
            pending_tasks = [
                (tid, task) for tid, task in tasks.items()
                if task.get('status') == 'pending'
            ]
            
            # 按创建时间排序（先进先出）
            pending_tasks.sort(key=lambda x: x[1].get('created_at', 0))
            
            # 提交任务
            submitted = 0
            for task_id, task_data in pending_tasks[:available_slots]:
                if self.executor.submit_task(task_id, task_data):
                    submitted += 1
                else:
                    break
            
            if submitted > 0:
                log(f"已提交 {submitted} 个新任务")
                    
        except Exception as e:
            log(f"处理任务队列失败: {e}")
            log(traceback.format_exc())
    
    def run(self):
        """主循环"""
        log("=" * 60)
        log("OBS下载守护进程启动")
        log(f"最大并发数: {MAX_CONCURRENCY}")
        log(f"存储目录: {STORAGE_DIR}")
        log(f"PID: {os.getpid()}")
        log("=" * 60)
        
        loop_count = 0
        while self.running:
            try:
                loop_count += 1
                
                # 处理任务队列
                self.process_pending_tasks()
                
                # 定期清理已完成的任务（每30个循环）
                if loop_count % 30 == 0:
                    self.cleanup_completed_tasks()
                
                # 等待
                time.sleep(2)
                
            except Exception as e:
                log(f"主循环异常: {e}")
                log(traceback.format_exc())
                time.sleep(5)
        
        # 清理
        log("正在关闭守护进程...")
        self.executor.cleanup()
        self.daemon_lock.release()
        log("守护进程已安全关闭")
    
    def cleanup_completed_tasks(self):
        """清理已完成/取消的任务（保留7天）"""
        try:
            tasks = self.db.get_tasks()
            current_time = int(time.time())
            to_delete = []
            
            for task_id, task in tasks.items():
                status = task.get('status')
                if status in ('completed', 'cancelled', 'failed'):
                    # 获取完成时间
                    completed_at = task.get('completed_at', 0)
                    failed_at = task.get('failed_at', 0)
                    updated_at = task.get('updated_at', 0)
                    last_time = max(completed_at, failed_at, updated_at)
                    
                    # 7天前完成的任务删除
                    if current_time - last_time > 7 * 24 * 3600:
                        to_delete.append(task_id)
            
            for task_id in to_delete:
                self.db.delete_task(task_id)
            
            if to_delete:
                log(f"清理了 {len(to_delete)} 个过期任务")
                
        except Exception as e:
            log(f"清理任务失败: {e}")

def log(message: str):
    """写日志到文件和stdout"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_line = f"[{timestamp}] {message}"
    
    print(log_line)
    sys.stdout.flush()
    
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_line + '\n')
    except:
        pass

def main():
    """入口函数"""
    try:
        daemon = DownloadDaemon()
        daemon.run()
    except RuntimeError as e:
        log(f"启动失败: {e}")
        sys.exit(1)
    except Exception as e:
        log(f"守护进程异常: {e}")
        log(traceback.format_exc())
        sys.exit(1)

if __name__ == '__main__':
    main()
