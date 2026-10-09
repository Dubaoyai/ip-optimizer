"""图标候选的小尺寸可辨识性检验（用完即删）。

为什么必须做：图标在任务栏/文件夹里只有 16~32px，
现在看 1024px 大图很漂亮，缩到 16px 可能糊成一团。
判据：生成 16/32/48px 缩略图，检查主体是否仍可辨认。
"""
from pathlib import Path

from PIL import Image

CAND = Path(r"D:\开发工具\工具\ip-optimizer-分析\assets\candidates")

names = ["A-signal", "B-chevron", "C-node", "D-bolt"]
sizes = [16, 32, 48]

print("=== 小尺寸可辨识性分析 ===")
print("判据：主体与背景的对比度（亮部像素占比），过低的会糊\n")

for name in names:
    src = CAND / f"icon-{name}.png"
    if not src.exists():
        print(f"{name}: 缺失")
        continue

    img = Image.open(src).convert("RGBA")

    # 统一裁掉透明/白边，取中心主体（生成图常见四周留白）
    print(f"{name}:")
    for size in sizes:
        small = img.resize((size, size), Image.LANCZOS)
        px = list(small.convert("RGB").getdata())
        # 统计「亮部」（紫色主体）像素占比
        bright = sum(1 for r, g, b in px if (r + g + b) / 3 > 70)
        ratio = bright / len(px)
        # 主体占比 15%~60% 为佳：太低=太小看不清，太高=糊满
        verdict = "✅ 清晰" if 0.12 <= ratio <= 0.65 else ("⚠️ 偏小" if ratio < 0.12 else "⚠️ 糊满")
        print(f"    {size:2d}px: 主体占比 {ratio:5.1%}  {verdict}")

    # 拼一张对比图供目视
    strip = Image.new("RGBA", (16 + 32 + 48 + 40, 48), (11, 11, 11, 255))
    x = 10
    for size in sizes:
        s = img.resize((size, size), Image.LANCZOS)
        strip.paste(s, (x, (48 - size) // 2), s)
        x += size + 12
    strip.save(CAND / f"preview-{name}.png")

print(f"\n已生成各候选的小尺寸拼图（preview-*.png）于 {CAND}")
