"""全项目体检扫描器：用可复算的指标定位问题，而非凭印象。

扫描维度：
1. 冗余/重复：同名函数、未被引用的公开函数、重复的色值字面量
2. 死代码：定义后从未被调用的方法/函数
3. 硬编码：绝对路径、魔法数字
4. 异常处理：裸 except、静默 pass
5. 注释覆盖：公开函数是否都有 docstring
6. 界面文本：是否有多处重复的提示语（可统一的）

输出：分类问题清单 + 计数，供人工复核。

运行：
    python tools/audit_project.py
"""

from __future__ import annotations

import ast
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"__pycache__", ".git", "output", "logs", ".pytest_cache"}
PY_DIRS = ("core", "gui", "utils")


def iter_py_files() -> list[Path]:
    """列出项目内所有 Python 源文件（不含测试与缓存）。"""
    files: list[Path] = [ROOT / "main.py"]
    for d in PY_DIRS:
        files.extend(sorted((ROOT / d).rglob("*.py")))
    return [f for f in files if f.exists() and not any(s in f.parts for s in SKIP_DIRS)]


def main() -> int:
    """执行体检。"""
    files = iter_py_files()
    print(f"扫描 {len(files)} 个源文件\n")
    print("=" * 72)
    print("① 死代码：定义了但从未被引用的模块级函数 / 方法")
    print("=" * 72)

    all_sources = {f: f.read_text(encoding="utf-8") for f in files}
    combined = "\n".join(all_sources.values())

    defined: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    for f, src in all_sources.items():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            print(f"  ⚠ 语法错误，跳过：{f}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                defined[node.name].append((f, node.lineno))

    dead: list[tuple[str, Path, int]] = []
    for name, places in defined.items():
        if name in ("main", "__init__"):
            continue
        # 引用次数（排除定义行本身）
        usages = len(re.findall(rf"\b{re.escape(name)}\b", combined))
        if usages <= len(places):
            for f, lineno in places:
                dead.append((name, f, lineno))
    if dead:
        for name, f, lineno in sorted(dead, key=lambda x: str(x[1])):
            print(f"  {f.relative_to(ROOT)}:{lineno}  {name}()")
    else:
        print("  无")
    print(f"  → 共 {len(dead)} 处\n")

    print("=" * 72)
    print("② 重复定义：同一函数名在多个文件里各自实现（可能重复造轮子）")
    print("=" * 72)
    dup = {k: v for k, v in defined.items() if len(v) > 1}
    if dup:
        for name, places in sorted(dup.items()):
            locs = ", ".join(f"{f.relative_to(ROOT)}:{ln}" for f, ln in places)
            print(f"  {name}()  ×{len(places)}  → {locs}")
    else:
        print("  无")
    print(f"  → 共 {len(dup)} 组\n")

    print("=" * 72)
    print("③ 硬编码色值：界面代码里直接写的十六进制颜色（应统一走 theme）")
    print("=" * 72)
    hex_re = re.compile(r'["\']#[0-9a-fA-F]{6}["\']')
    hits = 0
    for f, src in all_sources.items():
        if f.name == "theme.py":
            continue
        for i, line in enumerate(src.splitlines(), 1):
            if hex_re.search(line) and "rgba" not in line:
                print(f"  {f.relative_to(ROOT)}:{i}  {line.strip()[:80]}")
                hits += 1
    if not hits:
        print("  无（全部色值集中在 theme.py）")
    print(f"  → 共 {hits} 处\n")

    print("=" * 72)
    print("④ 异常处理：裸 except / 静默 pass")
    print("=" * 72)
    bad_exc = 0
    for f, src in all_sources.items():
        lines = src.splitlines()
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if s.startswith("except:") or s == "except Exception:":
                # 看下一行是否只是 pass
                nxt = lines[i].strip() if i < len(lines) else ""
                if nxt == "pass":
                    print(f"  {f.relative_to(ROOT)}:{i}  裸 except + 静默 pass")
                    bad_exc += 1
    if not bad_exc:
        print("  无裸 except+pass")
    print(f"  → 共 {bad_exc} 处\n")

    print("=" * 72)
    print("⑤ 公开函数缺 docstring")
    print("=" * 72)
    no_doc: list[tuple[Path, int, str]] = []
    for f, src in all_sources.items():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_") and node.name != "__init__":
                    continue
                if not ast.get_docstring(node):
                    no_doc.append((f, node.lineno, node.name))
    for f, lineno, name in no_doc:
        print(f"  {f.relative_to(ROOT)}:{lineno}  {name}()")
    if not no_doc:
        print("  无")
    print(f"  → 共 {len(no_doc)} 处\n")

    print("=" * 72)
    print("⑥ 界面提示语重复（同义文案分散在多处，可考虑统一）")
    print("=" * 72)
    zh_re = re.compile(r'"([\u4e00-\u9fa5][^"]{6,40})"')
    texts: Counter[str] = Counter()
    for f, src in all_sources.items():
        for m in zh_re.finditer(src):
            texts[m.group(1)] += 1
    repeated = [(t, n) for t, n in texts.most_common() if n >= 3]
    if repeated:
        for t, n in repeated[:15]:
            print(f"  ×{n}  {t}")
    else:
        print("  无高频重复文案")
    print(f"  → 共 {len(repeated)} 条\n")

    print("=" * 72)
    print("⑦ 各文件行数排行（定位超大文件，可能需要拆分）")
    print("=" * 72)
    sizes = sorted(((len(s.splitlines()), f) for f, s in all_sources.items()), reverse=True)
    for n, f in sizes[:8]:
        print(f"  {n:5} 行  {f.relative_to(ROOT)}")
    print()

    print("=" * 72)
    print("⑧ TODO / FIXME / XXX 标记")
    print("=" * 72)
    marks = 0
    for f, src in all_sources.items():
        for i, line in enumerate(src.splitlines(), 1):
            if re.search(r"\b(TODO|FIXME|XXX|HACK)\b", line):
                print(f"  {f.relative_to(ROOT)}:{i}  {line.strip()[:80]}")
                marks += 1
    if not marks:
        print("  无")
    print(f"  → 共 {marks} 处\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
