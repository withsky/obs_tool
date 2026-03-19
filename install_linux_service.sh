#!/bin/bash
# OBS Download Daemon 安装脚本
# 在 Linux 服务器上以 root 权限运行

set -e

echo "=== OBS Download Daemon 安装脚本 ==="
echo ""

# 检查是否以 root 运行
if [ "$EUID" -ne 0 ]; then 
    echo "请以 root 权限运行此脚本"
    exit 1
fi

# 配置
INSTALL_DIR="/data9/obs_tool"
SERVICE_NAME="obs-daemon"
USER="dl"
PYTHON_PATH="/home/dl/miniconda3/bin/python"

echo "1. 创建必要的目录..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/storage"
mkdir -p "$INSTALL_DIR/storage/progress"
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$INSTALL_DIR/config"

echo "2. 设置目录权限..."
chown -R $USER:$USER "$INSTALL_DIR"
chmod -R 755 "$INSTALL_DIR"
chmod 777 "$INSTALL_DIR/storage"
chmod 777 "$INSTALL_DIR/logs"

echo "3. 复制服务文件..."
cp linux_server/obs-daemon.service /etc/systemd/system/

echo "4. 重新加载 systemd..."
systemctl daemon-reload

echo "5. 启用服务（开机自启）..."
systemctl enable obs-daemon.service

echo "6. 启动服务..."
systemctl start obs-daemon.service

echo ""
echo "=== 安装完成 ==="
echo ""
echo "服务状态检查:"
systemctl status obs-daemon.service --no-pager

echo ""
echo "常用命令:"
echo "  查看状态: systemctl status obs-daemon"
echo "  停止服务: systemctl stop obs-daemon"
echo "  启动服务: systemctl start obs-daemon"
echo "  重启服务: systemctl restart obs-daemon"
echo "  查看日志: tail -f $INSTALL_DIR/logs/daemon.log"
echo ""
