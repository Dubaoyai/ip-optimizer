"""验证：代理模板「输入即保存、重启能读回」（对齐原版行为）。

原版行为（HTML）：templateInput 的 input/change 事件 → persistFixed() → localStorage
本实现应等价：template_edit.textChanged → _on_template_changed → _save_prefs

本脚本**真实模拟**：输入模板 → 检查落盘 → 新建实例模拟重启 → 检查读回。

运行：
    python tests/verify_template_persist.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 隔离存储，避免污染用户真实配置
_TMP = Path(tempfile.mkdtemp(prefix="ipo_tpl_"))
os.environ["IPO_SAMPLE_PREFS"] = str(_TMP / "sample_prefs.json")
os.environ["IPO_SAMPLE_RESULTS"] = str(_TMP / "sample_results.json")

from PySide6.QtWidgets import QApplication  # noqa: E402

from gui import theme  # noqa: E402
from gui.sample_page import SamplePage  # noqa: E402
from utils.logger import ensure_runtime_dirs  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """记录检查结果。"""
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" —— {detail}" if detail else ""), flush=True)


def main() -> int:
    """验证模板持久化全链路。"""
    ensure_runtime_dirs()
    app = QApplication(sys.argv)
    theme.apply_theme(app, "dark")

    page = SamplePage()
    prefs_path = page._prefs_path()
    print(f"隔离的偏好文件：{prefs_path}\n")

    # ---------- 1. 启动时的默认模板 ----------
    default_tpl = page.template_edit.toPlainText()
    check("① 首次启动载入默认模板", "@" in default_tpl, default_tpl[:50] + "...")

    # ---------- 2. 用户输入新模板 → 立即保存 ----------
    user_tpl = (
        "vless://11111111-2222-3333-4444-555555555555@1.2.3.4:443"
        "?encryption=none&security=none&type=ws&host=my-own.workers.dev&path=%2F#我的节点"
    )
    page.template_edit.setPlainText(user_tpl)
    app.processEvents()          # 触发 textChanged

    check("② 输入后立即落盘（文件已存在）", prefs_path.exists(),
          str(prefs_path.exists()))
    if prefs_path.exists():
        data = json.loads(prefs_path.read_text(encoding="utf-8"))
        check("③ 盘上内容 = 用户输入的模板",
              data.get("template") == user_tpl,
              f"盘上：{(data.get('template') or '')[:60]}...")
    else:
        check("③ 盘上内容 = 用户输入的模板", False, "文件不存在")

    # ---------- 3. 校验提示同步 ----------
    check("④ 模板校验提示已更新（识别到端口）",
          "已识别端点" in page.template_hint.text(),
          page.template_hint.text())

    # ---------- 4. 模拟重启：新实例应读回用户模板 ----------
    fresh = SamplePage()
    app.processEvents()
    check("⑤ 重启后读回用户模板（不是默认值）",
          fresh.template_edit.toPlainText() == user_tpl,
          fresh.template_edit.toPlainText()[:60] + "...")
    check("⑤bis 读回的确实不是默认模板",
          fresh.template_edit.toPlainText() != default_tpl)

    # ---------- 5. CIDR 同样行为 ----------
    user_cidr = "104.16.0.0/13\n172.64.0.0/13"
    fresh.cidr_edit.setPlainText(user_cidr)
    app.processEvents()
    data2 = json.loads(prefs_path.read_text(encoding="utf-8"))
    check("⑥ CIDR 也是输入即保存", data2.get("cidr") == user_cidr,
          f"盘上：{(data2.get('cidr') or '')[:40]}")

    fresh3 = SamplePage()
    app.processEvents()
    check("⑦ 重启后读回 CIDR", fresh3.cidr_edit.toPlainText() == user_cidr,
          fresh3.cidr_edit.toPlainText()[:40])

    # ---------- 6. 参数也保存 ----------
    fresh3.per_cidr_spin.setValue(321)
    fresh3.timeout_spin.setValue(350)
    app.processEvents()
    data3 = json.loads(prefs_path.read_text(encoding="utf-8"))
    check("⑧ 数值参数同样输入即保存",
          data3.get("per_cidr") == 321 and data3.get("timeout") == 350,
          f"{data3.get('per_cidr')}/{data3.get('timeout')}")

    # ---------- 7. 与用户的真实配置互不影响（隔离验证） ----------
    from utils.paths import data_root

    real = data_root() / "sample_prefs.json"
    check("⑨ 测试未污染用户真实配置",
          not real.exists() or str(real) != str(prefs_path),
          f"真实路径 {real}（测试用的是 {prefs_path}）")

    print()
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"模板持久化验证：{passed}/{total} 通过")
    if passed < total:
        print("失败项：")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}  {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
