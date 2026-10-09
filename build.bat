@echo off
chcp 65001 >nul
rem ====================================================================
rem  《IP优化器》打包脚本
rem
rem  用法：双击本文件，或在项目根目录执行  build.bat
rem  产物：dist\IP-Optimizer-V1.5.exe（单文件，免安装）
rem
rem  为什么要用脚本而不是 README 里那条一行命令：
rem  项目只用到 PySide6 的 3 个模块（QtCore/QtGui/QtWidgets），但 PyInstaller
rem  默认会把整个 PySide6 站点目录扫进去，实测可执行件达 424.5 MB
rem  （其中 Qt6WebEngineCore.dll 一个就 194 MB，本项目根本用不到）。
rem  IP-Optimizer.spec 里逐项排除了这些无用模块，本脚本就是调用它。
rem ====================================================================

cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

echo ============================================================
echo   打包《IP优化器》
echo ============================================================
echo.

rem ---- 1. 检查 Python ----
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [错误] 未找到 python 命令。
    echo        请先安装 Python 3.10+ 并在安装时勾选 "Add python.exe to PATH"。
    echo.
    pause
    exit /b 1
)
echo [1/4] Python 就绪
python --version

rem ---- 2. 检查 / 安装依赖 ----
echo.
echo [2/4] 检查依赖...
python -c "import PySide6" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo       缺少 PySide6，正在安装（约 250 MB，首次较慢）...
    python -m pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo [错误] PySide6 安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
)
echo       PySide6 就绪

python -c "import PyInstaller" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo       缺少 PyInstaller，正在安装...
    python -m pip install pyinstaller
    if %ERRORLEVEL% neq 0 (
        echo [错误] PyInstaller 安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
)
echo       PyInstaller 就绪

rem ---- 3. 打包 ----
echo.
echo [3/4] 开始打包（约 1-2 分钟，请勿关闭窗口）...
echo.
python -m PyInstaller --noconfirm --clean IP-Optimizer.spec
if %ERRORLEVEL% neq 0 (
    echo.
    echo [错误] 打包失败，请查看上方输出中的报错信息。
    pause
    exit /b 1
)

rem ---- 4. 结果 ----
echo.
echo [4/4] 打包完成
echo.
if exist "dist\IP-Optimizer-V1.5.exe" (
    for %%F in ("dist\IP-Optimizer-V1.5.exe") do (
        echo   产物：dist\IP-Optimizer-V1.5.exe
        echo   体积：%%~zF 字节
    )
    echo.
    echo   提示：这个 exe 是独立单文件，拷到任意目录（U 盘/桌面）都能直接运行，
    echo         不需要项目里的任何其它文件。日志与导出结果会生成在 exe 同级目录。
) else (
    echo   [警告] 未找到预期的 exe 产物，请检查 dist\ 目录。
)
echo.
echo ============================================================
pause
