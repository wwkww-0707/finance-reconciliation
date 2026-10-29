# -*- coding: utf-8 -*-
"""
指标计算（口径写死并可输出到报告）。

必须同时给出两个口径，否则“99.9%”永远说不清：
  · 口径 A（验收口径）：分母 = 进入自动匹配的结算行，排除修复队列与低置信转人工
  · 口径 B（全量口径）：分母 = 全部结算行，转人工一律不计为正确
管理者引用 99.9% 时用 A，风险复核时看 B——两个数都要能复现（对齐 f42 / f53）。
"""

from __future__ import annotations

from . import config as C


def compute(summary: dict, quality: dict, match: dict, diffs: list, tickets: list,
            timings: dict) -> dict:
    total = summary["channel_rows"]
    results = match["results"]

    repair = len([r for r in results if r["method"] == "质控拦截"])
    low_conf = len([r for r in results if r["reason_code"] == "D10"])
    denom = total - repair - low_conf

    # 口径 A：参与自动匹配的结算行
    part = [r for r in results if r["method"] not in ("质控拦截",) and r["reason_code"] != "D10"]
    correct_a = len([r for r in part if r["reason_code"] == r["truth"]])
    accuracy_a = correct_a / denom if denom else 0.0

    # 口径 B：全量（转人工计为未命中）
    correct_b = len([r for r in results if r["reason_code"] == r["truth"]])
    accuracy_b = correct_b / total if total else 0.0

    explained = len([d for d in diffs if d["explained"]])
    unexplained = len(diffs) - explained

    by_code = {}
    for d in diffs:
        by_code.setdefault(d["reason_code"], 0)
        by_code[d["reason_code"]] += 1

    auto_concluded = len([r for r in results
                          if r["reason_code"] != "D10" and r["method"] != "质控拦截"
                          and r["reason_code"] != "D08"])
    ok_rows = len([r for r in results if r["reason_code"] == "OK"])

    kpi = [
        {"key": "分母", "label": "参与自动匹配", "value": "%d 笔" % denom,
         "hint": "全量 %d 笔 − 修复队列 %d − 低置信 %d" % (total, repair, low_conf)},
        {"key": "准确率A", "label": "匹配准确率（验收口径）", "value": "%.2f%%" % (accuracy_a * 100),
         "hint": "%d / %d，目标 99.90%%" % (correct_a, denom), "flag": accuracy_a >= 0.999},
        {"key": "准确率B", "label": "匹配准确率（全量口径）", "value": "%.2f%%" % (accuracy_b * 100),
         "hint": "转人工 %d 笔计入未命中，用于风险复核" % (repair + low_conf)},
        {"key": "覆盖率", "label": "可查原因覆盖率", "value": "%.1f%%" % (explained * 100.0 / len(diffs) if diffs else 100.0),
         "hint": "未解释差异 %d 笔（目标 0）" % unexplained, "flag": unexplained == 0},
        {"key": "差异", "label": "差异笔数", "value": "%d 笔" % len(diffs),
         "hint": "其中转人工 %d 单" % len(tickets)},
        {"key": "自动率", "label": "自动出结论率", "value": "%.1f%%" % (auto_concluded * 100.0 / total if total else 0),
         "hint": "含正常匹配 %d 笔，不含需人工判定的差异" % ok_rows},
    ]

    # 六节点耗时：系统实测 vs 访谈基线（基线明确标注为假设）
    node_rows = []
    for code, name in C.NODES:
        ms = timings.get(code)
        node_rows.append({
            "code": code,
            "name": name,
            "system_ms": ms,
            "system_text": (("%.1f ms" % ms) if ms >= 0.1 else "<0.1 ms") if ms is not None else "人工环节",
            "baseline": C.BASELINE[code],
            "mode": "系统自动" if ms is not None else "人工（保留）",
        })

    return {
        "total_rows": total,
        "repair_count": repair,
        "low_conf_count": low_conf,
        "denominator": denom,
        "correct_a": correct_a,
        "accuracy_a": accuracy_a,
        "correct_b": correct_b,
        "accuracy_b": accuracy_b,
        "explained": explained,
        "unexplained": unexplained,
        "by_code": by_code,
        "tickets": len(tickets),
        "kpi": kpi,
        "nodes": node_rows,
        "spec": C.METRIC_SPEC,
        "target": 0.999,
    }
