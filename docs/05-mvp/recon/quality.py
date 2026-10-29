# -*- coding: utf-8 -*-
"""
字段级质量校验（匹配前置）。

对齐 f33：先校验主编号、事件时间和版本字段，**有歧义的记录进人工修复队列，
不进入自动推荐样本**。这一步的意义在于——脏数据不污染匹配结论，
否则差异定位出来的原因不可信，也谈不上“差异全部有可查原因”。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from . import config as C

TZ8 = timezone(timedelta(hours=8))
TIME_UPPER_BOUND = date(2026, 10, 29)      # 渠道时间晚于结算日次日即视为异常

CHECKS = [
    ("Q1", "主编号完整性", "商户订单号 / 渠道订单号至少一项存在"),
    ("Q2", "时区一致性", "渠道时间戳偏移须为 +08:00"),
    ("Q3", "事件时间有效性", "时间可解析，且不晚于结算日次日"),
    ("Q4", "金额与净额一致性", "净额 = 交易金额 − 手续费，且支付金额为正"),
    ("Q5", "规则版本字段", "内部流水须带手续费规则版本"),
    ("Q6", "主键唯一性", "同一商户订单号不应有多笔支付成功记录"),
    ("Q7", "快照时效", "数据源未超过一个更新周期（否则标记待刷新）"),
]


def _parse(ts: str):
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def run_check(ledger: list, channel: list, sources: list) -> dict:
    """返回 {issues, blocked_rows, repair_tasks, signals, check_stats}。"""
    issues = []
    blocked = {}                     # channel row_id -> reason_code
    signals = {"dup_key": {}, "stale_sources": []}
    stats = {c[0]: {"code": c[0], "name": c[1], "desc": c[2], "hits": 0} for c in CHECKS}

    def add(check, target, row, detail, reason_code, block=False):
        stats[check]["hits"] += 1
        issues.append({
            "check": check, "target": target, "row_id": row.get("row_id") or row.get("txn_id"),
            "detail": detail, "reason_code": reason_code,
        })
        if block and row.get("row_id"):
            blocked[row["row_id"]] = reason_code

    # ---------------- 内部流水 ----------------
    seen_pay = {}
    for r in ledger:
        if not r.get("fee_rule_version"):
            add("Q5", "内部流水", r, "缺少手续费规则版本，无法回溯费率依据", "D06")
        t = _parse(r["pay_time"])
        if t is None:
            add("Q3", "内部流水", r, "支付时间不可解析", "D08")
        if r["txn_type"] == "PAY" and r["gross_cents"] <= 0:
            add("Q4", "内部流水", r, "支付金额非正数", "D08")
        if r["txn_type"] == "PAY":
            key = r["merchant_order_no"]
            if key:
                seen_pay.setdefault(key, []).append(r)

    # 同一商户订单号出现多笔支付成功 → 重复订单信号（f11）
    for key, rows in seen_pay.items():
        if len(rows) > 1:
            stats["Q6"]["hits"] += 1
            signals["dup_key"][key] = [x["biz_no"] for x in rows]
            issues.append({
                "check": "Q6", "target": "内部流水", "row_id": rows[0]["txn_id"],
                "detail": "同一商户订单号 %s 出现 %d 笔支付成功记录（疑通知超时重试）" % (key, len(rows)),
                "reason_code": "D03",
            })

    # ---------------- 渠道结算文件 ----------------
    for r in channel:
        mo = (r.get("merchant_order_no") or "").strip()
        co = (r.get("channel_order_no") or "").strip()
        is_agg = mo.startswith("AGG/")

        # Q1 主编号完整性：合并入账行按设计不带单笔主编号，不算缺失
        if not mo and not co:
            add("Q1", "渠道结算", r, "商户订单号与渠道订单号同时缺失", "D05", block=True)
        elif not mo and not is_agg:
            add("Q1", "渠道结算", r, "缺少商户订单号，无法建立主键关系", "D05", block=True)

        # Q2 时区一致性
        t = _parse(r["channel_time"])
        if t is None:
            add("Q3", "渠道结算", r, "渠道时间不可解析", "D05", block=True)
        else:
            off = t.utcoffset()
            if off is not None and off.total_seconds() != 8 * 3600:
                add("Q2", "渠道结算", r,
                    "渠道时间戳偏移为 UTC%s，与内部 +08:00 口径相差 %d 小时"
                    % (_fmt_off(off), int(abs(off.total_seconds() - 8 * 3600) // 3600)), "D04", block=True)
            if t.astimezone(TZ8).date() > TIME_UPPER_BOUND:
                add("Q3", "渠道结算", r, "渠道时间晚于结算日次日", "D05", block=True)

        # Q4 金额一致性
        if r["net_cents"] != r["gross_cents"] - r["fee_cents"]:
            add("Q4", "渠道结算", r, "净额与金额、手续费不自洽", "D07")
        if r["txn_type"] == "PAY" and r["gross_cents"] <= 0:
            add("Q4", "渠道结算", r, "支付类结算行金额非正", "D08", block=True)

    # ---------------- Q7 快照时效 ----------------
    for s in sources:
        if s.get("status") == "待刷新" or int(s.get("lag_hours", 0)) > 24:
            signals["stale_sources"].append(s)
            stats["Q7"]["hits"] += 1
            issues.append({
                "check": "Q7", "target": s["source"], "row_id": "SNAPSHOT",
                "detail": "%s 快照滞后 %s 小时，超过一个更新周期，标记“暂未更新”"
                          % (s["source"], s.get("lag_hours")),
                "reason_code": "D09",
            })

    repair_tasks = [i for i in issues if i["check"] in ("Q1", "Q2", "Q3") and i["row_id"] != "SNAPSHOT"]
    return {
        "issues": issues,
        "blocked_rows": blocked,
        "repair_tasks": repair_tasks,
        "signals": signals,
        "check_stats": list(stats.values()),
        "blocked_count": len(blocked),
    }


def _fmt_off(off) -> str:
    total = int(off.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return "%s%02d:%02d" % (sign, total // 3600, (total % 3600) // 60)
