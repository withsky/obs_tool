@echo off
chcp 65001 >nul
title OBS下载工具 - 配置向导
echo.
echo ╔════════════════════════════════════════╗
echo ║       OBS下载工具 - 配置向导           ║
echo ╚════════════════════════════════════════╝
echo.
echo 欢迎使用OBS下载工具！
echo.
echo 本向导将帮助您完成初始配置。
echo.

:: 创建配置目录
if not exist "config" mkdir config

:: 检查是否已有配置
if exist "config\settings.json" (
    echo [提示] 检测到已有配置文件
    set /p overwrite="是否重新配置？(y/n): "
    if /i "!overwrite!"=="n" (
        echo 保留现有配置，退出向导。
        pause
        exit /b 0
    )
)

echo.
echo ──────────────────────────────────────
echo 步骤 1/3: 服务器连接配置
echo ──────────────────────────────────────
echo.

set /p ssh_host="服务器地址 [默认: 10.155.106.228]: "
if "!ssh_host!"=="" set ssh_host=10.155.106.228

set /p ssh_user="用户名 [默认: dl]: "
if "!ssh_user!"=="" set ssh_user=dl

set /p ssh_pass="密码 [默认: tfds#2025]: "
if "!ssh_pass!"=="" set ssh_pass=tfds#2025

echo.
echo ──────────────────────────────────────
echo 步骤 2/3: 下载路径配置
echo ──────────────────────────────────────
echo.
echo 这是文件下载到Linux服务器后的保存位置。
echo 默认路径为：/railway-efs/000-tfds/
echo.

set /p download_path="下载路径 [默认: /railway-efs/000-tfds/]: "
if "!download_path!"=="" set download_path=/railway-efs/000-tfds/

echo.
echo ──────────────────────────────────────
echo 步骤 3/3: 确认配置
echo ──────────────────────────────────────
echo.
echo 服务器地址: !ssh_host!
echo 用户名:     !ssh_user!
echo 密码:       ********
echo 下载路径:   !download_path!
echo.

set /p confirm="配置是否正确？(y/n): "
if /i not "!confirm!"=="y" (
    echo 配置已取消，请重新运行向导。
    pause
    exit /b 1
)

:: 保存配置
echo {> config\settings.json
echo   "ssh_host": "!ssh_host!",>> config\settings.json
echo   "ssh_user": "!ssh_user!",>> config\settings.json
echo   "ssh_password": "!ssh_pass!",>> config\settings.json
echo   "linux_path": "/data9/obs_tool/linux_server",>> config\settings.json
echo   "download_path": "!download_path!">> config\settings.json
echo }>> config\settings.json

echo.
echo [✓] 配置已保存到 config\settings.json
echo.
echo ╔════════════════════════════════════════╗
echo ║ 配置完成！                             ║
echo ║                                        ║
echo ║ 现在您可以：                            ║
echo ║ 1. 双击 start.bat 启动程序             ║
echo ║ 2. 或双击 start.exe 启动（如果已打包） ║
echo ╚════════════════════════════════════════╝
echo.

pause
