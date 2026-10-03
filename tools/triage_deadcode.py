"""死代码甄别：逐条给出「保留 / 删除」判断与理由。

不自动删除 —— 死代码里有一部分是**预留的公开 API**（如 `as_dict` 用于
导出、`is_packaged` 用于打包判断），删掉会破坏接口完整性。
本脚本只做**判定与清单**，实际处理由人工确认后执行。

判定标准：
- 属「数据模型的转换/查询接口」→ 保留（第三方/未来调用者可能用）
- 属「已被新实现取代的旧接口」→ 建议删除
- 属「调试/工具函数」且无调用 → 建议删除

运行：
    python tools/triage_deadcode.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# (函数名, 所在文件, 行号, 判定, 理由)
TRIAGE: list[tuple[str, str, int, str, str]] = [
    # ---- 保留：数据模型的查询/转换接口，属对外能力 ----
    ("as_dict", "core/tcp_tester.py", 61, "保留",
     "TestResult 的字典转换接口，导出/持久化场景常用；删掉会削弱数据模型的可用性"),
    ("palette", "gui/theme.py", 215, "保留",
     "主题色板查询接口，供外部按需取色；与 color()/qcolor() 构成完整 API"),
    ("qcolor", "gui/theme.py", 234, "保留",
     "同上（实际已有 30 处引用，非死代码，扫描器按定义计数误报）"),
    ("current_mode", "gui/theme.py", 246, "保留",
     "查询当前主题模式的公开接口，界面状态展示可能用到"),
    ("is_packaged", "utils/paths.py", 83, "保留",
     "判断是否运行在 PyInstaller 打包环境的公开接口，打包相关逻辑的标准探测点"),
    ("set_title", "gui/widgets.py", 244, "保留",
     "Panel 组件的标题更新接口，动态改标题时需要"),

    # ---- 保留：已用或有明确用途但计数误报 ----
    ("sort_results", "core/scanner.py", 128, "保留",
     "扫描结果排序接口（3 处引用：定义+内部调用+文档），扫描器内部排序用"),
    ("total_failed", "core/stability.py", 128, "保留",
     "稳定性统计的失败计数（2 处引用），与 total_success 成对，删一个破坏对称性"),

    # ---- 删除：确定被取代或纯调试用 ----
    ("max_download_speed", "core/stability.py", 101, "删除",
     "稳定性统计的极值接口，界面与导出均未使用；与 min/avg 重复覆盖，属冗余"),
    ("min_download_speed", "core/stability.py", 105, "删除",
     "同上"),
    ("is_valid_count", "gui/fetch_worker.py", 109, "删除",
     "获取线程里的数量校验，实际校验已在 SampleWorker/对话框层完成，属遗留"),
    ("load_saved_mode_legacy", "gui/theme.py", 329, "删除",
     "旧版主题记忆的读取接口，当前版本已改为「启动恒深色」，该接口无调用且易误用"),
    ("restyle", "gui/theme.py", 1048, "删除",
     "对单控件重设样式，实际全部走全局 apply_theme；保留会鼓励绕过统一主题"),
    ("section_title", "gui/widgets.py", 273, "删除",
     "构造小节标题的辅助函数，实际都用 Panel 组件；属早期实现遗留"),
]


def main() -> int:
    """输出判定清单与统计。"""
    keep = [x for x in TRIAGE if x[3] == "保留"]
    drop = [x for x in TRIAGE if x[3] == "删除"]

    print("=" * 74)
    print("死代码甄别结果")
    print("=" * 74)
    print(f"\n【保留】{len(keep)} 项（属公开接口或计数误报）")
    for name, f, ln, _, reason in keep:
        print(f"  · {f}:{ln}  {name}()")
        print(f"      理由：{reason}")

    print(f"\n【建议删除】{len(drop)} 项（冗余/遗留/易误用）")
    for name, f, ln, _, reason in drop:
        print(f"  · {f}:{ln}  {name}()")
        print(f"      理由：{reason}")

    print("\n" + "=" * 74)
    print(f"合计 {len(TRIAGE)} 项 → 保留 {len(keep)} / 删除 {len(drop)}")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
