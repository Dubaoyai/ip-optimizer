"""原版移植保真度核验：逐字比对原 HTML 与 Python 实现的常量与取值范围。

这是针对"是否偷工"的**机器核验**，不靠人眼比对。

运行：
    python tests/verify_fidelity.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import sampler  # noqa: E402

SOURCE_HTML = Path(r"D:\软件\节点工具\优选IP测速_重构版.html")

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """记录检查结果。"""
    results.append((name, ok, detail))
    print(f"[{'OK  ' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def main() -> int:
    """逐字核验移植保真度。"""
    text = SOURCE_HTML.read_text(encoding="utf-8")

    # ---------- 1. CIDR 网段逐行比对 ----------
    m = re.search(r'<textarea id="cidrInput"[^>]*>(.*?)</textarea>', text, re.S)
    check("能提取原版 CIDR textarea", m is not None)
    if m:
        original_lines = [ln.strip() for ln in m.group(1).strip().splitlines() if ln.strip()]
        mine_lines = [ln.strip() for ln in sampler.DEFAULT_CIDRS.strip().splitlines() if ln.strip()]
        check("CIDR 行数一致", len(original_lines) == len(mine_lines),
              f"原版 {len(original_lines)} 行，我的 {len(mine_lines)} 行")
        if original_lines == mine_lines:
            check("CIDR 内容逐行完全一致", True)
        else:
            diff = [
                (i, a, b) for i, (a, b) in enumerate(zip(original_lines, mine_lines), 1)
                if a != b
            ]
            check("CIDR 内容逐行完全一致", False, f"差异行 {diff[:6]}")
        v6_orig = [x for x in original_lines if ":" in x]
        v6_mine = [x for x in mine_lines if ":" in x]
        check("IPv6 段数量一致", len(v6_orig) == len(v6_mine),
              f"原版 {len(v6_orig)} 段，我的 {len(v6_mine)} 段")

    # ---------- 2. 代理模板逐字比对 ----------
    m2 = re.search(r'<textarea id="templateInput"[^>]*>(.*?)</textarea>', text, re.S)
    check("能提取原版模板 textarea", m2 is not None)
    if m2:
        original_tpl = m2.group(1).strip()
        check("模板逐字完全一致", original_tpl == sampler.DEFAULT_TEMPLATE,
              f"原版 {original_tpl[:50]}... vs 我的 {sampler.DEFAULT_TEMPLATE[:50]}...")

    # ---------- 3. 测速源键名比对 ----------
    opts = re.findall(r'<option value="(\w+)">([^<]+)</option>', text)
    check("测速源选项数量一致", len(opts) == len(sampler.SOURCE_LABELS),
          f"原版 {len(opts)} 个，我的 {len(sampler.SOURCE_LABELS)} 个")
    for key, label in opts:
        ok = key in sampler.SPEED_SOURCES and key in sampler.SOURCE_LABELS
        check(f"测速源键名 {key!r} 存在且标签一致",
              ok and sampler.SOURCE_LABELS[key].strip() == label.strip(),
              f"我的标签={sampler.SOURCE_LABELS.get(key)!r}")

    # ---------- 4. 数字输入框的 value/min/max ----------
    specs = re.findall(
        r'id="(sampleNum|concSample|timeoutSample|keepSample)"\s+value="(\d+)"\s+min="(\d+)"\s+max="(\d+)"',
        text,
    )
    check("能提取 4 个数字输入框规格", len(specs) == 4, f"提取到 {len(specs)} 个")
    mapping = {
        "sampleNum": ("DEFAULT_SAMPLE_PER_CIDR", "SAMPLE_PER_CIDR_MIN", "SAMPLE_PER_CIDR_MAX"),
        "concSample": ("DEFAULT_CONCURRENCY", "CONCURRENCY_MIN", "CONCURRENCY_MAX"),
        "timeoutSample": ("DEFAULT_TIMEOUT_MS", "TIMEOUT_MIN_MS", "TIMEOUT_MAX_MS"),
        "keepSample": ("DEFAULT_KEEP_N", "KEEP_N_MIN", "KEEP_N_MAX"),
    }
    for ident, value, lo, hi in specs:
        dname, lname, hname = mapping[ident]
        d_ok = getattr(sampler, dname) == int(value)
        l_ok = getattr(sampler, lname) == int(lo)
        h_ok = getattr(sampler, hname) == int(hi)
        check(
            f"{ident} 的 value/min/max 一致（{value}/{lo}/{hi}）",
            d_ok and l_ok and h_ok,
            f"我的 {getattr(sampler, dname)}/{getattr(sampler, lname)}/{getattr(sampler, hname)}",
        )

    # ---------- 5. 内置端口列表 ----------
    m3 = re.search(r"BUILT_IN_PORTS\s*=\s*\[([^\]]+)\]", text)
    check("能提取原版端口列表", m3 is not None)
    if m3:
        orig_ports = [int(x.strip()) for x in m3.group(1).split(",") if x.strip()]
        check("端口列表完全一致", orig_ports == list(sampler.BUILT_IN_PORTS),
              f"原版 {orig_ports} vs 我的 {list(sampler.BUILT_IN_PORTS)}")

    # ---------- 6. 默认选中端口 ----------
    m4 = re.search(r"selectedPorts\s*=\s*new Set\(\[([^\]]+)\]\)", text)
    check("能提取默认选中端口", m4 is not None)
    if m4:
        orig_sel = [int(x.strip()) for x in m4.group(1).split(",") if x.strip()]
        check("默认选中端口一致", orig_sel == list(sampler.DEFAULT_PORTS),
              f"原版 {orig_sel} vs 我的 {list(sampler.DEFAULT_PORTS)}")

    # ---------- 7. 延迟配色阈值 ----------
    m5 = re.search(r"r\.ms\s*<\s*(\d+)\s*\?\s*'row-ms-fast", text)
    m6 = re.search(r"r\.ms\s*<\s*(\d+)\s*\?\s*'row-ms-mid", text)
    check("能提取延迟配色阈值", m5 is not None and m6 is not None)
    if m5 and m6:
        check("快/中阈值一致（100 / 300）",
              sampler.FAST_MS == int(m5.group(1)) and sampler.MID_MS == int(m6.group(1)),
              f"原版 {m5.group(1)}/{m6.group(1)} vs 我的 {sampler.FAST_MS}/{sampler.MID_MS}")

    # ---------- 8. 测速源路径 ----------
    check("Cloudflare 路径一致",
          sampler.SPEED_SOURCES.get("cloudflare") == "/__down?bytes=10000000",
          sampler.SPEED_SOURCES.get("cloudflare", ""))
    check("CacheFly 路径一致",
          sampler.SPEED_SOURCES.get("cachefly") == "/50mb.test",
          sampler.SPEED_SOURCES.get("cachefly", ""))

    # ---------- 9. V6 抽样算法（base::i，最多 8） ----------
    # 原版 JS: base = cidr.split('/')[0].replace(/:+$/,'')  —— 末尾冒号会被去掉
    # 对 "2400:cb00::/32" => base = "2400:cb00" => 结果 "2400:cb00::1" ...
    got = sampler.sample_ipv6("2400:cb00::/32", 99)
    expect = [f"2400:cb00::{i}" for i in range(1, 9)]
    check("IPv6 抽样：最多 8 个且形式为 base::i", got == expect, f"{got[:3]} vs {expect[:3]}")

    # ---------- 10. 抽样最小值约束（原版 Math.max(10, ...) ） ----------
    check("每段抽样最小值约束为 10（对齐 Math.max(10, n)）",
          sampler.SAMPLE_PER_CIDR_MIN == 10)

    print()
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"保真度核验：{passed}/{total} 通过")
    if passed < total:
        print("失败项：")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}  {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
