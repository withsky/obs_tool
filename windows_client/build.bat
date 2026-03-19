#!/bin/bash
# Windows 客户端打包脚本 (在 Windows 上运行)

echo "=== OBS下载工具 Windows客户端打包脚本 ==="
echo ""

# 检查Python
python --version
if [ $? -ne 0 ]; then
    echo "错误: 未找到Python，请先安装Python 3.8+"
    exit 1
fi

echo "1. 安装依赖..."
pip install pyinstaller paramiko

echo "2. 创建输出目录..."
mkdir -p ../dist/windows_client

echo "3. 打包EXE..."
pyinstaller --onefile --windowed \
    --name "OBS下载工具" \
    --icon=assets/icon.ico \
    --add-data "assets;assets" \
    --clean \
    launcher.py

echo "4. 复制到输出目录..."
cp dist/OBS下载工具.exe ../dist/windows_client/
cp -r config ../dist/windows_client/

echo ""
echo "=== 打包完成 ==="
echo "输出文件: ../dist/windows_client/OBS下载工具.exe"
echo ""
echo "使用说明:"
echo "1. 将整个 dist/windows_client 文件夹复制到Windows电脑"
echo "2. 双击运行 OBS下载工具.exe"
echo "3. 确保Windows电脑可以访问 10.155.106.228 的SSH端口"
echo ""
