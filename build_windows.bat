@echo off
chcp 65001 >nul
title OBS下载工具 - 打包脚本
echo.
echo ╔════════════════════════════════════════╗
echo ║       OBS下载工具 - 打包脚本           ║
echo ╚════════════════════════════════════════╝
echo.
echo 本脚本将把Python程序打包成独立的EXE文件，
echo 方便没有Python环境的用户使用。
echo.

:: 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python
    echo 请先安装Python 3.8或更高版本
    pause
    exit /b 1
)

echo [✓] Python已安装

:: 检查PyInstaller
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [安装] PyInstaller...
    pip install pyinstaller -q
)

echo [✓] PyInstaller已安装

:: 检查其他依赖
echo [检查依赖...]
python -c "import paramiko" >nul 2>&1
if errorlevel 1 (
    echo [安装] paramiko...
    pip install paramiko -q
)

echo [✓] 依赖检查完成

:: 创建输出目录
if not exist "dist" mkdir dist
if not exist "dist\OBS下载工具" mkdir "dist\OBS下载工具"

echo.
echo ╔════════════════════════════════════════╗
echo ║  正在打包...                           ║
echo ╚════════════════════════════════════════╝
echo.

:: 打包主程序
echo [1/4] 打包主程序...
pyinstaller --onefile --windowed --noconsole ^
    --name "OBS下载工具" ^
    --distpath "dist\OBS下载工具" ^
    --workpath "build" ^
    --specpath "build" ^
    windows_client\launcher.py

if errorlevel 1 (
    echo [错误] 打包失败
    pause
    exit /b 1
)

echo [✓] 主程序打包完成

:: 复制必要文件
echo [2/4] 复制配置文件...
if not exist "dist\OBS下载工具\config" mkdir "dist\OBS下载工具\config"
copy "windows_client\config\settings.json" "dist\OBS下载工具\config\" >nul
echo [✓] 配置文件已复制

echo [3/4] 复制启动脚本...
copy "start.bat" "dist\OBS下载工具\" >nul
copy "config_wizard.bat" "dist\OBS下载工具\" >nul
echo [✓] 启动脚本已复制

echo [4/4] 复制说明文档...
copy "README.md" "dist\OBS下载工具\" >nul
echo [✓] 说明文档已复制

:: 创建桌面快捷方式（可选）
echo.
set /p create_shortcut="是否创建桌面快捷方式？(y/n): "
if /i "!create_shortcut!"=="y" (
    echo [创建] 桌面快捷方式...
    powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\Desktop\OBS下载工具.lnk'); $Shortcut.TargetPath = '%CD%\dist\OBS下载工具\OBS下载工具.exe'; $Shortcut.WorkingDirectory = '%CD%\dist\OBS下载工具'; $Shortcut.IconLocation = '%CD%\dist\OBS下载工具\OBS下载工具.exe,0'; $Shortcut.Save()"
    echo [✓] 快捷方式已创建
)

echo.
echo ╔════════════════════════════════════════╗
echo ║ 打包完成！                             ║
echo ║                                        ║
echo ║ 输出目录: dist\OBS下载工具\            ║
echo ║                                        ║
echo ║ 文件清单：                              ║
echo ║ - OBS下载工具.exe    （主程序）         ║
echo ║ - config\settings.json （配置文件）     ║
echo ║ - start.bat          （启动脚本）       ║
echo ║ - config_wizard.bat  （配置向导）       ║
echo ║ - README.md          （使用说明）       ║
echo ╚════════════════════════════════════════╝
echo.
echo 使用方法：
echo 1. 将整个 dist\OBS下载工具 文件夹复制到目标电脑
echo 2. 双击 OBS下载工具.exe 运行
echo 3. 首次使用请运行 config_wizard.bat 进行配置
echo.
echo 提示：
echo - 如果目标电脑没有Python环境，使用EXE版本
echo - 如果有Python环境，可以直接使用 start.bat 启动
echo.

pause
