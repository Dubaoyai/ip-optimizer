"""节点可用性独立验证：证明抽出来的节点是真能用的（不是假数据）。

验证手段**独立于抽样引擎**：
1. 裸 socket 三次握手（自己计时，不看引擎的 ms）；
2. 真实 HTTP GET（CF 测速端点），检查是否真返回响应；
3. 用节点模板生成链接，检查格式是否能被 V2Ray 解析。

运行：
    python tests/verify_nodes_live.py
"""

from __future__ import annotations

import http.client
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.sampler import DEFAULT_TEMPLATE, SampleEngine, build_node  # noqa: E402
from utils.logger import ensure_runtime_dirs  # noqa: E402


def probe_raw(ip: str, port: int, timeout: float = 2.0) -> float:
    """裸 socket 握手计时（独立于引擎实现）。

    Args:
        ip: 目标 IP。
        port: 目标端口。
        timeout: 超时秒数。

    Returns:
        握手毫秒数；失败返回 -1。
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        start = time.perf_counter()
        sock.connect((ip, port))
        return (time.perf_counter() - start) * 1000.0
    except OSError:
        return -1.0
    finally:
        try:
            sock.close()
        except OSError:
            pass


def probe_http(ip: str, port: int, timeout: float = 2.0):
    """真实 HTTP 请求（检查是否真返回响应）。

    Args:
        ip: 目标 IP。
        port: 目标端口。
        timeout: 超时秒数。

    Returns:
        (状态码, 读到的字节数, 耗时毫秒)；失败返回 (None, 0, -1)。
    """
    try:
        conn = http.client.HTTPConnection(ip, port, timeout=timeout)
        start = time.perf_counter()
        conn.request(
            "GET", "/__down?bytes=1000",
            headers={"Host": ip, "User-Agent": "IPOptimizer-Verify/1.0"},
        )
        resp = conn.getresponse()
        status = resp.status
        data = resp.read(64)
        elapsed = (time.perf_counter() - start) * 1000.0
        conn.close()
        return status, len(data), elapsed
    except Exception:
        return None, 0, -1.0


def main() -> int:
    """抽样 + 独立验活。"""
    ensure_runtime_dirs()

    print("=" * 70)
    print("步骤 1：用真实 Cloudflare 网段抽样（引擎跑一轮）")
    print("=" * 70)
    engine = SampleEngine()
    t0 = time.time()
    fresh = engine.run_round(
        cidr_text="104.16.0.0/13",
        per_cidr=30,
        ports=[443, 80],
        template=DEFAULT_TEMPLATE,
        source="cloudflare",
        timeout_ms=500,
        concurrency=15,
    )
    print(f"耗时 {time.time() - t0:.1f}s")
    print(f"候选 {len(engine.candidates)} 个，已测 {engine.tested_count()} 个，可用 {fresh} 个")
    print()

    if not engine.passing:
        print("未抽到可用节点，无法继续验证")
        return 1

    print("=" * 70)
    print("步骤 2：独立验活（裸 socket + 真实 HTTP GET，不用引擎的结论）")
    print("=" * 70)
    ok_count = 0
    checked = engine.passing[:8]
    for rec in checked:
        hs = probe_raw(rec.ip, rec.port)
        status, nbytes, rt = probe_http(rec.ip, rec.port)
        if hs > 0 and status is not None:
            ok_count += 1
            verdict = "可用"
        else:
            verdict = "不可用"
        print(
            f"  {rec.ip}:{rec.port:<5} "
            f"引擎报 {rec.ms:6.0f}ms | "
            f"裸握手 {hs:6.0f}ms | "
            f"HTTP {status} ({nbytes}字节, {rt:.0f}ms) -> {verdict}"
        )
    print()

    print("=" * 70)
    print("步骤 3：节点链接格式检查（能否被 V2Ray 类客户端解析）")
    print("=" * 70)
    sample = engine.passing[0]
    node = sample.node
    checks = [
        ("以 vless:// 开头", node.startswith("vless://")),
        ("含 UUID", "@" in node and len(node.split("://")[1].split("@")[0]) >= 32),
        ("含实测 IP", sample.ip in node),
        ("含实测端口", f":{sample.port}" in node),
        ("含 type=ws", "type=ws" in node),
        ("含 host 参数", "host=" in node),
        ("含备注 #", "#" in node),
    ]
    for name, passed in checks:
        print(f"  [{'OK  ' if passed else 'FAIL'}] {name}")
    print()
    print(f"示例节点：{node[:100]}...")
    print()

    print("=" * 70)
    print(f"结论：抽查 {len(checked)} 个节点，独立验活通过 {ok_count} 个")
    print("=" * 70)
    return 0 if ok_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
