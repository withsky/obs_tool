#!/usr/bin/env python3
"""
Windows客户端 - OBS下载工具
现代化的网盘风格界面，参考百度网盘、阿里云盘等设计
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from tkinter.font import Font
import json
from datetime import datetime
import threading
import paramiko
import time
import os
from typing import List, Dict, Any, Optional
from PIL import Image, ImageTk
import io
import base64

# 嵌入的图标数据（简化版emoji转图片）
ICONS = {
    'folder': '📁',
    'folder_open': '📂', 
    'file': '📄',
    'image': '🖼️',
    'video': '🎬',
    'audio': '🎵',
    'zip': '📦',
    'doc': '📝',
    'excel': '📊',
    'pdf': '📕',
    'code': '💻',
    'unknown': '📎'
}

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "settings.json")

def load_config():
    """加载本地配置"""
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"加载配置失败: {e}")
    
    # 默认配置
    return {
        "ssh_host": "10.155.106.228",
        "ssh_user": "dl",
        "ssh_password": "tfds#2025",
        "linux_path": "/data9/obs_tool/linux_server",
        "download_path": "/railway-efs/000-tfds/"
    }

def save_config(config):
    """保存配置"""
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"保存配置失败: {e}")

class SSHClient:
    """SSH客户端封装 - 带连接池"""
    _instance = None
    _client = None
    _lock = threading.Lock()
    
    def __new__(cls, host=None, user=None, password=None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance.host = host
                    cls._instance.user = user
                    cls._instance.password = password
        return cls._instance
    
    def connect(self):
        """建立连接"""
        if self._client is None:
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._client.connect(
                self.host, 
                username=self.user, 
                password=self.password, 
                timeout=10,
                compress=True
            )
    
    def exec(self, cmd, timeout=30):
        """执行命令"""
        with self._lock:
            try:
                if self._client is None:
                    self.connect()
                
                # 设置超时
                self._client.get_transport().set_keepalive(30)
                
                stdin, stdout, stderr = self._client.exec_command(cmd, timeout=timeout)
                out = stdout.read().decode('utf-8', errors='ignore')
                err = stderr.read().decode('utf-8', errors='ignore')
                
                # 检查连接是否还活跃
                if not self._client.get_transport().is_active():
                    self._client = None
                    
                return out, err
            except Exception as e:
                # 连接失败时重置
                self._client = None
                raise e
    
    def close(self):
        """关闭连接"""
        with self._lock:
            if self._client:
                self._client.close()
                self._client = None

class ModernButton(ttk.Button):
    """现代化按钮样式"""
    def __init__(self, master=None, **kw):
        # 设置样式
        style = ttk.Style()
        style.configure('Modern.TButton', 
                       font=('微软雅黑', 10),
                       padding=8)
        
        super().__init__(master, style='Modern.TButton', **kw)

class IconButton(tk.Button):
    """带图标的按钮"""
    def __init__(self, master=None, icon='', text='', command=None, **kw):
        super().__init__(master, text=f"{icon} {text}", 
                        font=('微软雅黑', 10),
                        bg='#1890ff',
                        fg='white',
                        activebackground='#40a9ff',
                        activeforeground='white',
                        relief='flat',
                        cursor='hand2',
                        command=command,
                        padx=15,
                        pady=5,
                        **kw)
        self.bind('<Enter>', self.on_enter)
        self.bind('<Leave>', self.on_leave)
    
    def on_enter(self, e):
        self['bg'] = '#40a9ff'
    
    def on_leave(self, e):
        self['bg'] = '#1890ff'

class SecondaryButton(tk.Button):
    """次要按钮"""
    def __init__(self, master=None, icon='', text='', command=None, **kw):
        super().__init__(master, text=f"{icon} {text}",
                        font=('微软雅黑', 10),
                        bg='white',
                        fg='#333333',
                        activebackground='#f5f5f5',
                        relief='flat',
                        cursor='hand2',
                        command=command,
                        padx=15,
                        pady=5,
                        **kw)
        self.bind('<Enter>', self.on_enter)
        self.bind('<Leave>', self.on_leave)
    
    def on_enter(self, e):
        self['bg'] = '#f5f5f5'
    
    def on_leave(self, e):
        self['bg'] = 'white'

class FileItem(tk.Frame):
    """文件列表项组件"""
    def __init__(self, master=None, name='', size='', modified='', is_folder=False, 
                 selected=False, on_click=None, on_double_click=None, **kw):
        super().__init__(master, bg='white' if not selected else '#e6f7ff', **kw)
        
        self.is_folder = is_folder
        self.selected = selected
        self.on_click = on_click
        self.on_double_click = on_double_click
        
        # 图标
        icon = ICONS['folder'] if is_folder else self.get_file_icon(name)
        self.icon_label = tk.Label(self, text=icon, font=('Segoe UI Emoji', 24), 
                                  bg=self['bg'])
        self.icon_label.pack(side=tk.LEFT, padx=10, pady=5)
        
        # 信息区域
        info_frame = tk.Frame(self, bg=self['bg'])
        info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=5)
        
        # 文件名
        self.name_label = tk.Label(info_frame, text=name, font=('微软雅黑', 11, 'bold'),
                                  bg=self['bg'], fg='#333333', anchor='w')
        self.name_label.pack(fill=tk.X)
        
        # 文件信息
        info_text = f"{size}  |  {modified}"
        self.info_label = tk.Label(info_frame, text=info_text, font=('微软雅黑', 9),
                                  bg=self['bg'], fg='#999999', anchor='w')
        self.info_label.pack(fill=tk.X)
        
        # 绑定事件
        self.bind('<Button-1>', self.on_select)
        self.icon_label.bind('<Button-1>', self.on_select)
        self.name_label.bind('<Button-1>', self.on_select)
        self.info_label.bind('<Button-1>', self.on_select)
        
        self.bind('<Double-Button-1>', self.on_double)
        self.icon_label.bind('<Double-Button-1>', self.on_double)
        self.name_label.bind('<Double-Button-1>', self.on_double)
        
        # 悬停效果
        self.bind('<Enter>', self.on_hover)
        self.bind('<Leave>', self.on_leave)
    
    def get_file_icon(self, filename):
        """根据文件类型返回图标"""
        ext = filename.lower().split('.')[-1] if '.' in filename else ''
        
        icon_map = {
            'jpg': 'image', 'jpeg': 'image', 'png': 'image', 'gif': 'image', 'bmp': 'image',
            'mp4': 'video', 'avi': 'video', 'mkv': 'video', 'mov': 'video',
            'mp3': 'audio', 'wav': 'audio', 'flac': 'audio', 'aac': 'audio',
            'zip': 'zip', 'rar': 'zip', '7z': 'zip', 'tar': 'zip', 'gz': 'zip',
            'doc': 'doc', 'docx': 'doc', 'txt': 'doc', 'md': 'doc',
            'xls': 'excel', 'xlsx': 'excel', 'csv': 'excel',
            'pdf': 'pdf',
            'py': 'code', 'js': 'code', 'java': 'code', 'cpp': 'code', 'c': 'code', 
            'h': 'code', 'html': 'code', 'css': 'code', 'json': 'code', 'xml': 'code'
        }
        
        return ICONS.get(icon_map.get(ext, 'unknown'), ICONS['unknown'])
    
    def on_select(self, event):
        if self.on_click:
            self.on_click(self)
    
    def on_double(self, event):
        if self.on_double_click:
            self.on_double_click(self)
    
    def on_hover(self, event):
        if not self.selected:
            self.configure(bg='#f5f5f5')
            self.icon_label.configure(bg='#f5f5f5')
            for child in self.winfo_children():
                if isinstance(child, tk.Frame):
                    child.configure(bg='#f5f5f5')
                    for grandchild in child.winfo_children():
                        grandchild.configure(bg='#f5f5f5')
    
    def on_leave(self, event):
        if not self.selected:
            self.configure(bg='white')
            self.icon_label.configure(bg='white')
            for child in self.winfo_children():
                if isinstance(child, tk.Frame):
                    child.configure(bg='white')
                    for grandchild in child.winfo_children():
                        grandchild.configure(bg='white')
    
    def set_selected(self, selected):
        self.selected = selected
        bg_color = '#e6f7ff' if selected else 'white'
        self.configure(bg=bg_color)
        self.icon_label.configure(bg=bg_color)
        for child in self.winfo_children():
            if isinstance(child, tk.Frame):
                child.configure(bg=bg_color)
                for grandchild in child.winfo_children():
                    grandchild.configure(bg=bg_color)

class FileBrowserDialog:
    """文件浏览器对话框 - 网盘风格"""
    def __init__(self, parent, ssh_client, config):
        self.parent = parent
        self.ssh = ssh_client
        self.config = config
        self.selected_files = []
        self.current_path = ""
        self.files_data = []
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("OBS文件浏览器")
        self.dialog.geometry("1200x800")
        self.dialog.configure(bg='#f0f2f5')
        
        # 设置窗口最小尺寸
        self.dialog.minsize(1000, 600)
        
        self.create_ui()
        self.load_files()
    
    def create_ui(self):
        """创建界面"""
        # 顶部工具栏
        toolbar = tk.Frame(self.dialog, bg='white', height=60)
        toolbar.pack(fill=tk.X, padx=0, pady=0)
        toolbar.pack_propagate(False)
        
        # 左侧Logo和标题
        title_frame = tk.Frame(toolbar, bg='white')
        title_frame.pack(side=tk.LEFT, padx=20, pady=10)
        
        tk.Label(title_frame, text="☁️", font=('Segoe UI Emoji', 24), 
                bg='white').pack(side=tk.LEFT)
        tk.Label(title_frame, text="OBS文件浏览器", font=('微软雅黑', 16, 'bold'),
                bg='white', fg='#1890ff').pack(side=tk.LEFT, padx=10)
        
        # 右侧操作按钮
        btn_frame = tk.Frame(toolbar, bg='white')
        btn_frame.pack(side=tk.RIGHT, padx=20, pady=10)
        
        self.refresh_btn = SecondaryButton(btn_frame, icon='🔄', text='刷新', 
                                          command=self.load_files)
        self.refresh_btn.pack(side=tk.LEFT, padx=5)
        
        # 面包屑导航栏
        breadcrumb_frame = tk.Frame(self.dialog, bg='#f0f2f5', height=40)
        breadcrumb_frame.pack(fill=tk.X, padx=20, pady=10)
        breadcrumb_frame.pack_propagate(False)
        
        self.breadcrumb_label = tk.Label(breadcrumb_frame, text="全部文件", 
                                        font=('微软雅黑', 11), bg='#f0f2f5', 
                                        fg='#333333', cursor='hand2')
        self.breadcrumb_label.pack(side=tk.LEFT)
        self.breadcrumb_label.bind('<Button-1>', lambda e: self.go_home())
        
        # 主内容区
        content_frame = tk.Frame(self.dialog, bg='#f0f2f5')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=0)
        
        # 左侧边栏 - 快速导航
        sidebar = tk.Frame(content_frame, bg='white', width=200)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        sidebar.pack_propagate(False)
        
        # 导航标题
        tk.Label(sidebar, text="快速导航", font=('微软雅黑', 12, 'bold'),
                bg='white', fg='#333333').pack(anchor='w', padx=15, pady=15)
        
        # 导航项
        nav_items = [
            ('📁', '全部文件', self.go_home),
            ('⏰', '最近更新', self.show_recent),
            ('📦', '大文件', self.show_large_files),
        ]
        
        for icon, text, cmd in nav_items:
            btn = tk.Button(sidebar, text=f"{icon}  {text}", 
                           font=('微软雅黑', 10),
                           bg='white', fg='#333333',
                           activebackground='#e6f7ff',
                           relief='flat', anchor='w',
                           cursor='hand2', command=cmd)
            btn.pack(fill=tk.X, padx=10, pady=2)
        
        # 分隔线
        ttk.Separator(sidebar, orient='horizontal').pack(fill=tk.X, padx=15, pady=10)
        
        # 收藏夹
        tk.Label(sidebar, text="收藏夹", font=('微软雅黑', 12, 'bold'),
                bg='white', fg='#333333').pack(anchor='w', padx=15, pady=(5, 10))
        
        self.load_favorites(sidebar)
        
        # 右侧文件列表区
        right_frame = tk.Frame(content_frame, bg='white')
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 列表标题
        header_frame = tk.Frame(right_frame, bg='#fafafa', height=40)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, text="文件名", font=('微软雅黑', 10, 'bold'),
                bg='#fafafa', fg='#666666').place(x=60, y=10)
        tk.Label(header_frame, text="大小", font=('微软雅黑', 10, 'bold'),
                bg='#fafafa', fg='#666666').place(x=500, y=10)
        tk.Label(header_frame, text="修改时间", font=('微软雅黑', 10, 'bold'),
                bg='#fafafa', fg='#666666').place(x=650, y=10)
        
        # 文件列表滚动区域
        list_container = tk.Frame(right_frame, bg='white')
        list_container.pack(fill=tk.BOTH, expand=True)
        
        # Canvas + Scrollbar
        self.canvas = tk.Canvas(list_container, bg='white', highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", 
                                 command=self.canvas.yview)
        
        self.files_frame = tk.Frame(self.canvas, bg='white')
        
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.files_frame, 
                                                       anchor='nw', width=980)
        
        self.files_frame.bind("<Configure>", self.on_frame_configure)
        self.canvas.bind("<Configure>", self.on_canvas_configure)
        
        # 绑定鼠标滚轮
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        
        # 底部操作栏
        bottom_bar = tk.Frame(self.dialog, bg='white', height=70)
        bottom_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=0, pady=0)
        bottom_bar.pack_propagate(False)
        
        # 选中信息
        self.selection_label = tk.Label(bottom_bar, text="未选择文件", 
                                       font=('微软雅黑', 10), bg='white', fg='#666666')
        self.selection_label.pack(side=tk.LEFT, padx=20, pady=20)
        
        # 操作按钮
        btn_frame = tk.Frame(bottom_bar, bg='white')
        btn_frame.pack(side=tk.RIGHT, padx=20, pady=15)
        
        self.download_btn = IconButton(btn_frame, icon='📥', text='下载选中', 
                                      command=self.download_selected)
        self.download_btn.pack(side=tk.LEFT, padx=5)
        self.download_btn.config(state='disabled')
        
        self.sync_btn = IconButton(btn_frame, icon='☁️', text='同步文件夹',
                                  command=self.sync_folder)
        self.sync_btn.pack(side=tk.LEFT, padx=5)
        
        SecondaryButton(btn_frame, icon='✕', text='关闭',
                       command=self.dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        # 搜索和时间过滤
        filter_frame = tk.Frame(right_frame, bg='white', height=50)
        filter_frame.pack(fill=tk.X, padx=10, pady=5)
        filter_frame.pack_propagate(False)
        
        # 搜索框
        search_frame = tk.Frame(filter_frame, bg='#f5f5f5', highlightbackground='#d9d9d9',
                               highlightthickness=1)
        search_frame.place(x=0, y=10, width=300, height=32)
        
        tk.Label(search_frame, text='🔍', font=('Segoe UI Emoji', 12), 
                bg='#f5f5f5').pack(side=tk.LEFT, padx=8)
        
        self.search_entry = tk.Entry(search_frame, font=('微软雅黑', 10),
                                    bg='#f5f5f5', relief='flat', bd=0)
        self.search_entry.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        self.search_entry.bind('<KeyRelease>', self.on_search)
        
        # 时间过滤
        time_frame = tk.Frame(filter_frame, bg='white')
        time_frame.place(x=320, y=10)
        
        tk.Label(time_frame, text="只显示晚于:", font=('微软雅黑', 10),
                bg='white', fg='#666666').pack(side=tk.LEFT)
        
        self.time_var = tk.StringVar(value='')
        time_entry = tk.Entry(time_frame, textvariable=self.time_var, 
                             font=('微软雅黑', 10), width=12)
        time_entry.pack(side=tk.LEFT, padx=5)
        time_entry.insert(0, "2024-01-01")
        
        IconButton(time_frame, icon='🔍', text='筛选', 
                  command=self.apply_time_filter).pack(side=tk.LEFT, padx=5)
    
    def on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    
    def on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)
    
    def on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    def load_favorites(self, parent):
        """加载收藏夹"""
        try:
            cmd = f"python {self.config.get('linux_path')}/cli.py favorites"
            out, err = self.ssh.exec(cmd)
            if not err:
                favorites = json.loads(out)
                for fav in favorites[:5]:  # 只显示前5个
                    name = fav.get('name', '未命名')
                    btn = tk.Button(parent, text=f"📌 {name}", 
                                   font=('微软雅黑', 10),
                                   bg='white', fg='#333333',
                                   activebackground='#e6f7ff',
                                   relief='flat', anchor='w',
                                   cursor='hand2')
                    btn.pack(fill=tk.X, padx=10, pady=2)
        except:
            pass
    
    def load_files(self):
        """加载文件列表"""
        try:
            self.refresh_btn.config(text='🔄 加载中...', state='disabled')
            self.dialog.update()
            
            cmd = f"python {self.config.get('linux_path')}/cli.py list-obs --bucket tfds-ht --prefix ''"
            out, err = self.ssh.exec(cmd)
            
            if err:
                messagebox.showerror("错误", f"加载文件列表失败:\n{err}")
                return
            
            self.files_data = json.loads(out)
            self.display_files(self.files_data)
            
        except Exception as e:
            messagebox.showerror("错误", f"加载失败: {str(e)}")
        finally:
            self.refresh_btn.config(text='🔄 刷新', state='normal')
    
    def display_files(self, files):
        """显示文件列表"""
        # 清空现有列表
        for widget in self.files_frame.winfo_children():
            widget.destroy()
        
        self.file_items = []
        
        if not files:
            # 显示空状态
            empty_frame = tk.Frame(self.files_frame, bg='white')
            empty_frame.pack(fill=tk.BOTH, expand=True, pady=100)
            
            tk.Label(empty_frame, text="📂", font=('Segoe UI Emoji', 64),
                    bg='white', fg='#d9d9d9').pack()
            tk.Label(empty_frame, text="暂无文件", font=('微软雅黑', 14),
                    bg='white', fg='#999999').pack(pady=10)
            return
        
        # 按文件夹分组排序
        folders = [f for f in files if f.get('is_in_folder', False)]
        root_files = [f for f in files if not f.get('is_in_folder', False)]
        
        # 显示根目录文件
        for file_info in root_files:
            self.create_file_item(file_info)
        
        # 显示文件夹
        displayed_folders = set()
        for folder in folders:
            parent_dir = folder.get('parent_dir', '')
            if parent_dir and parent_dir not in displayed_folders:
                displayed_folders.add(parent_dir)
                # 创建文件夹项
                folder_info = {
                    'key': parent_dir + '/',
                    'name': parent_dir.split('/')[-1] or parent_dir,
                    'size': '',
                    'last_modified': max([
                        f.get('last_modified', 0) 
                        for f in folders 
                        if f.get('parent_dir') == parent_dir
                    ]) if folders else 0,
                    'is_folder': True
                }
                self.create_file_item(folder_info)
    
    def create_file_item(self, file_info):
        """创建文件项"""
        is_folder = file_info.get('is_folder', False)
        
        if is_folder:
            name = file_info.get('name', '')
            size = f"{sum(1 for f in self.files_data if f.get('parent_dir') == file_info['key'].rstrip('/'))} 个项目"
        else:
            name = file_info.get('key', '').split('/')[-1]
            size = self.format_size(file_info.get('size', 0))
        
        modified = self.format_time(file_info.get('last_modified', 0))
        
        item = FileItem(
            self.files_frame,
            name=name,
            size=size,
            modified=modified,
            is_folder=is_folder,
            on_click=self.on_file_click,
            on_double_click=self.on_file_double_click
        )
        item.pack(fill=tk.X, padx=5, pady=2)
        item.file_info = file_info
        self.file_items.append(item)
    
    def on_file_click(self, item):
        """文件点击事件"""
        # 清除其他选中状态
        for fi in self.file_items:
            fi.set_selected(False)
        
        # 设置当前选中
        item.set_selected(True)
        self.selected_files = [item.file_info]
        
        # 更新选中信息
        name = item.file_info.get('key', '').split('/')[-1]
        self.selection_label.config(text=f"已选择: {name}")
        self.download_btn.config(state='normal')
    
    def on_file_double_click(self, item):
        """文件双击事件"""
        if item.file_info.get('is_folder'):
            # 进入文件夹
            self.enter_folder(item.file_info)
        else:
            # 直接下载
            self.download_selected()
    
    def enter_folder(self, folder_info):
        """进入文件夹"""
        folder_path = folder_info.get('key', '').rstrip('/')
        self.current_path = folder_path
        
        # 更新面包屑
        self.breadcrumb_label.config(text=f"全部文件 > {folder_path}")
        
        # 过滤显示该文件夹下的文件
        folder_files = [
            f for f in self.files_data 
            if f.get('parent_dir') == folder_path
        ]
        self.display_files(folder_files)
    
    def go_home(self):
        """返回根目录"""
        self.current_path = ""
        self.breadcrumb_label.config(text="全部文件")
        self.load_files()
    
    def show_recent(self):
        """显示最近更新的文件"""
        recent_files = sorted(
            self.files_data,
            key=lambda x: x.get('last_modified', 0),
            reverse=True
        )[:20]  # 最近20个
        self.display_files(recent_files)
        self.breadcrumb_label.config(text="全部文件 > 最近更新")
    
    def show_large_files(self):
        """显示大文件"""
        large_files = sorted(
            self.files_data,
            key=lambda x: x.get('size', 0),
            reverse=True
        )[:20]  # 最大的20个
        self.display_files(large_files)
        self.breadcrumb_label.config(text="全部文件 > 大文件")
    
    def on_search(self, event):
        """搜索文件"""
        keyword = self.search_entry.get().lower()
        if not keyword:
            self.display_files(self.files_data)
            return
        
        filtered = [
            f for f in self.files_data 
            if keyword in f.get('key', '').lower()
        ]
        self.display_files(filtered)
    
    def apply_time_filter(self):
        """应用时间过滤"""
        date_str = self.time_var.get()
        if not date_str:
            self.display_files(self.files_data)
            return
        
        try:
            filter_date = datetime.strptime(date_str, '%Y-%m-%d')
            filter_ts = int(filter_date.timestamp())
            
            filtered = [
                f for f in self.files_data 
                if f.get('last_modified', 0) > filter_ts
            ]
            self.display_files(filtered)
            
        except ValueError:
            messagebox.showerror("错误", "日期格式应为: YYYY-MM-DD")
    
    def download_selected(self):
        """下载选中的文件"""
        if not self.selected_files:
            return
        
        file_info = self.selected_files[0]
        key = file_info.get('key', '')
        
        # 询问下载位置
        target = messagebox.askstring(
            "确认下载",
            f"文件: {key}\n\n请输入下载到Linux服务器的目标路径:",
            initialvalue=self.config.get('download_path', '/railway-efs/000-tfds/')
        )
        
        if target:
            self.parent.start_download(key, target)
            self.dialog.destroy()
    
    def sync_folder(self):
        """同步文件夹"""
        if not self.selected_files:
            messagebox.showwarning("提示", "请先选择一个文件夹")
            return
        
        file_info = self.selected_files[0]
        if not file_info.get('is_folder'):
            messagebox.showwarning("提示", "请选择一个文件夹而不是文件")
            return
        
        folder_path = file_info.get('key', '').rstrip('/')
        
        # 询问是否应用时间过滤
        date_str = self.time_var.get()
        if date_str:
            msg = f"将同步文件夹: {folder_path}\n只下载 {date_str} 之后的文件\n\n是否继续？"
        else:
            msg = f"将同步文件夹: {folder_path}\n下载所有文件\n\n是否继续？"
        
        if messagebox.askyesno("确认同步", msg):
            target = self.config.get('download_path', '/railway-efs/000-tfds/')
            self.parent.sync_folder(folder_path, target, date_str)
            self.dialog.destroy()
    
    def format_size(self, size):
        """格式化文件大小"""
        if not size:
            return "-"
        size = int(size)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
    
    def format_time(self, timestamp):
        """格式化时间戳"""
        if not timestamp:
            return "-"
        try:
            ts = int(timestamp)
            return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
        except:
            return str(timestamp)

class MainApplication:
    """主应用程序 - 现代化界面"""
    def __init__(self, master):
        self.master = master
        master.title("OBS下载工具")
        master.geometry("1400x900")
        master.configure(bg='#f0f2f5')
        
        # 设置最小尺寸
        master.minsize(1200, 700)
        
        # 加载配置
        self.config = load_config()
        
        # 初始化SSH客户端
        self.ssh = SSHClient(
            self.config["ssh_host"],
            self.config["ssh_user"],
            self.config["ssh_password"]
        )
        
        # 测试连接
        self.test_connection()
        
        # 创建界面
        self.create_ui()
        
        # 启动状态轮询
        self.start_polling()
    
    def test_connection(self):
        """测试服务器连接"""
        try:
            self.ssh.connect()
            messagebox.showinfo("连接成功", f"成功连接到服务器 {self.config['ssh_host']}")
        except Exception as e:
            messagebox.showerror("连接失败", 
                f"无法连接到服务器:\n{str(e)}\n\n"
                f"请检查:\n1. 网络连接是否正常\n"
                f"2. 服务器地址、用户名、密码是否正确\n"
                f"3. 配置文件: {CONFIG_PATH}")
            self.master.quit()
    
    def create_ui(self):
        """创建主界面"""
        # 顶部导航栏
        header = tk.Frame(self.master, bg='white', height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        # Logo
        logo_frame = tk.Frame(header, bg='white')
        logo_frame.pack(side=tk.LEFT, padx=20, pady=10)
        
        tk.Label(logo_frame, text="☁️", font=('Segoe UI Emoji', 28),
                bg='white').pack(side=tk.LEFT)
        tk.Label(logo_frame, text="OBS下载工具", font=('微软雅黑', 18, 'bold'),
                bg='white', fg='#1890ff').pack(side=tk.LEFT, padx=10)
        
        # 顶部操作按钮
        btn_frame = tk.Frame(header, bg='white')
        btn_frame.pack(side=tk.RIGHT, padx=20, pady=12)
        
        IconButton(btn_frame, icon='🌐', text='浏览文件',
                  command=self.open_file_browser).pack(side=tk.LEFT, padx=5)
        IconButton(btn_frame, icon='📥', text='新建下载',
                  command=self.show_download_dialog).pack(side=tk.LEFT, padx=5)
        
        # 主内容区
        content = tk.Frame(self.master, bg='#f0f2f5')
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # 左侧统计面板
        left_panel = tk.Frame(content, bg='white', width=280)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 20))
        left_panel.pack_propagate(False)
        
        # 统计卡片
        self.create_stats_cards(left_panel)
        
        # 右侧任务列表
        right_panel = tk.Frame(content, bg='white')
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 任务列表标题
        list_header = tk.Frame(right_panel, bg='white', height=50)
        list_header.pack(fill=tk.X, padx=20, pady=10)
        list_header.pack_propagate(False)
        
        tk.Label(list_header, text="下载任务", font=('微软雅黑', 16, 'bold'),
                bg='white', fg='#333333').pack(side=tk.LEFT)
        
        # 刷新按钮
        SecondaryButton(list_header, icon='🔄', text='刷新',
                       command=self.refresh_tasks).pack(side=tk.RIGHT)
        
        # 任务列表
        self.create_task_list(right_panel)
        
        # 底部状态栏
        self.status_bar = tk.Label(self.master, 
                                  text=f"✓ 已连接到 {self.config['ssh_host']}  |  就绪",
                                  font=('微软雅黑', 10),
                                  bg='#fafafa', fg='#666666',
                                  relief='flat', anchor='w', padx=20, pady=8)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)
    
    def create_stats_cards(self, parent):
        """创建统计卡片"""
        # 标题
        tk.Label(parent, text="📊 统计概览", font=('微软雅黑', 14, 'bold'),
                bg='white', fg='#333333').pack(anchor='w', padx=20, pady=20)
        
        # 运行中任务
        self.running_card = self.create_stat_card(parent, "▶️ 运行中", "0", "#1890ff")
        self.running_card.pack(fill=tk.X, padx=20, pady=10)
        
        # 待处理任务
        self.pending_card = self.create_stat_card(parent, "⏳ 待处理", "0", "#faad14")
        self.pending_card.pack(fill=tk.X, padx=20, pady=10)
        
        # 已完成任务
        self.completed_card = self.create_stat_card(parent, "✅ 已完成", "0", "#52c41a")
        self.completed_card.pack(fill=tk.X, padx=20, pady=10)
        
        # 下载速度
        self.speed_card = self.create_stat_card(parent, "⚡ 当前速度", "0 MB/s", "#722ed1")
        self.speed_card.pack(fill=tk.X, padx=20, pady=10)
    
    def create_stat_card(self, parent, title, value, color):
        """创建单个统计卡片"""
        card = tk.Frame(parent, bg='#f6ffed', highlightbackground=color,
                       highlightthickness=1, bd=0)
        
        inner = tk.Frame(card, bg='#f6ffed', padx=15, pady=15)
        inner.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(inner, text=title, font=('微软雅黑', 11),
                bg='#f6ffed', fg='#666666').pack(anchor='w')
        
        value_label = tk.Label(inner, text=value, font=('微软雅黑', 24, 'bold'),
                              bg='#f6ffed', fg=color)
        value_label.pack(anchor='w', pady=(5, 0))
        
        card.value_label = value_label
        return card
    
    def create_task_list(self, parent):
        """创建任务列表"""
        # 列表容器
        list_frame = tk.Frame(parent, bg='white')
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # 表头
        header = tk.Frame(list_frame, bg='#fafafa', height=40)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        headers = [
            ("任务名称", 300),
            ("状态", 120),
            ("进度", 150),
            ("大小", 120),
            ("创建者", 100),
            ("操作", 150)
        ]
        
        x = 20
        for text, width in headers:
            tk.Label(header, text=text, font=('微软雅黑', 10, 'bold'),
                    bg='#fafafa', fg='#666666').place(x=x, y=10)
            x += width
        
        # 任务列表Canvas
        self.task_canvas = tk.Canvas(list_frame, bg='white', highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical",
                                 command=self.task_canvas.yview)
        
        self.task_list_frame = tk.Frame(self.task_canvas, bg='white')
        self.task_canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.task_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.task_canvas_window = self.task_canvas.create_window(
            (0, 0), window=self.task_list_frame, anchor='nw', width=960)
        
        self.task_list_frame.bind("<Configure>", 
                                 lambda e: self.task_canvas.configure(
                                     scrollregion=self.task_canvas.bbox("all")))
    
    def open_file_browser(self):
        """打开文件浏览器"""
        FileBrowserDialog(self.master, self.ssh, self.config)
    
    def show_download_dialog(self):
        """显示下载对话框"""
        dialog = tk.Toplevel(self.master)
        dialog.title("新建下载任务")
        dialog.geometry("600x350")
        dialog.configure(bg='white')
        dialog.transient(self.master)
        dialog.grab_set()
        
        # 标题
        tk.Label(dialog, text="📥 新建下载任务", font=('微软雅黑', 16, 'bold'),
                bg='white', fg='#333333').pack(pady=20)
        
        # 表单
        form_frame = tk.Frame(dialog, bg='white', padx=40)
        form_frame.pack(fill=tk.X, pady=10)
        
        # OBS路径
        tk.Label(form_frame, text="OBS文件路径:", font=('微软雅黑', 11),
                bg='white', fg='#333333').pack(anchor='w', pady=(10, 5))
        
        path_frame = tk.Frame(form_frame, bg='white')
        path_frame.pack(fill=tk.X)
        
        entry_path = tk.Entry(path_frame, font=('微软雅黑', 11), 
                             relief='solid', bd=1)
        entry_path.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
        
        IconButton(path_frame, icon='📋', text='粘贴',
                  command=lambda: self.paste_clipboard(entry_path)).pack(side=tk.LEFT, padx=5)
        
        # 目标路径
        tk.Label(form_frame, text="下载到:", font=('微软雅黑', 11),
                bg='white', fg='#333333').pack(anchor='w', pady=(15, 5))
        
        entry_target = tk.Entry(form_frame, font=('微软雅黑', 11),
                               relief='solid', bd=1)
        entry_target.pack(fill=tk.X, ipady=5)
        entry_target.insert(0, self.config.get('download_path', '/railway-efs/000-tfds/'))
        
        # 按钮
        btn_frame = tk.Frame(dialog, bg='white', pady=30)
        btn_frame.pack()
        
        def on_submit():
            path = entry_path.get().strip()
            target = entry_target.get().strip()
            
            if not path:
                messagebox.showwarning("提示", "请输入OBS文件路径")
                return
            
            self.start_download(path, target)
            dialog.destroy()
        
        IconButton(btn_frame, icon='✓', text='开始下载', command=on_submit).pack(side=tk.LEFT, padx=5)
        SecondaryButton(btn_frame, icon='✕', text='取消', command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    
    def paste_clipboard(self, entry):
        """粘贴剪贴板内容"""
        try:
            text = self.master.clipboard_get()
            entry.delete(0, tk.END)
            entry.insert(0, text)
        except:
            pass
    
    def start_download(self, object_key, target_dir):
        """开始下载"""
        try:
            cmd = (f"python /data9/obs_tool/linux_server/cli.py download "
                  f"--object_key '{object_key}' --target_dir '{target_dir}' "
                  f"--created_by 'windows_user'")
            out, err = self.ssh.exec(cmd)
            
            if err:
                messagebox.showerror("错误", f"启动下载失败:\n{err}")
            else:
                result = json.loads(out)
                task_id = result.get('task_id')
                messagebox.showinfo("成功", f"✅ 任务已创建\n任务ID: {task_id}")
                self.refresh_tasks()
                
        except Exception as e:
            messagebox.showerror("错误", f"操作失败: {str(e)}")
    
    def sync_folder(self, folder_path, target_dir, date_filter=None):
        """同步文件夹"""
        try:
            cmd = (f"python /data9/obs_tool/linux_server/cli.py sync-folder "
                  f"--bucket tfds-ht --prefix '{folder_path}/' "
                  f"--target-dir '{target_dir}'")
            
            if date_filter:
                try:
                    filter_ts = int(datetime.strptime(date_filter, '%Y-%m-%d').timestamp())
                    cmd += f" --after {filter_ts}"
                except:
                    pass
            
            out, err = self.ssh.exec(cmd)
            
            if err:
                messagebox.showerror("错误", f"启动同步失败:\n{err}")
            else:
                result = json.loads(out)
                task_count = len(result.get('tasks', []))
                messagebox.showinfo("成功", f"✅ 同步任务已创建\n共 {task_count} 个文件")
                self.refresh_tasks()
                
        except Exception as e:
            messagebox.showerror("错误", f"操作失败: {str(e)}")
    
    def refresh_tasks(self):
        """刷新任务列表"""
        try:
            cmd = "python /data9/obs_tool/linux_server/cli.py list"
            out, err = self.ssh.exec(cmd)
            
            if err:
                self.status_bar.config(text=f"刷新失败: {err}")
                return
            
            tasks = json.loads(out)
            self.update_task_list(tasks)
            self.update_stats(tasks)
            
        except Exception as e:
            self.status_bar.config(text=f"刷新失败: {str(e)}")
    
    def update_task_list(self, tasks):
        """更新任务列表显示"""
        # 清空现有列表
        for widget in self.task_list_frame.winfo_children():
            widget.destroy()
        
        if not tasks:
            # 显示空状态
            empty = tk.Label(self.task_list_frame, text="暂无任务",
                           font=('微软雅黑', 14), bg='white', fg='#999999')
            empty.pack(pady=50)
            return
        
        # 按状态排序：运行中 > 待处理 > 暂停 > 其他
        status_order = {'running': 0, 'pending': 1, 'paused': 2}
        sorted_tasks = sorted(
            tasks.items(),
            key=lambda x: (status_order.get(x[1].get('status'), 99), x[0])
        )
        
        for task_id, task in sorted_tasks:
            self.create_task_item(task_id, task)
    
    def create_task_item(self, task_id, task):
        """创建任务项"""
        item_frame = tk.Frame(self.task_list_frame, bg='white', height=60)
        item_frame.pack(fill=tk.X, pady=2)
        item_frame.pack_propagate(False)
        
        # 任务名称
        name = task.get('object_key', '未知文件').split('/')[-1]
        tk.Label(item_frame, text=name, font=('微软雅黑', 11),
                bg='white', fg='#333333', anchor='w').place(x=20, y=18, width=280)
        
        # 状态
        status = task.get('status', 'unknown')
        status_text, status_color = self.get_status_info(status)
        status_label = tk.Label(item_frame, text=status_text,
                               font=('微软雅黑', 10),
                               bg=status_color, fg='white',
                               padx=8, pady=2)
        status_label.place(x=320, y=16)
        
        # 进度
        progress = task.get('progress', {})
        pct = progress.get('percentage', 0)
        progress_text = f"{pct:.1f}%"
        
        # 进度条
        progress_frame = tk.Frame(item_frame, bg='#f5f5f5', width=100, height=8)
        progress_frame.place(x=460, y=22)
        progress_fill = tk.Frame(progress_frame, bg='#1890ff',
                                width=int(100 * pct / 100), height=8)
        progress_fill.place(x=0, y=0)
        
        tk.Label(item_frame, text=progress_text, font=('微软雅黑', 9),
                bg='white', fg='#666666').place(x=570, y=18)
        
        # 大小
        size = self.format_size(task.get('total_size', 0))
        tk.Label(item_frame, text=size, font=('微软雅黑', 10),
                bg='white', fg='#666666').place(x=660, y=18)
        
        # 创建者
        creator = task.get('created_by', '未知')
        tk.Label(item_frame, text=creator, font=('微软雅黑', 10),
                bg='white', fg='#666666').place(x=780, y=18)
        
        # 操作按钮
        btn_frame = tk.Frame(item_frame, bg='white')
        btn_frame.place(x=880, y=12)
        
        if status == 'running':
            SecondaryButton(btn_frame, icon='⏸', text='暂停',
                           command=lambda: self.pause_task(task_id)).pack(side=tk.LEFT, padx=2)
        elif status == 'paused':
            SecondaryButton(btn_frame, icon='▶', text='继续',
                           command=lambda: self.resume_task(task_id)).pack(side=tk.LEFT, padx=2)
        
        SecondaryButton(btn_frame, icon='✕', text='取消',
                       command=lambda: self.cancel_task(task_id)).pack(side=tk.LEFT, padx=2)
    
    def get_status_info(self, status):
        """获取状态信息"""
        status_map = {
            'pending': ('⏳ 等待中', '#faad14'),
            'running': ('▶️ 下载中', '#1890ff'),
            'paused': ('⏸️ 已暂停', '#fa8c16'),
            'completed': ('✅ 完成', '#52c41a'),
            'failed': ('❌ 失败', '#ff4d4f'),
            'cancelled': ('🚫 已取消', '#999999')
        }
        return status_map.get(status, ('❓ 未知', '#999999'))
    
    def update_stats(self, tasks):
        """更新统计信息"""
        running = sum(1 for t in tasks.values() if t.get('status') == 'running')
        pending = sum(1 for t in tasks.values() if t.get('status') in ('pending', 'paused'))
        completed = sum(1 for t in tasks.values() if t.get('status') == 'completed')
        
        self.running_card.value_label.config(text=str(running))
        self.pending_card.value_label.config(text=str(pending))
        self.completed_card.value_label.config(text=str(completed))
    
    def pause_task(self, task_id):
        """暂停任务"""
        try:
            cmd = f"python /data9/obs_tool/linux_server/cli.py pause --task_id {task_id}"
            self.ssh.exec(cmd)
            self.refresh_tasks()
        except Exception as e:
            messagebox.showerror("错误", f"暂停失败: {str(e)}")
    
    def resume_task(self, task_id):
        """恢复任务"""
        try:
            cmd = f"python /data9/obs_tool/linux_server/cli.py resume --task_id {task_id}"
            self.ssh.exec(cmd)
            self.refresh_tasks()
        except Exception as e:
            messagebox.showerror("错误", f"恢复失败: {str(e)}")
    
    def cancel_task(self, task_id):
        """取消任务"""
        if messagebox.askyesno("确认", "确定要取消这个任务吗？"):
            try:
                cmd = f"python /data9/obs_tool/linux_server/cli.py cancel --task_id {task_id}"
                self.ssh.exec(cmd)
                self.refresh_tasks()
            except Exception as e:
                messagebox.showerror("错误", f"取消失败: {str(e)}")
    
    def start_polling(self):
        """启动状态轮询"""
        self.refresh_tasks()
        self.master.after(3000, self.start_polling)  # 每3秒刷新
    
    def format_size(self, size):
        """格式化文件大小"""
        if not size:
            return "0 B"
        size = int(size)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
    
    def show_history(self):
        """显示下载历史"""
        try:
            cmd = "python /data9/obs_tool/linux_server/cli.py history --limit 20"
            out, err = self.ssh.exec(cmd)
            
            if err:
                messagebox.showerror("错误", f"获取历史记录失败: {err}")
                return
            
            history = json.loads(out)
            
            dialog = tk.Toplevel(self.master)
            dialog.title("下载历史")
            dialog.geometry("700x500")
            dialog.configure(bg='white')
            
            # 标题
            tk.Label(dialog, text="📋 下载历史", font=('微软雅黑', 16, 'bold'),
                    bg='white', fg='#333333').pack(pady=15)
            
            # 历史记录列表
            text = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, font=('微软雅黑', 10))
            text.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
            
            if not history:
                text.insert(tk.END, "暂无下载历史")
            else:
                for item in reversed(history):
                    text.insert(tk.END, f"📄 {item.get('object_key', '未知')}\n")
                    text.insert(tk.END, f"   路径: {item.get('final_path', '未知')}\n")
                    text.insert(tk.END, f"   大小: {self.format_size(item.get('size', 0))}\n")
                    completed = item.get('completed_at', 0)
                    if completed:
                        from datetime import datetime
                        time_str = datetime.fromtimestamp(completed).strftime('%Y-%m-%d %H:%M:%S')
                        text.insert(tk.END, f"   时间: {time_str}\n")
                    text.insert(tk.END, "-" * 60 + "\n")
            
            # 关闭按钮
            tk.Button(dialog, text="关闭", command=dialog.destroy,
                     font=('微软雅黑', 10), bg='white').pack(pady=10)
            
        except Exception as e:
            messagebox.showerror("错误", f"操作失败: {str(e)}")
    
    def manage_favorites(self):
        """管理收藏夹"""
        dialog = tk.Toplevel(self.master)
        dialog.title("收藏夹管理")
        dialog.geometry("500x400")
        dialog.configure(bg='white')
        
        # 标题
        tk.Label(dialog, text="⭐ 收藏夹管理", font=('微软雅黑', 16, 'bold'),
                bg='white', fg='#333333').pack(pady=15)
        
        # 当前收藏夹列表
        list_frame = tk.Frame(dialog, bg='white')
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        self.fav_listbox = tk.Listbox(list_frame, font=('微软雅黑', 11),
                                      selectbackground='#e6f7ff', bd=1, relief='solid')
        self.fav_listbox.pack(fill=tk.BOTH, expand=True)
        
        # 加载收藏夹
        self.refresh_favorites_list()
        
        # 添加新收藏夹
        add_frame = tk.Frame(dialog, bg='white')
        add_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(add_frame, text="名称:", bg='white', font=('微软雅黑', 10)).pack(side=tk.LEFT)
        name_entry = tk.Entry(add_frame, font=('微软雅黑', 10), width=15)
        name_entry.pack(side=tk.LEFT, padx=5)
        
        tk.Label(add_frame, text="路径:", bg='white', font=('微软雅黑', 10)).pack(side=tk.LEFT)
        path_entry = tk.Entry(add_frame, font=('微软雅黑', 10), width=20)
        path_entry.pack(side=tk.LEFT, padx=5)
        
        def add_fav():
            name = name_entry.get().strip()
            path = path_entry.get().strip()
            if name and path:
                try:
                    cmd = f"python /data9/obs_tool/linux_server/cli.py favorites --action add --name '{name}' --path '{path}'"
                    self.ssh.exec(cmd)
                    self.refresh_favorites_list()
                    name_entry.delete(0, tk.END)
                    path_entry.delete(0, tk.END)
                except Exception as e:
                    messagebox.showerror("错误", f"添加失败: {e}")
            else:
                messagebox.showwarning("提示", "请填写名称和路径")
        
        tk.Button(add_frame, text="添加", command=add_fav,
                 font=('微软雅黑', 10), bg='#1890ff', fg='white').pack(side=tk.LEFT, padx=10)
        
        # 关闭按钮
        tk.Button(dialog, text="关闭", command=dialog.destroy,
                 font=('微软雅黑', 10), bg='white').pack(pady=15)
    
    def refresh_favorites_list(self):
        """刷新收藏夹列表"""
        self.fav_listbox.delete(0, tk.END)
        try:
            cmd = "python /data9/obs_tool/linux_server/cli.py favorites"
            out, err = self.ssh.exec(cmd)
            if not err:
                favorites = json.loads(out)
                for fav in favorites:
                    name = fav.get('name', '未命名')
                    path = fav.get('path', '')
                    self.fav_listbox.insert(tk.END, f"{name} ({path})")
        except Exception as e:
            print(f"加载收藏夹失败: {e}")

def main():
    root = tk.Tk()
    
    # 设置DPI感知
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    
    app = MainApplication(root)
    root.mainloop()

if __name__ == '__main__':
    main()
