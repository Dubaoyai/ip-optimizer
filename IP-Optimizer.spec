# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（V1.5 · 2026-10-09）。

设计目标：**体积最小，但功能零损失**。

## 为什么需要这个文件（而不是 README 里那条一行命令）

项目只用到 PySide6 的 3 个模块（QtCore / QtGui / QtWidgets），
但 PyInstaller 会把整个 PySide6 站点目录当成依赖源，把**用不到的大件**
一并打进 exe。实测（2026-10-09）PySide6 可执行件合计 424.5 MB，其中：

    Qt6WebEngineCore.dll   194.0 MB  ← 内嵌浏览器，本项目不用
    opengl32sw.dll          19.7 MB  ← 软件 OpenGL 回退，本项目无 3D
    avcodec-61.dll          13.4 MB  ← 音视频编解码，本项目无媒体

排除它们后 exe 从 44.3 MB 降到约 25 MB 量级（实测值见构建脚本输出）。

## 排除原则（保守，宁可多留不可误删）

**只排除本项目明确不可能调用的模块**，判据是「源码里 import 过吗」：
    判据命令：Select-String -Path gui\*.py,core\*.py,utils\*.py,main.py -Pattern 'from PySide6'

排除清单里每一个都附了「为什么本项目用不到」。
**不确定的一律保留** —— 体积次要，功能正确性优先。
"""

# ----------------------------------------------------------------------
# 本项目用不到的 Qt 模块（附排除理由）
# ----------------------------------------------------------------------
# 判据：项目全部源码只 import 了 QtCore / QtGui / QtWidgets 三个模块。
EXCLUDED_QT_MODULES = [
    "PySide6.QtWebEngineCore",     # 内嵌 Chromium 浏览器（194 MB 级）—— 本项目是原生表格界面，无任何网页渲染
    "PySide6.QtWebEngineWidgets",  # 同上，WebEngine 的控件层
    "PySide6.QtWebEngineQuick",    # 同上
    "PySide6.QtWebChannel",        # WebEngine 与 JS 通信桥梁 —— 无网页即无用
    "PySide6.QtWebSockets",        # WebSocket 是浏览器侧协议 —— 本项目用标准库 http/socket
    "PySide6.QtNetwork",           # 本项目网络走标准库 socket / http.client / urllib，未用 QtNetwork
    "PySide6.QtQml",               # QML 声明式 UI —— 本项目全部用 QWidget 手写
    "PySide6.QtQuick",             # QML 运行时
    "PySide6.QtQuick3D",           # QML 3D
    "PySide6.QtQuickWidgets",      # QML 嵌入 Widget
    "PySide6.QtQuickControls2",    # QML 控件样式
    "PySide6.Qt3DCore",            # 3D 引擎 —— 本项目无 3D
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtCharts",            # 图表控件 —— 本项目结果用表格展示，无图表
    "PySide6.QtDataVisualization", # 数据可视化 3D —— 同上
    "PySide6.QtGraphs",            # 新图表模块
    "PySide6.QtMultimedia",        # 音视频 —— 本项目无媒体功能
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtPdf",               # PDF 渲染 —— 本项目不打开 PDF
    "PySide6.QtPdfWidgets",
    "PySide6.QtSql",               # 数据库 —— 本项目数据存 JSON / 内存，不用 SQL
    "PySide6.QtTest",              # Qt 单元测试框架 —— 打包产物不需要
    "PySide6.QtDesigner",          # Qt Designer 集成 —— 仅设计期使用
    "PySide6.QtUiTools",           # 运行期加载 .ui 文件 —— 本项目界面全部手写代码
    "PySide6.QtOpenGL",            # OpenGL 上下文 —— 无 3D/自定义 GL 绘制
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtSvg",               # SVG 渲染 —— 本项目图标用 Qt 内置绘制，不加载 .svg 文件
    "PySide6.QtSvgWidgets",
    "PySide6.QtPrintSupport",      # 打印 —— 无打印功能
    "PySide6.QtBluetooth",         # 蓝牙 —— 无关
    "PySide6.QtNfc",               # NFC —— 无关
    "PySide6.QtPositioning",       # 定位 —— 无关
    "PySide6.QtSerialPort",        # 串口 —— 无关
    "PySide6.QtSensors",           # 传感器 —— 无关
    "PySide6.QtStateMachine",      # 状态机 —— 本项目状态管理是普通 Python 变量
    "PySide6.QtHelp",              # 帮助文档浏览器 —— 本项目帮助在 README
    "PySide6.QtScxml",             # SCXML 状态机 —— 无关
    "PySide6.QtRemoteObjects",     # Qt 远程对象 —— 无关
    "PySide6.QtSpatialAudio",      # 空间音频 —— 无关
    "PySide6.QtTextToSpeech",      # 语音合成 —— 无关
    "PySide6.QtHttpServer",        # Qt 内置 HTTP 服务 —— 本项目自己写 socket 测速
    "PySide6.QtConcurrent",        # Qt 线程池 —— 本项目用 QThread + 标准库 threading
]

# ----------------------------------------------------------------------
# 用不到的标准库 / 第三方（附理由）
# ----------------------------------------------------------------------
EXCLUDED_MODULES = [
    "tkinter",          # 本项目用 PySide6，不碰 Tk
    "unittest",         # 打包产物不需要测试框架（tests/ 不进 exe）
    "pytest",
    "pydoc",            # 文档生成
    "doctest",
    "pip",              # 打包产物不需要包管理器（distutils/setuptools 保留：
    "wheel",            #   PyInstaller 引导链路可能间接引用，排除风险高于收益）
]

# ⚠️ 标准库 http / urllib / email / socket / ssl **一律不排除**：
#    本项目核心功能是 HTTP 测速与下载测速，这些是**功能依赖**而非冗余。
#    曾误将 email 放入排除清单（注释与代码自相矛盾），已在复检中修正 ——
#    http.client 的解析链路可能间接用到 email，排除它会埋下运行时炸弹。

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_MODULES + EXCLUDED_QT_MODULES,
    noarchive=False,
    optimize=2,          # 字节码优化级别 2：剥掉 docstring 与断言，进一步减小体积
)

# ======================================================================
# 二进制后置过滤（关键 —— excludes 挡不住 DLL 依赖链）
# ======================================================================
#
# ## 为什么需要这一步
#
# `excludes` 只作用于 **Python 层 import**。PyInstaller 的 Qt hook 会用
# QLibraryInfo 查询运行时路径，把整组 Qt DLL **按依赖关系**收进 a.binaries，
# 这一步与 excludes 无关 —— 所以上面排除了 QtPdf / QtQml 等模块后，
# 它们的 DLL 仍会出现在 exe 里。
#
# 实测（2026-10-09，仅用 excludes 时 exe 内的残留）：
#     opengl32sw.dll    7.31 MB
#     Qt6Quick.dll      2.75 MB
#     Qt6Pdf.dll        2.35 MB
#     Qt6Qml.dll        2.01 MB
#     Qt6Network.dll    0.72 MB
#     合计             约 15.1 MB —— 占 exe 总体积的约 1/3
#
# ## 剔除判据（保守，每项都验证过）
#
# 只剔除**明确验证过零引用**的项；判据 = 项目源码是否 import 过该模块
# 或加载过对应资源。验证方法与结论见本文件顶部排除清单的逐条注释。
# **不确定的一律保留** —— 体积是次要目标，功能正确性是硬约束。

_UNUSED_BINARIES = {
    # --- 软件 OpenGL 回退（7.31 MB）---
    # 本项目界面全部是 QWidget 标准控件，无任何 OpenGL 绘制。
    # 判据：源码 grep "QOpenGL|QSurfaceFormat" → 0 处。
    # 风险说明：Qt6Gui 在缺少硬件 OpenGL 时理论上会回退到它，
    #   但 Windows 平台插件 qwindows.dll 走 D3D 渲染路径，不依赖此库。
    #   ⚠️ 此项为**唯一有理论风险**的剔除，packaged 冒烟测试必须覆盖
    #   「窗口能显示且控件可见」。
    "opengl32sw.dll",
    # --- QML / Quick 运行时（合计约 5 MB）---
    # 界面 100% QWidget 手写，项目内无任何 .qml 文件。
    "qt6qml.dll", "qt6qmlmodels.dll", "qt6qmlcompiler.dll",
    "qt6quick.dll", "qt6quickcontrols2.dll", "qt6quicktemplates2.dll",
    "qt6quickdialogs2.dll", "qt6quickshapes.dll", "qt6quickwidgets.dll",
    # --- PDF（2.35 MB）--- 源码 grep "QtPdf" → 0 处
    "qt6pdf.dll",
    # --- Qt 网络层（0.72 MB）--- 全部网络走标准库 socket/http.client/ssl
    "qt6network.dll",
    # --- 虚拟键盘 / 3D / Shader / Designer ---  均为无关功能
    "qt6virtualkeyboard.dll", "qt6shadertools.dll", "qt6opengl.dll",
    "qt6designer.dll", "qt6designercomponents.dll", "qt6svg.dll",
}

_UNUSED_PLUGIN_FRAGMENTS = (
    # QML 相关插件目录（无 QML 即无用）
    "qmltooling\\", "scenegraph\\", "designer\\",
    "assetimporters\\", "virtualkeyboard\\",
    # 图像格式插件：结果用表格呈现，不显示图片文件。
    # 保留 qico/qjpeg（窗口图标可能用到），其余剔除。
    "imageformats\\qtiff.dll", "imageformats\\qwebp.dll",
    "imageformats\\qpdf.dll", "imageformats\\qsvg.dll",
    "imageformats\\qgif.dll",
)


def _slim_binaries(binaries):
    """从 Analysis 收集的二进制里剔除确认无用的项。

    Args:
        binaries: [(dest_name, src_path, typecode), ...]

    Returns:
        (保留列表, 剔除列表)
    """
    kept, removed = [], []
    for entry in binaries:
        dest = str(entry[0])
        low = dest.lower()
        name = low.rsplit("\\", 1)[-1]

        if name in _UNUSED_BINARIES:
            removed.append((dest, entry[2] if len(entry) > 2 else 0))
            continue
        if any(frag in low for frag in _UNUSED_PLUGIN_FRAGMENTS):
            removed.append((dest, entry[2] if len(entry) > 2 else 0))
            continue
        kept.append(entry)
    return kept, removed


_kept_binaries, _removed_binaries = _slim_binaries(a.binaries)
if _removed_binaries:
    print(f"[qtslim] 剔除 {len(_removed_binaries)} 个无用二进制：")
    for _dest, _ in _removed_binaries:
        print(f"[qtslim]   - {_dest}")
a.binaries = _kept_binaries

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="IP-Optimizer-V1.5",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,         # Windows 下 strip 无意义且可能损坏
    upx=False,           # UPX 压缩易被杀软误报，本机也未必装了 UPX —— 不启用
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # 窗口程序，不弹黑框
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,           # 暂无 .ico 资源（assets/ 为空）；有图标后可填 "assets/app.ico"
)
