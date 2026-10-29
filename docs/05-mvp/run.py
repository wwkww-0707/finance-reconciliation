#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
对账差异定位台 · 最小 MVP 入口

用法：
    python run.py                  # 跑一次离线回放，导出结果并生成静态复核台
    python run.py --regen          # 重新生成合成样本（固定随机种子，结果可复现）
    python run.py --serve          # 启动本地复核台（默认 http://127.0.0.1:8787）
    python run.py --serve --port 9000
    python run.py --n 2000         # 调整样本规模
"""

from __future__ import annotations

import argparse
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from recon import config as C          # noqa: E402
from recon import pipeline, report     # noqa: E402

DATA_DIR = os.path.join(BASE_DIR, "sample", "data")
OUT_DIR = os.path.join(BASE_DIR, "sample", "out")


def banner():
    print("=" * 74)
    print(" %s" % C.PROJECT)
    print(" 渠道 %s · 结算日 %s · 资料版本 v%s · 只读模式（不产生任何资金操作）"
          % (C.CHANNEL, C.SETTLE_DATE, C.SNAPSHOT_VERSION))
    print("=" * 74)


def main(argv=None):
    ap = argparse.ArgumentParser(description="对账差异定位台（离线回放）")
    ap.add_argument("--serve", action="store_true", help="启动本地复核台")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--regen", action="store_true", help="重新生成合成样本")
    ap.add_argument("--n", type=int, default=1100, help="基础交易笔数（默认 1100）")
    ap.add_argument("--no-browser", action="store_true", help="启动服务时不打开浏览器")
    args = ap.parse_args(argv)

    if args.regen or not os.path.exists(os.path.join(DATA_DIR, "内部流水_ledger.csv")):
        from recon import datagen
        s = datagen.generate(DATA_DIR, n_base=args.n)
        print("已生成合成样本：内部流水 %d 笔 / 渠道结算 %d 行 / 退款 %d 笔"
              % (s["ledger_rows"], s["channel_rows"], s["refund_rows"]))

    if args.serve:
        from recon.server import serve
        serve(args.port, open_browser=not args.no_browser)
        return 0

    banner()
    st = pipeline.run(DATA_DIR, regenerate=False)
    os.makedirs(OUT_DIR, exist_ok=True)
    pipeline.export(st, OUT_DIR)

    html = report.render(st)
    html_path = os.path.join(BASE_DIR, "sample", "out", "差异定位复核台.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    k = st["kpi"]
    print("\n[匹配]")
    for m in st["match"]["method_stats"]:
        print("   %-16s %5d" % (m["label"], m["count"]))
    print("\n[指标]")
    for item in k["kpi"]:
        print("   %-22s %-10s %s" % (item["label"], item["value"], item["hint"]))
    print("\n[差异分布]")
    for code, n in sorted(k["by_code"].items(), key=lambda x: -x[1]):
        print("   %s %-18s %4d 笔" % (code, C.REASON_CODES[code][0], n))
    print("\n[审计] 哈希链 %d 条 · 校验 %s"
          % (st["audit"]["total"], "通过" if st["audit"]["check"]["ok"] else "失败"))
    print("\n输出：")
    print("   报告 %s" % html_path)
    print("   明细 %s" % OUT_DIR)
    print("\n打开报告或执行 `python run.py --serve` 进入交互复核台。")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
