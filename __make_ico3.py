"""图标后处理 v3：四角白底转透明 + 生成多尺寸 ICO（用完即删）。

## 修正上一版的误判

v1/v2 我以为图标有「白色外框」需要裁掉 —— **实测证伪**：
  - 左上角 (0,0) = (251,251,253) 白
  - 顶边中点   = (17,16,22)      深色
⇒ 白边**只存在于圆角之外的四个角**，这是圆角图标的正常形态，不是"白框"。
真正的处理应该是：**把圆角外的白色变透明**（透明化），而不是裁掉内容。

## 做法

对每个像素：若接近白色 **且** 处于图像四角区域 → 设为透明。
（只处理角落区域，避免误伤主体内部可能存在的白色/高光像素）

## 产出

- `icon-<name>.ico`：多尺寸（16/24/32/48/64/128/256），透明角
- `icon-<name>-preview.png`：16/32/48/256 四档放大拼图，供目视/选择
"""
from pathlib import Path

from PIL import Image

CAND = Path(r"D:\开发工具\工具\ip-optimizer-分析\assets\candidates")
OUT = Path(r"D:\开发工具\工具\ip-optimizer-分析\assets")


def make_corners_transparent(img: Image.Image, thresh: int = 235) -> Image.Image:
    """把四角区域的白色像素变透明（保留主体完整）。

    Args:
        img: RGB 图像。
        thresh: 判定白色的阈值。

    Returns:
        RGBA 图像（四角透明）。
    """
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()

    # 只处理「距边缘不超过 22% 边长」且「靠近对角」的像素，
    # 这样既覆盖圆角外的白区，又不会误伤主体内部
    margin = int(min(w, h) * 0.22)
    for y in range(h):
        for x in range(w):
            near_x = x < margin or x > w - margin
            near_y = y < margin or y > h - margin
            if not (near_x and near_y):
                continue
            r, g, b, _ = px[x, y]
            if r > thresh and g > thresh and b > thresh:
                px[x, y] = (0, 0, 0, 0)
    return img


for name in ["A-signal", "C-node", "D-bolt"]:
    src = CAND / f"icon-{name}.png"
    if not src.exists():
        continue

    img = Image.open(src)
    print(f"\n=== {name} ===")
    processed = make_corners_transparent(img)

    # 母版（1024，透明角）
    master = OUT / f"icon-{name}-clean.png"
    processed.save(master, "PNG")
    print(f"  母版: {master.name}")

    # 多尺寸 ICO
    ico = OUT / f"icon-{name}.ico"
    processed.save(
        ico, format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"  ICO : {ico.name}  ({ico.stat().st_size:,} B)")

    # 预览拼图：在深色底上展示 16/32/48/256 四档
    tiles = [16, 32, 48, 256]
    pad = 14
    total_w = sum(tiles) + pad * (len(tiles) + 1)
    max_h = max(tiles) + pad * 2
    strip = Image.new("RGB", (total_w, max_h), (24, 24, 28))
    x = pad
    for t in tiles:
        s = processed.resize((t, t), Image.LANCZOS)
        strip.paste(s, (x, (max_h - t) // 2), s)
        x += t + pad
    prev = OUT / f"preview-{name}.png"
    strip.save(prev, "PNG")
    print(f"  预览: {prev.name}  ({strip.width}x{strip.height})")

print("\n完成")
