"""抽样测速与节点生成核心模块。

移植自《优选IP测速_重构版.html》（浏览器版），但**测速引擎改为 Python 真实 HTTP 请求**：

- 浏览器版受 CORS 限制，用 `fetch(mode:'no-cors')` 只能测「有没有响应」；
- Python 版用真实 socket/HTTP 连接测延迟，不依赖浏览器同源策略，结果更可靠。

功能对应关系：
    sampleV4 / sampleV6        -> sample_ipv4 / sample_ipv6
    buildCandidates            -> build_candidates
    builtInEngine              -> probe_latency
    probeIp（多端口逐个试）      -> probe_ip
    buildNode / extractTemplatePort -> build_node / extract_template_port
    runRound 的并发 worker      -> SampleEngine.run_round
    updateSummary              -> summarize
"""

from __future__ import annotations

import logging
import random
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from utils.logger import get_logger

logger: logging.Logger = get_logger()

# 内置可探测端口（与浏览器版 BUILT_IN_PORTS 一致）
BUILT_IN_PORTS: Tuple[int, ...] = (
    80, 443, 2052, 2053, 2082, 2083, 2086, 2087, 2095, 2096, 8080, 8443, 8880,
)
DEFAULT_PORTS: Tuple[int, ...] = (80, 443)

# 测速源：路径与键名**逐字对齐原版 HTML**（原版 option value="cachefly"）
SPEED_SOURCES: Dict[str, str] = {
    "cloudflare": "/__down?bytes=10000000",
    "cachefly": "/50mb.test",
}
SOURCE_LABELS: Dict[str, str] = {
    "cloudflare": "Cloudflare 10MB (/__down?bytes=10000000)",
    "cachefly": "CacheFly 50MB (/50mb.test)",
}

# 默认 CIDR 网段（**逐字复制原 HTML textarea 内容**，22 段，含 7 个 IPv6 段；
# 注意：原版这 22 段里 103.21.244.0/22、104.16.0.0/13 等确有重复，属原版原样，不擅自"修正"）
DEFAULT_CIDRS: str = """103.21.244.0/22
103.22.200.0/22
103.31.4.0/22
104.16.0.0/13
104.24.0.0/14
108.162.192.0/18
131.0.72.0/22
141.101.64.0/18
162.158.0.0/15
172.64.0.0/13
173.245.48.0/20
188.114.96.0/20
190.93.240.0/20
197.234.240.0/22
198.41.128.0/17
2400:cb00::/32
2606:4700::/32
2803:f800::/32
2405:b500::/32
2405:8100::/32
2a06:98c0::/29
2c0f:f248::/32"""

# 默认代理模板（**逐字复制原 HTML textarea 内容**）
DEFAULT_TEMPLATE: str = (
    "vless://fa40fa57-9498-46db-b347-975d38f3a06a@190.93.246.162:80"
    "?encryption=none&security=none&type=ws"
    "&host=white-hat-c4f4.slo825030.workers.dev&path=%2F%3Fed%3D2048#%E8%81%94%E9%80%9A-80-WS"
)

# 默认参数（数值与取值范围**逐字对齐原 HTML input 的 value/min/max**）
DEFAULT_SAMPLE_PER_CIDR = 200
SAMPLE_PER_CIDR_MIN = 10
SAMPLE_PER_CIDR_MAX = 2000

DEFAULT_CONCURRENCY = 30
CONCURRENCY_MIN = 1
CONCURRENCY_MAX = 100

DEFAULT_TIMEOUT_MS = 100
TIMEOUT_MIN_MS = 50
# 上限 500ms：超时只是「多久算不通」，超过 500ms 才响应的节点本身已不适合使用，
# 放宽上限只会让抽样变慢而不产生有用结果（原版给到 3000 属未贴合实际使用场景）。
TIMEOUT_MAX_MS = 500

DEFAULT_KEEP_N = 20
KEEP_N_MIN = 1
KEEP_N_MAX = 300

# 延迟配色阈值（毫秒）：与浏览器版的行样式一致
FAST_MS = 100
MID_MS = 300


@dataclass
class ProbeResult:
    """一条可用的测速结果。"""

    ip: str
    port: int
    ms: float
    node: str


@dataclass
class SampleStats:
    """一轮抽样的统计摘要。"""

    candidates: int = 0          # 本轮候选 IP 数
    tested: int = 0              # 本轮已测数
    passing: int = 0             # 累计可用数
    fastest_ms: Optional[float] = None
    success_rate: Optional[float] = None      # 可用 / 已测
    avg_ms: Optional[float] = None
    port_dist: List[Tuple[int, int]] = field(default_factory=list)


# ======================================================================
# 一、IP 抽样（对应 sampleV4 / sampleV6）
# ======================================================================

def _ip_to_int(ip: str) -> int:
    """IPv4 字符串转 32 位整数。"""
    parts = [int(x) for x in ip.split(".")]
    return ((parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3]) & 0xFFFFFFFF


def _int_to_ip(value: int) -> str:
    """32 位整数转 IPv4 字符串。"""
    return ".".join(str((value >> shift) & 255) for shift in (24, 16, 8, 0))


def is_ipv6_cidr(text: str) -> bool:
    """判断是否为 IPv6 CIDR（与浏览器版 isV6 同款正则口径）。"""
    return bool(re.match(r"^([0-9a-fA-F]{1,4}:){1,7}[0-9a-fA-F]{0,4}/\d{1,3}$", text.strip()))


def sample_ipv4(cidr: str, count: int) -> List[str]:
    """从 IPv4 网段内随机抽 count 个地址（排除网络号与广播地址）。

    每次调用都重新随机，保证多轮抽测能覆盖到新 IP（与浏览器版行为一致）。

    Args:
        cidr: 形如 "104.16.0.0/13" 的网段。
        count: 抽样个数。

    Returns:
        抽到的 IP 列表；网段非法或可用地址为 0 时返回空列表。
    """
    try:
        ip_part, prefix_part = cidr.strip().split("/")
        prefix = int(prefix_part)
        octets = [int(x) for x in ip_part.split(".")]
    except (ValueError, AttributeError):
        return []
    if len(octets) != 4 or any(x < 0 or x > 255 for x in octets):
        return []
    if not 0 <= prefix <= 32:
        return []

    net = _ip_to_int(ip_part) & ((0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF if prefix else 0)
    usable = 2 ** (32 - prefix)
    real_usable = max(usable - 2, 0)
    if real_usable == 0:
        return []

    take = min(count, real_usable)
    rng = random.Random()
    first_ip = net + 1
    chosen: Set[int] = {first_ip}
    guard = 0
    while len(chosen) < take and guard < take * 20:
        offset = rng.randrange(real_usable)
        ip = net + 1 + offset
        # 末位为 0 或 255 的地址通常不可用，改成同段的 1
        if (ip & 255) in (0, 255):
            ip = (ip & 0xFFFFFF00) | 1
        chosen.add(ip)
        guard += 1
    return [_int_to_ip(x) for x in chosen]


def sample_ipv6(cidr: str, count: int) -> List[str]:
    """从 IPv6 网段生成候选（与浏览器版一致：最多 8 个，形式 base::i）。"""
    base = cidr.strip().split("/")[0].rstrip(":")
    return [f"{base}::{i}" for i in range(1, min(count, 8) + 1)]


def build_candidates(cidr_text: str, per_cidr: int) -> List[str]:
    """解析多行 CIDR 文本，为每段抽样并全局去重。

    Args:
        cidr_text: 每行一个 CIDR，支持用 # 注释、空行忽略。
        per_cidr: 每段抽样个数（最小 10，与浏览器版一致）。

    Returns:
        去重后的候选 IP 列表。
    """
    sample_n = max(10, per_cidr)
    pool: List[str] = []
    seen: Set[str] = set()
    for raw_line in cidr_text.splitlines():
        line = raw_line.split("#")[0].strip()
        if not line:
            continue
        ips = sample_ipv6(line, sample_n) if is_ipv6_cidr(line) else sample_ipv4(line, sample_n)
        for ip in ips:
            if ip not in seen:
                seen.add(ip)
                pool.append(ip)
    return pool


# ======================================================================
# 二、节点模板（对应 extractTemplatePort / buildNode）
# ======================================================================

_TEMPLATE_RE = re.compile(r"@([^:\s]+):(\d+)")


def extract_template_port(template: str) -> Optional[Tuple[str, str]]:
    """从模板中提取 `@IP:端口` 片段。

    Args:
        template: 代理链接模板。

    Returns:
        (端口字符串, 待替换的完整片段)；模板不含该格式时返回 None。
    """
    match = _TEMPLATE_RE.search(template)
    if not match:
        return None
    return match.group(2), match.group(0)


def build_node(template: str, ip: str, port: int, pair: str) -> str:
    """把模板里的 `@IP:端口` 替换为实测通过的值。"""
    return template.replace(pair, f"@{ip}:{port}")


# ======================================================================
# 三、测速引擎（对应 builtInEngine，但改用真实 TCP/HTTP 连接）
# ======================================================================

def probe_latency(ip: str, port: int, source: str, timeout_ms: int) -> float:
    """探测单个 IP:端口的延迟。

    与浏览器版的区别：浏览器受 CORS 限制只能发 no-cors 请求「看有没有响应」，
    这里用真实 TCP 连接 + HTTP 请求测量，结果更接近实际可用性。

    Args:
        ip: 目标 IP。
        port: 目标端口。
        source: 测速源键（cloudflare / custom）。
        timeout_ms: 超时毫秒数。

    Returns:
        延迟毫秒数；失败或超时返回 -1。
    """
    path = SPEED_SOURCES.get(source, SPEED_SOURCES["cloudflare"])
    timeout_s = max(timeout_ms / 1000.0, 0.05)
    start = time.perf_counter()

    # 先做 TCP 连接（能反映端口是否开放），再发一个轻量 HTTP 请求头
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout_s)
    try:
        sock.connect((ip, port))
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {ip}\r\n"
            "User-Agent: IPOptimizer/2.0\r\n"
            "Accept: */*\r\n"
            "Connection: close\r\n\r\n"
        )
        sock.sendall(request.encode("ascii", errors="ignore"))
        # 只等首个响应字节即可判定「有响应」，避免真下载 10MB
        sock.recv(1)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        if elapsed_ms >= timeout_ms:
            return -1.0
        return elapsed_ms
    except (socket.timeout, OSError, ValueError):
        return -1.0
    finally:
        try:
            sock.close()
        except OSError:
            pass


def probe_ip(
    ip: str,
    ports: Sequence[int],
    template: str,
    pair: str,
    source: str,
    timeout_ms: int,
    tested: Set[str],
) -> Optional[Tuple[float, int]]:
    """按端口顺序逐个试，命中第一个可用端口即返回。

    Args:
        ip: 目标 IP。
        ports: 待试端口列表（按顺序）。
        template: 节点模板。
        pair: 模板中待替换的片段。
        source: 测速源键。
        timeout_ms: 超时毫秒数。
        tested: 会话级已测集合（避免重复测同一个 IP:端口）。

    Returns:
        (延迟毫秒, 端口)；全部端口不可用时返回 None。
    """
    for port in ports:
        node = build_node(template, ip, port, pair)
        if node in tested:
            continue
        ms = probe_latency(ip, port, source, timeout_ms)
        tested.add(node)
        if ms >= 0:
            return ms, port
    return None


def resolve_probe_ports(selected_ports: Sequence[int], template_port: Optional[str]) -> List[int]:
    """确定实际探测的端口集合（模板端口默认优先加入）。

    Args:
        selected_ports: 用户在界面勾选的端口。
        template_port: 模板里写死的端口（可为 None）。

    Returns:
        去重并排序后的端口列表；为空时回退模板端口或 80。
    """
    ports: Set[int] = {p for p in selected_ports if 0 < p < 65536}
    if template_port:
        try:
            ports.add(int(template_port))
        except ValueError:
            pass
    if ports:
        return sorted(ports)
    if template_port:
        try:
            return [int(template_port)]
        except ValueError:
            return [80]
    return [80]


def summarize(
    passing: Sequence[ProbeResult], tested_count: int
) -> SampleStats:
    """汇总统计（对应 updateSummary）。

    Args:
        passing: 累计可用结果。
        tested_count: 会话累计已测节点数。

    Returns:
        统计摘要对象。
    """
    stats = SampleStats(passing=len(passing))
    if tested_count:
        stats.success_rate = len(passing) / max(1, tested_count) * 100.0
    if passing:
        stats.fastest_ms = min(r.ms for r in passing)
        stats.avg_ms = sum(r.ms for r in passing) / len(passing)
        counter: Dict[int, int] = {}
        for r in passing:
            counter[r.port] = counter.get(r.port, 0) + 1
        stats.port_dist = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)
    return stats


# ======================================================================
# 四、抽样引擎（对应 runRound 的并发 worker 池）
# ======================================================================

class SampleEngine:
    """抽样测速引擎：管理候选、并发探测、结果累积与去重。

    设计为**无 Qt 依赖**的纯逻辑类，便于单测；界面通过回调解耦。

    与浏览器版一致的行为：
    - 结果按延迟升序累积，不因新一轮而清空；
    - 已测过的 IP:端口 不重复测（会话级去重）；
    - 支持中途 stop。
    """

    def __init__(self) -> None:
        """初始化空引擎。"""
        self.passing: List[ProbeResult] = []
        self.tested: Set[str] = set()
        self.candidates: List[str] = []
        self._stop_flag = False

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------
    def request_stop(self) -> None:
        """请求停止当前抽样（已完成的探测结果保留）。"""
        self._stop_flag = True

    @property
    def stopping(self) -> bool:
        """是否已请求停止。"""
        return self._stop_flag

    def clear(self) -> None:
        """清空结果与已测记录（对应 sampleClear）。"""
        self.passing = []
        self.tested = set()
        self.candidates = []
        self._stop_flag = False

    def tested_count(self) -> int:
        """会话累计已测节点数。"""
        return len(self.tested)

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def run_round(
        self,
        cidr_text: str,
        per_cidr: int,
        ports: Sequence[int],
        template: str,
        source: str,
        timeout_ms: int,
        concurrency: int,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_pass: Optional[Callable[[ProbeResult], None]] = None,
    ) -> int:
        """执行一轮抽样测速。

        Args:
            cidr_text: CIDR 网段文本。
            per_cidr: 每段抽样数。
            ports: 待探测端口列表。
            template: 节点模板。
            source: 测速源键。
            timeout_ms: 单次超时毫秒。
            concurrency: 并发数。
            on_progress: 进度回调 (已测数, 总数)。
            on_pass: 每发现一个可用节点时的回调。

        Returns:
            **本轮新发现的可用节点数**（用于自动模式判断是否已抽完；
            注意不是"新测数" —— 后者的语义会让自动模式永远不判定收敛）。

        Raises:
            ValueError: 模板中找不到 `@IP:端口` 格式。
        """
        parsed = extract_template_port(template)
        if parsed is None:
            raise ValueError("模板中未找到 @IP:端口 格式，请检查代理模板")
        _, pair = parsed

        self._stop_flag = False
        self.candidates = build_candidates(cidr_text, per_cidr)
        if not self.candidates:
            return 0

        total = len(self.candidates)
        passing_before = len(self.passing)
        done_counter = {"done": 0}

        def work(ip: str) -> Optional[ProbeResult]:
            """探测单个 IP（线程池任务）。"""
            if self._stop_flag:
                return None
            hit = probe_ip(ip, ports, template, pair, source, timeout_ms, self.tested)
            if hit is None or self._stop_flag:
                return None
            ms, port = hit
            return ProbeResult(ip=ip, port=port, ms=ms, node=build_node(template, ip, port, pair))

        workers = max(1, min(int(concurrency), total))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(work, ip): ip for ip in self.candidates}
            for future in as_completed(futures):
                if self._stop_flag:
                    # 已提交的任务无法取消，直接跳出循环等线程池收尾
                    break
                done_counter["done"] += 1
                try:
                    result = future.result()
                except Exception:
                    logger.exception("探测 %s 时发生异常", futures[future])
                    result = None
                if result is not None:
                    self.passing.append(result)
                    self.passing.sort(key=lambda r: r.ms)
                    if on_pass is not None:
                        on_pass(result)
                if on_progress is not None:
                    on_progress(done_counter["done"], total)

        # 新发现的可用节点数（不是新测数）
        return max(0, len(self.passing) - passing_before)

    # ------------------------------------------------------------------
    # 复制 / 导出（对应 copyBest / copyPass / copyIp / downloadNodes）
    # ------------------------------------------------------------------
    def best_nodes(self, n: int) -> List[str]:
        """取最优 N 条的节点链接（对应 copyBest）。"""
        count = max(1, n)
        return [r.node for r in self.passing[:count]]

    def all_nodes(self) -> List[str]:
        """全部可用节点链接（对应 copyPass）。"""
        return [r.node for r in self.passing]

    def all_ips(self) -> List[str]:
        """全部可用 IP（对应 copyIp）。"""
        return [r.ip for r in self.passing]
