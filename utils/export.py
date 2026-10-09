"""导出模块（V1.3 新增）：TXT 导出 + CSV 导出。

- TXT：每行一个 IP（默认导出 TOP100），文件名自动生成；
- CSV：完整字段（排名/IP/端口/TCP延迟/HTTP状态/HTTP延迟/下载速度/评分/状态），
  使用 utf-8-sig 编码，Excel 打开中文不乱码。
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

from core.ranking import RankEntry
from utils.logger import get_logger
from utils.paths import data_root

logger = get_logger()

# 输出目录：与日志目录同一个根目录（源码运行是项目根目录下的 output/，
# 打包运行是 exe 旁边的 output/），不存在时由下面的 mkdir 自动创建。
OUTPUT_DIR = data_root() / "output"

CSV_HEADERS = (
    "排名", "IP", "端口", "TCP延迟(ms)", "HTTP状态",
    "HTTP延迟(ms)", "下载速度(MB/s)", "综合评分", "状态",
)


class ExportError(Exception):
    """导出失败（磁盘不可写等），错误信息为中文。"""


def _format_speed_mbps(speed_bps: Optional[float]) -> str:
    """速度统一以 MB/s 输出到 CSV（保留 3 位小数）。"""
    if speed_bps is None:
        return ""
    return f"{speed_bps / (1024 * 1024):.3f}"


def _status_text(result) -> str:
    """生成状态列文本（与 GUI 展示口径一致）。"""
    if result.success and result.download_speed_bps is not None:
        return "成功"
    if result.http_error:
        return f"失败（{result.http_error}）"
    if result.download_error:
        return f"失败（{result.download_error}）"
    if not result.success and result.error:
        return f"失败（{result.error}）"
    return "失败" if not result.success else "成功"


def export_txt(entries: Sequence[RankEntry], top_n: int = 100) -> Path:
    """导出 TXT：只写成功 IP，每行一个，默认 TOP100。

    返回生成的文件路径；失败抛出 ExportError。
    """
    lines: List[str] = []
    for entry in entries:
        if entry.score is None:
            continue  # 只导出可评分（成功）的 IP
        if len(lines) >= top_n:
            break
        lines.append(entry.result.ip)

    if not lines:
        raise ExportError("没有可导出的成功 IP，请先完成测速")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"IP优选_TOP{top_n}_{stamp}.txt"
    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ExportError(f"写入 TXT 失败：{exc}") from exc
    logger.info("TXT 导出成功：%s（%s 个 IP）", path, len(lines))
    return path


def export_csv(
    entries: Sequence[RankEntry],
    target: Optional[Path] = None,
    filename_prefix: str = "IP优选_结果",
) -> Path:
    """导出 CSV：完整字段，utf-8-sig 编码（Excel 直接打开不乱码）。

    Args:
        entries: 要导出的排名条目。**可以是任意子集** —— 调用方自行切片后传入，
            本函数不做排名或截断，导出内容与传入顺序一一对应。
        target: 指定保存路径（用户在「另存为」对话框里选的）；
            为 None 时自动存到 output\\ 目录。
        filename_prefix: 自动命名时的文件名前缀（如「IP优选_选中」）。

    Returns:
        实际写入的文件路径。

    Raises:
        ExportError: 写盘失败。
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if target is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / f"{filename_prefix}_{stamp}.csv"
    else:
        path = target
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            writer.writerow(CSV_HEADERS)
            for entry in entries:
                result = entry.result
                rank_text = str(entry.rank) if entry.rank > 0 else ""
                writer.writerow([
                    rank_text,
                    result.ip,
                    result.port,
                    result.latency if result.latency is not None else "",
                    result.http_status if result.http_status is not None else "",
                    result.http_latency if result.http_latency is not None else "",
                    _format_speed_mbps(result.download_speed_bps),
                    entry.score if entry.score is not None else "",
                    _status_text(result),
                ])
    except OSError as exc:
        raise ExportError(f"写入 CSV 失败：{exc}") from exc
    logger.info("CSV 导出成功：%s（%s 行）", path, len(entries))
    return path


# ======================================================================
# 节点链接导出（把优选 IP 套进用户自己的代理模板）
# ======================================================================

def build_nodes_from_entries(
    entries: Sequence[RankEntry],
    template: str,
    top_n: int = 100,
) -> List[str]:
    """把测速排名结果套进代理模板，生成可用节点链接。

    与「抽样测速」页共用同一套模板机制（core.sampler）：
    模板中的 `@IP:端口` 会被替换成该条结果的 IP 与实际端口。

    Args:
        entries: 排名结果（build_ranking 的返回值）。
        template: 代理模板，必须含 `@IP:端口` 片段。
        top_n: 最多生成多少条。

    Returns:
        节点链接列表（按传入顺序，即排名顺序）。

    Raises:
        ExportError: 模板缺少 `@IP:端口` 片段。
    """
    from core.sampler import build_node, extract_template_port

    parsed = extract_template_port(template)
    if parsed is None:
        raise ExportError(
            "代理模板中未找到 @IP:端口 格式，无法生成节点。\n\n"
            "示例：vless://uuid@1.2.3.4:443?encryption=none&security=none&type=ws"
        )
    _, pair = parsed

    nodes: List[str] = []
    for entry in entries:
        if entry.score is None:
            continue          # 只导出可评分的（测速成功的）
        if len(nodes) >= top_n:
            break
        result = entry.result
        nodes.append(build_node(template, result.ip, result.port, pair))
    return nodes


def export_nodes(
    entries: Sequence[RankEntry],
    template: str,
    top_n: int = 100,
    target: Optional[Path] = None,
) -> Path:
    """导出节点链接到 txt。

    Args:
        entries: 排名结果。
        template: 代理模板。
        top_n: 最多导出条数。
        target: 指定保存路径（用户在「另存为」对话框里选的）；
                为 None 时自动存到 output\\ 目录。

    Returns:
        实际写入的文件路径。

    Raises:
        ExportError: 模板非法或没有可导出的结果或写盘失败。
    """
    nodes = build_nodes_from_entries(entries, template, top_n)
    if not nodes:
        raise ExportError("没有可导出的节点，请先完成测速（需有测速成功的 IP）")

    if target is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = OUTPUT_DIR / f"优选节点_TOP{top_n}_{stamp}.txt"

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(nodes) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ExportError(f"写入节点文件失败：{exc}") from exc
    logger.info("节点导出成功：%s（%s 条）", target, len(nodes))
    return target


def export_plain_text(content: str, target: Path) -> Path:
    """把一段文本写入指定路径（供「另存为」使用）。

    Args:
        content: 要写入的文本内容。
        target: 目标文件路径。

    Returns:
        实际写入的路径。

    Raises:
        ExportError: 写盘失败。
    """
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise ExportError(f"写入文件失败：{exc}") from exc
    logger.info("文件导出成功：%s", target)
    return target


# ======================================================================
# V1.4：稳定性复测结果的导出
# ======================================================================
STABLE_CSV_HEADERS = (
    "最终排名", "IP", "端口",
    "TCP平均延迟(ms)", "HTTP平均延迟(ms)", "平均下载速度(MB/s)",
    "TCP成功率", "HTTP成功率", "下载成功率",
    "稳定性评分", "最终评分",
)


def export_stable_txt(final_entries: Sequence, top_n: int = 100) -> Path:
    """导出稳定 TOP100 TXT：每行一个 IP（按最终排名取前 N 个）。"""
    lines: List[str] = []
    for entry in final_entries:
        if len(lines) >= top_n:
            break
        lines.append(entry.result.ip)

    if not lines:
        raise ExportError("没有可导出的稳定 IP，请先完成稳定性复测")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"IP优选_稳定TOP{top_n}_{stamp}.txt"
    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ExportError(f"写入 TXT 失败：{exc}") from exc
    logger.info("稳定 TOP TXT 导出成功：%s（%s 个 IP）", path, len(lines))
    return path


def export_stable_csv(
    final_entries: Sequence,
    target: Optional[Path] = None,
    filename_prefix: str = "IP优选_稳定性结果",
) -> Path:
    """导出稳定性复测结果 CSV：V1.4 的完整统计字段。

    Args:
        final_entries: 最终排名条目，**可以是任意子集**。
        target: 指定保存路径；为 None 时自动存到 output\\ 目录。
        filename_prefix: 自动命名时的文件名前缀。

    Returns:
        实际写入的文件路径。

    Raises:
        ExportError: 写盘失败。
    """
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if target is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / f"{filename_prefix}_{stamp}.csv"
    else:
        path = target
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            writer.writerow(STABLE_CSV_HEADERS)
            for entry in final_entries:
                data = entry.data
                writer.writerow([
                    entry.rank,
                    entry.result.ip,
                    entry.result.port,
                    f"{data.avg_tcp_latency:.0f}" if data.avg_tcp_latency is not None else "",
                    f"{data.avg_http_latency:.0f}" if data.avg_http_latency is not None else "",
                    _format_speed_mbps(data.avg_download_speed),
                    f"{data.tcp_success_rate:.0%}",
                    f"{data.http_success_rate:.0%}",
                    f"{data.download_success_rate:.0%}",
                    entry.stability_score,
                    entry.final_score,
                ])
    except OSError as exc:
        raise ExportError(f"写入 CSV 失败：{exc}") from exc
    logger.info("稳定性 CSV 导出成功：%s（%s 行）", path, len(final_entries))
    return path