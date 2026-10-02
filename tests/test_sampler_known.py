"""抽样模块的已知答案测试（自写工具投产前必须先验）。

每一项都用可手工核对的期望值，避免"工具本身就错、还拿它验对象"。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.sampler import (  # noqa: E402
    build_candidates,
    build_node,
    extract_template_port,
    resolve_probe_ports,
    sample_ipv4,
    sample_ipv6,
    summarize,
    _int_to_ip,
    _ip_to_int,
    ProbeResult,
)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """记录一项检查。"""
    results.append((name, ok, detail))
    print(f"[{'OK  ' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def main() -> int:
    """执行全部已知答案测试。"""
    # ---- 1. IP 整数往返 ----
    for ip in ("0.0.0.0", "192.168.1.1", "255.255.255.255", "104.16.0.1"):
        check(f"IP 整数往返 {ip}", _int_to_ip(_ip_to_int(ip)) == ip,
              _int_to_ip(_ip_to_int(ip)))

    # ---- 2. /24 抽样：数量、范围、去重 ----
    ips = sample_ipv4("104.16.0.0/24", 50)
    net, bcast = _ip_to_int("104.16.0.0"), _ip_to_int("104.16.0.255")
    check("抽样数量 = 50", len(ips) == 50, f"实际 {len(ips)}")
    check("全部落在网段内（排除网络号/广播号）",
          all(net < _ip_to_int(x) < bcast for x in ips))
    check("无重复", len(set(ips)) == 50, f"唯一 {len(set(ips))}")

    # ---- 3. /30 只有 2 个可用地址 ----
    ips30 = sample_ipv4("10.0.0.0/30", 100)
    check("/30 可用数 = 2", len(ips30) == 2, str(ips30))

    # ---- 4. /31 与 /32 可用数为 0（无可用主机） ----
    check("/32 可用数 = 0", len(sample_ipv4("10.0.0.1/32", 10)) == 0)
    check("/31 可用数 = 0", len(sample_ipv4("10.0.0.0/31", 10)) == 0)

    # ---- 5. 非法输入不崩溃 ----
    for bad in ("", "abc", "1.2.3", "1.2.3.4.5", "999.1.1.1/24", "1.2.3.4/99"):
        out = sample_ipv4(bad, 10)
        check(f"非法输入不崩溃: {bad!r}", out == [], f"返回 {len(out)} 条")

    # ---- 6. IPv6 抽样 ----
    v6 = sample_ipv6("2400:cb00::/32", 100)
    check("IPv6 最多 8 个", len(v6) == 8, str(v6[:2]))

    # ---- 7. 多段构建与去重 ----
    pool = build_candidates("104.16.0.0/24\n104.16.0.0/24\n# 注释行\n\n10.0.0.0/30", 10)
    check("多段构建去重（同段写两次不重复）", len(pool) == len(set(pool)), f"共 {len(pool)} 条")
    check("忽略注释与空行", len(pool) > 0)

    # ---- 8. 模板解析 ----
    tpl = "vless://uuid@1.2.3.4:807?x=1"
    parsed = extract_template_port(tpl)
    check("模板解析出端口 807", parsed is not None and parsed[0] == "807",
          str(parsed))
    check("模板解析出完整片段", parsed is not None and parsed[1] == "@1.2.3.4:807",
          str(parsed))
    check("模板无 @IP:端口 时返回 None", extract_template_port("vless://no-endpoint") is None)

    # ---- 9. 节点生成 ----
    node = build_node(tpl, "9.9.9.9", 443, "@1.2.3.4:807")
    check("节点生成正确替换", node == "vless://uuid@9.9.9.9:443?x=1", node)

    # ---- 10. 端口解析 ----
    check("端口合并（选 80,443 + 模板 807）",
          resolve_probe_ports([80, 443], "807") == [80, 443, 807],
          str(resolve_probe_ports([80, 443], "807")))
    check("端口过滤非法值（0 与 70000 被剔除）",
          resolve_probe_ports([0, 70000, 443], None) == [443],
          str(resolve_probe_ports([0, 70000, 443], None)))
    check("端口全空时回退模板端口",
          resolve_probe_ports([], "8443") == [8443],
          str(resolve_probe_ports([], "8443")))
    check("端口全空且无模板时回退 80",
          resolve_probe_ports([], None) == [80])

    # ---- 11. 统计汇总 ----
    passing = [
        ProbeResult(ip="1.1.1.1", port=443, ms=50.0, node="n1"),
        ProbeResult(ip="1.1.1.2", port=443, ms=150.0, node="n2"),
        ProbeResult(ip="1.1.1.3", port=80, ms=100.0, node="n3"),
    ]
    st = summarize(passing, tested_count=10)
    check("统计：最快延迟 = 50", st.fastest_ms == 50.0, str(st.fastest_ms))
    check("统计：平均延迟 = 100", st.avg_ms == 100.0, str(st.avg_ms))
    check("统计：成功率 = 30%", st.success_rate == 30.0, str(st.success_rate))
    check("统计：端口分布首位 = 443×2", st.port_dist[0] == (443, 2), str(st.port_dist))

    print()
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"已知答案测试：{passed}/{total} 通过")
    if passed < total:
        print("失败项：")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}  {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
