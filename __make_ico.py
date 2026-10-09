"""图标后处理：裁掉白边 + 生成 .ico 多尺寸（用完即删）。

发现的问题：Agnes 生成的图标自带**白色圆角外框**，
在深色任务栏/文件夹背景上会像"贴了张白纸"，必须裁掉只保留深色主体。

做法：从外向内扫描，找到真正的深色圆角方块边界，裁掉四周白边。
"""
from pathlib import Path

from PIL import Image

CAND = Path(r"D:\开发工具\工具\ip-optimizer-分析\assets\candidates")
OUT = Path(r"D:\开发工具\工具\ip-optimizer-分析\assets")


def find_content_bbox(img: Image.Image, dark_threshold: int = 90) -> tuple:
    """找到深色主体（圆角方块）的边界框，用于裁掉白边。

    做法：按行/列统计「暗像素」数量，暗像素占比超过 30% 的行列才算主体。

    Args:
        img: RGB 图像。
        dark_threshold: 判定为「暗」的亮度上限。

    Returns:
        (left, top, right, bottom) 边界框。
    """
    w, h = img.size
    px = img.load()

    def row_is_content(y: int) -> bool:
        dark = sum(1 for x in range(0, w, 4)
                   if sum(px[x, y][:3]) / 3 < dark_threshold)
        return dark / (w // 4) > 0.3

    def col_is_content(x: int) -> bool:
        dark = sum(1 for y in range(0, h, 4)
                   if sum(px[x, y][:3]) / 3 < dark_threshold)
        return dark / (h // 4) > 0.3

    top = next((y for y in range(h) if row_is_content(y)), 0)
    bottom = next((y for y in range(h - 1, -1, -1) if row_is_content(y)), h - 1)
    left = next((x for x in range(w) if col_is_content(x)), 0)
    right = next((x for x in range(w - 1, -1, -1) if col_is_content(x)), w - 1)
    return (left, top, right + 1, bottom + 1)


def make_square(img: Image.Image) -> Image.Image:
    """裁成正方形（保持内容居中）。"""
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


results = []
for name in ["A-signal", "C-node", "D-bolt"]:
    src = CAND / f"icon-{name}.png"
    if not src.exists():
        continue

    img = Image.open(src).convert("RGB")
    print(f"\n=== {name} ===")
    print(f"  原图: {img.size}")

    bbox = find_content_bbox(img)
    print(f"  检测到主体边界: {bbox}")
    cropped = img.crop(bbox)
    print(f"  裁白边后: {cropped.size}")

    square = make_square(cropped)
    print(f"  正方形化: {square.size}")

    # 保存裁好的母版（1024 级，供后续任意缩放）
    master = square.resize((1024, 1024), Image.LANCZOS)
    master_path = OUT / f"icon-{name}-clean.png"
    master.save(master_path, "PNG")
    print(f"  母版: {master_path}")

    # 生成 .ico 多尺寸（Windows 图标标准档位）
    ico_path = OUT / f"icon-{name}.ico"
    square.resize((256, 256), Image.LANCZOS).save(
        ico_path, format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"  ICO: {ico_path}  ({ico_path.stat().st_size:,} B)")
    results.append((name, str(ico_path)))

print(f"\n{'=' * 60}")
print("已生成 .ico 候选：")
for n, p in results:
    print(f"  {n:12s} {p}")
