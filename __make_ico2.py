"""图标后处理 v2：正确裁掉白色圆角外框（用完即删）。

v1 失败原因：用「暗像素占比 > 30%」判主体边界，
白边很窄（几十像素），整行仍以暗像素为主 ⇒ 判据不敏感，边界返回整图。

v2 判据：**直接从四条边向内扫**，找第一个「明显不是白色」的像素位置。
白边特征明确（接近 #FFFFFF），这个判据精准得多。
"""
from pathlib import Path

from PIL import Image

CAND = Path(r"D:\开发工具\工具\ip-optimizer-分析\assets\candidates")
OUT = Path(r"D:\开发工具\工具\ip-optimizer-分析\assets")


def is_white(px, x, y, thresh=225):
    """判断某像素是否接近白色（白边特征）。"""
    r, g, b = px[x, y][:3]
    return r > thresh and g > thresh and b > thresh


def find_dark_bbox(img):
    """从四条边向内扫描，定位深色主体的边界。

    Args:
        img: RGB 图像。

    Returns:
        (left, top, right, bottom)
    """
    w, h = img.size
    px = img.load()

    def row_has_dark(y):
        """该行是否存在非白像素（至少 10% 宽度的非白）。"""
        cnt = sum(1 for x in range(0, w, 3) if not is_white(px, x, y))
        return cnt / (w // 3) > 0.10

    def col_has_dark(x):
        cnt = sum(1 for y in range(0, h, 3) if not is_white(px, x, y))
        return cnt / (h // 3) > 0.10

    top = next((y for y in range(h) if row_has_dark(y)), 0)
    bottom = next((y for y in range(h - 1, -1, -1) if row_has_dark(y)), h - 1)
    left = next((x for x in range(w) if col_has_dark(x)), 0)
    right = next((x for x in range(w - 1, -1, -1) if col_has_dark(x)), w - 1)
    return (left, top, right + 1, bottom + 1)


def make_square(img):
    """裁成正方形（内容居中）。"""
    w, h = img.size
    side = min(w, h)
    return img.crop(((w - side) // 2, (h - side) // 2,
                     (w - side) // 2 + side, (h - side) // 2 + side))


for name in ["A-signal", "C-node", "D-bolt"]:
    src = CAND / f"icon-{name}.png"
    if not src.exists():
        continue

    img = Image.open(src).convert("RGB")
    w, h = img.size

    # 打印四角与四边的像素，确认白边确实存在
    px = img.load()
    print(f"\n=== {name} ({w}x{h}) ===")
    print(f"  左上角(0,0): {px[0, 0]}")
    print(f"  顶边中点   : {px[w // 2, 0]}")
    print(f"  左边中点   : {px[0, h // 2]}")
    print(f"  中心       : {px[w // 2, h // 2]}")

    bbox = find_dark_bbox(img)
    print(f"  检测主体边界: {bbox}  "
          f"(裁掉 左{bbox[0]} 上{bbox[1]} 右{w - bbox[2]} 下{h - bbox[3]} px)")

    cropped = img.crop(bbox)
    square = make_square(cropped)
    master = square.resize((1024, 1024), Image.LANCZOS)
    master.save(OUT / f"icon-{name}-clean.png", "PNG")

    ico = OUT / f"icon-{name}.ico"
    square.resize((256, 256), Image.LANCZOS).save(
        ico, format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"  母版 {master.name}  |  ICO {ico.stat().st_size:,} B")

print("\n完成")
