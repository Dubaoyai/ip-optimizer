"""生成程序图标候选（Agnes 免费通道）。

设计约束（关键）：
- 图标最终用于 16/32/48/256px，**必须极简**：只用 1-2 个大色块形状；
- 配色契合程序主题：深灰底 #181818 / 紫强调 #7c6cf0 / 青绿 #00d4aa；
- 不要文字（小尺寸下文字必然糊）；
- 方形构图，主体居中占 60-70%，四周留白。

一共产 4 版候选，供用户挑选。
"""
import json
import subprocess
import sys
from pathlib import Path

SKILL = Path(r"D:\DSH-中枢大脑系统\技能\Agnes模型调用")
OUT = Path(r"D:\开发工具\工具\ip-optimizer-分析\assets\candidates")
OUT.mkdir(parents=True, exist_ok=True)

# 4 版候选，围绕「极简几何 + 优选/信号」语义展开
# 共同约束：纯色背景、单一主体、无文字、高对比
CANDIDATES = [
    ("A-signal", (
        "App icon, flat minimal geometric design, a single bold abstract symbol: "
        "three concentric arcs radiating from a small solid dot at bottom-left, "
        "suggesting signal or network reach. "
        "Deep charcoal background (#181818), symbol in vivid purple (#7c6cf0). "
        "Extremely simple, centered, generous padding, no text, no letters, no gradient, "
        "clean vector style, high contrast, rounded square canvas"
    )),
    ("B-chevron", (
        "App icon, flat minimal geometric design, a single bold chevron arrow "
        "pointing up-right made of two thick parallelograms, "
        "suggesting speed and optimization. "
        "Deep charcoal background (#181818), shape in vivid purple (#7c6cf0) "
        "with a small teal (#00d4aa) accent square. "
        "Extremely simple, centered, no text, no letters, no gradient, "
        "clean vector style, high contrast, rounded square canvas"
    )),
    ("C-node", (
        "App icon, flat minimal geometric design, a single large letter-free symbol: "
        "a bold rounded square with a smaller filled circle peer beneath it, "
        "connected by a thick short vertical bar, like a minimal network node. "
        "Deep charcoal background (#181818), shapes in vivid purple (#7c6cf0). "
        "Extremely simple, centered, no text, no letters, no gradient, "
        "clean vector style, high contrast, rounded square canvas"
    )),
    ("D-bolt", (
        "App icon, flat minimal geometric design, a single bold lightning-like "
        "angular shape made of two thick geometric slabs, suggesting speed. "
        "Deep charcoal background (#181818), shape in vivid purple (#7c6cf0). "
        "Extremely simple, centered, generous padding, no text, no letters, "
        "no gradient, clean vector style, high contrast, rounded square canvas"
    )),
]

results = []
for name, prompt in CANDIDATES:
    out = OUT / f"icon-{name}.png"
    if out.exists():
        print(f"[skip] {name} 已存在")
        results.append((name, str(out), 0))
        continue

    print(f"\n{'=' * 60}\n生成候选 {name}\n{'=' * 60}")
    cmd = [
        sys.executable, str(SKILL / "调用Agnes.py"), "image", prompt,
        "--size", "1K", "--ratio", "1:1", "--out", str(out),
    ]
    proc = subprocess.run(cmd, cwd=str(SKILL), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    tail = (proc.stdout or "")[-400:]
    print(tail)
    if proc.returncode != 0:
        print("STDERR:", (proc.stderr or "")[-400:])
    results.append((name, str(out), out.stat().st_size if out.exists() else 0))

print(f"\n{'=' * 60}\n汇总\n{'=' * 60}")
for name, path, size in results:
    print(f"  {name:14s} {'✅' if size else '❌'}  {size:>9,} B  {path}")
