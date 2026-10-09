"""utils/export.py 的单元测试（V1.3）。"""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import utils.export as export_mod  # noqa: E402
from core.ranking import build_ranking  # noqa: E402
from core.tcp_tester import TestResult  # noqa: E402
from utils.export import CSV_HEADERS, ExportError, export_csv, export_txt  # noqa: E402


def make_result(ip="104.16.0.1", success=True, tcp_ms=80, http_ms=200,
                speed_bps=1 * 1024 * 1024, status=200) -> TestResult:
    return TestResult(
        ip=ip, port=443, latency=tcp_ms, success=success, error=None,
        http_tested=True, http_success=True,
        http_status=status, http_latency=http_ms, http_error=None,
        download_tested=True, download_success=True,
        download_speed_bps=speed_bps, download_bytes=1024 * 1024,
        download_elapsed_ms=1000, download_error=None,
    )


def make_failed(ip="9.9.9.9") -> TestResult:
    return TestResult(ip=ip, port=443, latency=None, success=False, error="timeout")


class TempOutputDirTest(unittest.TestCase):
    """把输出目录临时指到 temp 目录，避免测试污染真实 output/。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_dir = export_mod.OUTPUT_DIR
        export_mod.OUTPUT_DIR = Path(self._tmp.name)

    def tearDown(self) -> None:
        export_mod.OUTPUT_DIR = self._old_dir
        self._tmp.cleanup()


class TestTxtExport(TempOutputDirTest):
    """TXT 导出。"""

    def test_txt_one_ip_per_line(self) -> None:
        """TXT 每行一个 IP，且只包含成功 IP。"""
        results = [
            make_result("104.16.0.1"),
            make_failed("9.9.9.9"),
            make_result("104.16.0.2"),
        ]
        ranking = build_ranking(results, top_n=None)
        path = export_txt(ranking, top_n=100)

        text = path.read_text(encoding="utf-8")
        lines = [line for line in text.splitlines() if line.strip()]
        self.assertEqual(lines, ["104.16.0.1", "104.16.0.2"])

    def test_txt_respects_top_n(self) -> None:
        """TXT 遵守 TOP N 限制。"""
        results = [make_result(f"104.16.0.{i}") for i in range(1, 21)]
        ranking = build_ranking(results, top_n=None)
        path = export_txt(ranking, top_n=10)
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(lines), 10)

    def test_txt_filename_format(self) -> None:
        """文件名格式：IP优选_TOP100_日期时间.txt。"""
        ranking = build_ranking([make_result()], top_n=None)
        path = export_txt(ranking, top_n=100)
        self.assertTrue(path.name.startswith("IP优选_TOP100_"))
        self.assertTrue(path.name.endswith(".txt"))

    def test_txt_empty_raises(self) -> None:
        """没有任何成功 IP 时报中文错误。"""
        ranking = build_ranking([make_failed()], top_n=None)
        with self.assertRaises(ExportError):
            export_txt(ranking)


class TestCsvExport(TempOutputDirTest):
    """CSV 导出。"""

    def test_csv_headers_complete(self) -> None:
        """CSV 表头字段完整（9 列）。"""
        self.assertEqual(CSV_HEADERS, (
            "排名", "IP", "端口", "TCP延迟(ms)", "HTTP状态",
            "HTTP延迟(ms)", "下载速度(MB/s)", "综合评分", "状态",
        ))

    def test_csv_rows_complete(self) -> None:
        """CSV 每行 9 个字段，含失败 IP（评分为空）。"""
        results = [
            make_result("104.16.0.1", tcp_ms=82, http_ms=120, speed_bps=int(0.54 * 1024 * 1024)),
            make_failed("9.9.9.9"),
        ]
        ranking = build_ranking(results, top_n=None)
        path = export_csv(ranking)

        with path.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))

        self.assertEqual(rows[0], list(CSV_HEADERS))
        self.assertEqual(len(rows), 3)  # 表头 + 2 行
        success_row = rows[1]
        self.assertEqual(success_row[0], "1")
        self.assertEqual(success_row[1], "104.16.0.1")
        self.assertEqual(success_row[2], "443")
        self.assertEqual(success_row[3], "82")
        self.assertEqual(success_row[4], "200")
        self.assertEqual(success_row[5], "120")
        self.assertEqual(success_row[6], "0.540")
        self.assertTrue(success_row[7].isdigit())
        self.assertEqual(success_row[8], "成功")
        failed_row = rows[2]
        self.assertEqual(failed_row[7], "")  # 失败 IP 无评分
        self.assertIn("失败", failed_row[8])

    def test_csv_utf8_sig(self) -> None:
        """CSV 使用 utf-8-sig 编码（Excel 中文不乱码）。"""
        ranking = build_ranking([make_result()], top_n=None)
        path = export_csv(ranking)
        raw = path.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))


class TestCsvSubsetExport(TempOutputDirTest):
    """CSV 子集导出（2026-10-09 新增：导出选中行）。

    背景：此前 export_csv 不接受任何子集参数，用户挑出几行只能
    全量导出再手工删 —— 这是「导出结果处理不方便」的机器可证根因。
    """

    def _ranking(self, count: int = 5):
        results = [make_result(f"104.16.0.{i}", tcp_ms=50 + i) for i in range(1, count + 1)]
        return build_ranking(results, top_n=None)

    def test_subset_exports_only_given_entries(self) -> None:
        """传入子集时，只导出该子集，不夹带其它行。"""
        ranking = self._ranking(5)
        subset = [ranking[0], ranking[2]]  # 挑第 1、3 条
        path = export_csv(subset)

        with path.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(len(rows), 3)  # 表头 + 2 行
        self.assertEqual(rows[1][1], "104.16.0.1")
        self.assertEqual(rows[2][1], "104.16.0.3")

    def test_subset_preserves_given_order(self) -> None:
        """导出顺序 == 传入顺序（不重排、不按排名排序）。"""
        ranking = self._ranking(5)
        reversed_subset = list(reversed(ranking))
        path = export_csv(reversed_subset)

        with path.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))
        ip_column = [row[1] for row in rows[1:]]
        self.assertEqual(ip_column, ["104.16.0.5", "104.16.0.4", "104.16.0.3",
                                     "104.16.0.2", "104.16.0.1"])

    def test_target_path_respected(self) -> None:
        """指定 target 时写到该路径，而不是自动命名到 output/。"""
        ranking = self._ranking(3)
        target = Path(self._tmp.name) / "自定义" / "选中结果.csv"
        path = export_csv(ranking[:1], target=target)

        self.assertEqual(path, target)
        self.assertTrue(target.exists())

    def test_filename_prefix_used_when_auto_naming(self) -> None:
        """不指定 target 时，用 filename_prefix 生成文件名。"""
        ranking = self._ranking(2)
        path = export_csv(ranking, filename_prefix="IP优选_选中")
        self.assertTrue(path.name.startswith("IP优选_选中_"))
        self.assertTrue(path.name.endswith(".csv"))

    def test_single_entry_subset(self) -> None:
        """只选 1 行也能正常导出（边界：最小子集）。"""
        ranking = self._ranking(3)
        path = export_csv(ranking[1:2])
        with path.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][1], "104.16.0.2")

    def test_empty_subset_writes_header_only(self) -> None:
        """空子集只写表头，不抛异常（调用方应在 GUI 层拦截空选中）。"""
        path = export_csv([])
        with path.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(rows, [list(CSV_HEADERS)])


if __name__ == "__main__":
    unittest.main(verbosity=2)