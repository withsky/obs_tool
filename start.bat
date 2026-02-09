@echo off
chcp 65001 >nul
title OBS下载工具 - 启动器
echo.
echo  ╔════════════════════════════════════════╗
echo  ║         OBS下载工具启动器              ║
echo  ║  专为非技术人员设计的文件下载工具      ║
echo  ╚════════════════════════════════════════╝
echo.

:: 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.8+
    echo.
    echo 安装方式：
    echo 1. 访问 https://www.python.org/downloads/
    echo 2. 下载Python 3.8或更高版本
    echo 3. 安装时勾选"Add Python to PATH"
    echo.
    pause
    exit /b 1
)

echo [✓] Python已安装

:: 检查必要的库
echo [检查依赖...]
python -c "import paramiko" >nul 2>&1
if errorlevel 1 (
    echo [安装依赖] paramiko...
    pip install paramiko -q
)

echo [✓] 依赖检查完成

:: 检查配置文件
if not exist "config\settings.json" (
    echo.
    echo [首次使用] 正在创建配置文件...
    if not exist "config" mkdir config
    (
        echo {
        echo   "ssh_host": "10.155.106.228",
        echo   "ssh_user": "dl",
        echo   "ssh_password": "tfds#2025",
        echo   "linux_path": "/data9/obs_tool/linux_server",
        echo   "download_path": "/railway-efs/000-tfds/"
        echo }
    ) > config\settings.json
    echo [✓] 配置文件已创建
)

echo.
echo ╔════════════════════════════════════════╗
echo ║  正在启动OBS下载工具...                ║
echo ╚════════════════════════════════════════╝
echo.
echo 提示：
echo - 首次启动可能需要几秒钟连接服务器
echo - 如遇问题请查看上方的错误信息
echo - 详细使用说明请查看 README.md
echo.

:: 启动程序
python windows_client\launcher.py

if errorlevel 1 (
    echo.
    echo [错误] 程序异常退出
    echo.
    echo 可能的解决方案：
    echo 1. 检查网络连接是否正常
    echo 2. 确认能访问服务器 10.155.106.228
    echo 3. 检查config\settings.json中的密码是否正确
    echo 4. 联系系统管理员
    echo.
    pause
)
