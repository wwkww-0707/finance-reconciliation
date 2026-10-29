# -*- coding: utf-8 -*-
"""
流水线编排：归集 → 质量校验 → 匹配 → 差异定位 → 兜底分派 → 指标 → 审计。

只读原则：全流程不写任何业务系统，不产生退款/调账/划转动作（f32/f52）。
"""

from __future__ import annotations

import csv
import json
import os
import time

from . import audit, config as C, datagen, differ, escalate, matcher, metrics, quality


def _load(path: str) -> list:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _to_int(rows: list, fields=("gross_cents", "fee_cents", "net_cents")) -> None:
    for r in rows:
        for k in fields:
            if k in r and r[k] != "":
                r[k] = int(r[k])


def run(data_dir: str, regenerate: bool = True) -> dict:
    """执行一次完整离线回放，返回可直接渲染的状态字典。"""
    os.makedirs(data_dir, exist_ok=True)
    ledger_csv = os.path.join(data_dir, "内部流水_ledger.csv")

    if regenerate or not os.path.exists(ledger_csv):
        summary = datagen.generate(data_dir)

    timings = {}

    # ---- N1 流水归集（读取并规整四类材料）----
    t = time.perf_counter()
    ledger = _load(ledger_csv)
    channel = _load(os.path.join(data_dir, "渠道结算_%s.csv" % C.CHANNEL))
    refunds = _load(os.path.join(data_dir, "退款事件_refunds.csv"))
    sources = _load(os.path.join(data_dir, "数据源快照_sources.csv"))
    _to_int(ledger)
    _to_int(channel)
    n_ledger, n_channel = len(ledger), len(channel)
    timings["N1"] = (time.perf_counter() - t) * 1000

    # ---- 质量校验（前置，不进 N2） ----
    t = time.perf_counter()
    q = quality.run_check(ledger, channel, sources)
    quality_ms = (time.perf_counter() - t) * 1000

    # ---- N2 渠道账单匹配 ----
    t = time.perf_counter()
    m = matcher.run_match(ledger, channel, refunds, q["blocked_rows"])
    timings["N2"] = (time.perf_counter() - t) * 1000

    # ---- N3 差异定位 ----
    t = time.perf_counter()
    diffs = differ.build_diffs(m, q, sources)
    timings["N3"] = (time.perf_counter() - t) * 1000

    # ---- N4 兜底分派（系统发单，人工接手） ----
    tickets = escalate.build_tickets(diffs)

    # ---- 审计留痕 ----
    chain = audit.seed_from_diffs(diffs)
    chain_check = audit.verify(chain)

    # ---- 指标 ----
    summary = {"ledger_rows": n_ledger, "channel_rows": n_channel,
               "refund_rows": len(refunds), "sources": sources}
    kpi = metrics.compute(summary, q, m, diffs, tickets, timings)

    state = {
        "meta": {
            "project": C.PROJECT,
            "channel": C.CHANNEL,
            "settle_date": C.SETTLE_DATE,
            "snapshot_version": C.SNAPSHOT_VERSION,
            "rule_version": C.LATEST_RULE_VERSION,
            "sources": sources,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "quality_ms": round(quality_ms, 1),
        },
        "summary": summary,
        "quality": {
            "issues": q["issues"][:200],
            "issue_total": len(q["issues"]),
            "check_stats": q["check_stats"],
            "repair_tasks": q["repair_tasks"][:200],
            "blocked_count": q["blocked_count"],
        },
        "match": {
            "total": len(m["results"]),
            "agg_groups": len(m["agg_groups"]),
            "unmatched_ledger": len([x for x in m["unmatched_ledger"] if x.get("truth") not in ("D03", "D10")]),
            "method_stats": _method_stats(m["results"]),
            "rows": [_slim(r) for r in m["results"]],
        },
        "diffs": diffs,
        "tickets": tickets,
        "audit": {"chain": chain[-200:], "total": len(chain), "check": chain_check,
                  "full_chain": chain},
        "kpi": kpi,
    }
    return state


def _method_stats(results: list) -> list:
    buckets = {"L1": "L1 主键精确", "L2": "L2 渠道单号", "L3": "L3 金额+时间窗",
               "AGG": "合并入账拆分", "REF": "退款事件反查",
               "L1-DUP": "重复订单识别", "NONE": "未匹配", "FRESHNESS": "快照校验",
               "L3-AMBIG": "低置信候选", "AGG-FAIL": "合并拆分失败", "质控拦截": "质控拦截"}
    cnt = {}
    for r in results:
        cnt[r["method"]] = cnt.get(r["method"], 0) + 1
    out = []
    for k, v in sorted(cnt.items(), key=lambda x: -x[1]):
        out.append({"method": k, "label": buckets.get(k, k), "count": v})
    return out


def _slim(r: dict) -> dict:
    """只保留渲染需要的字段，压缩输出体积。"""
    return {
        "row_id": r["row_id"], "biz_key": r["biz_key"], "code": r["reason_code"],
        "method": r["method"], "conf": r["confidence"], "amount": r["amount_cents"],
        "note": r["note"], "truth": r["truth"], "type": r["txn_type"],
    }


def export(state: dict, out_dir: str) -> dict:
    """导出 CSV / JSONL 审计日志。"""
    os.makedirs(out_dir, exist_ok=True)

    diffs = state["diffs"]
    if diffs:
        path = os.path.join(out_dir, "差异清单_diff_list.csv")
        cols = ["biz_no", "reason_code", "reason_title", "disposition", "side",
                "amount_cents", "method", "confidence", "explained", "note",
                "evidence_refs", "suggestion", "rule_version", "snapshot_version"]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for d in diffs:
                row = []
                for c in cols:
                    v = d.get(c, "")
                    if c == "evidence_refs":
                        v = " | ".join(v)
                    row.append(v)
                w.writerow(row)

    if state["tickets"]:
        path = os.path.join(out_dir, "转人工工单_tickets.csv")
        cols = ["ticket_id", "biz_no", "trigger_code", "trigger_title", "reason_title",
                "pool", "assignee", "created_at", "sla_deadline", "status", "double_check"]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for t in state["tickets"]:
                w.writerow([t[c] for c in cols])

    # 审计日志（完整链条导出，不截断）
    full = state["audit"].get("full_chain")
    if full:
        audit.dump(full, os.path.join(out_dir, "审计留痕_audit.jsonl"))

    with open(os.path.join(out_dir, "指标快照_metrics.json"), "w", encoding="utf-8") as f:
        json.dump({
            "meta": state["meta"], "summary": state["summary"],
            "kpi": state["kpi"]["kpi"], "by_code": state["kpi"]["by_code"],
            "spec": state["kpi"]["spec"], "nodes": state["kpi"]["nodes"],
            "audit_check": state["audit"]["check"],
        }, f, ensure_ascii=False, indent=2)
    return {"diff_csv": len(diffs), "tickets": len(state["tickets"])}
