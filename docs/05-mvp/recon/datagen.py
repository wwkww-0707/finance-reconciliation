# -*- coding: utf-8 -*-
"""
合成数据生成器（离线回放用）。

为什么用合成数据
----------------
发现报告要求“先取一个渠道的历史账单与流水做字段级校验清单回放”（REQ-1 下一步验证），
但真实支付数据不可获取。本模块按访谈描述的业务失败方式（f10/f11/f31/f50）等比例构造
缺陷样本，并为每条渠道结算行写入 `truth` 真值列——真值只用于评估准确率，
生产环境应以人工复核结论作为真值。

生成的四类材料对齐 f21：渠道结算文件、内部流水、退款事件、手续费规则。
"""

from __future__ import annotations

import csv
import os
import random
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import config as C

TZ8 = timezone(timedelta(hours=8))
D0 = datetime(2026, 10, 27, 0, 0, 0, tzinfo=TZ8)
MERCHANT_POOL = 240          # 商户数（决定合并入账的自然分组）

FEE_RULES = [
    # 版本冲突的来源：两版生效期重叠（v1.1 未按时下线）
    ("FEE-RULE-v1.1", "2026-09-01", "2026-10-31", 65, 1, 0, "旧版费率，应于 10-01 下线但未下线"),
    ("FEE-RULE-v1.2", "2026-10-01", "2026-12-31", 60, 1, 0, "当前生效版本"),
]


def _iso(dt: datetime, utc: bool = False) -> str:
    """按渠道/内部两种时区口径输出 ISO 时间串。"""
    return dt.astimezone(timezone.utc).isoformat() if utc else dt.isoformat()


def _fee(gross: int, rate_bp: int, min_fee: int) -> int:
    """手续费（分）。rate_bp 为万分比，60 = 0.6%。"""
    return max(int(round(gross * rate_bp / 10000.0)), min_fee)


def generate(out_dir: str, n_base: int = 1100, seed: int = 20261027) -> dict:
    """生成四类材料 + 快照元数据，返回统计摘要。"""
    rnd = random.Random(seed)
    os.makedirs(out_dir, exist_ok=True)

    # ---------- 1. 基础交易 ----------
    base = []
    for i in range(n_base):
        gross = rnd.randrange(1200, 48000, 100)
        pay = D0 + timedelta(minutes=rnd.randint(0, 21 * 60), seconds=rnd.randint(0, 59))
        base.append({
            "idx": i,
            "merchant_id": "MER%04d" % rnd.randint(1, MERCHANT_POOL),
            "merchant_order_no": "M%06d" % (100000 + i),
            "channel_order_no": "42000%011d" % (7000000 + i),
            "gross": gross,
            "pay": pay,
        })

    # ---------- 2. 先圈定“合并入账”的商户 ----------
    # 渠道按商户按日汇总入账，因此合并组 = 同一商户当天的全部交易（3~6 笔）。
    per_merchant = {}
    for b in base:
        per_merchant.setdefault(b["merchant_id"], []).append(b["idx"])
    eligible = [m for m, ids in per_merchant.items() if 3 <= len(ids) <= 6]
    rnd.shuffle(eligible)
    agg_merchants = set(eligible[:12])
    idx_agg = [i for i in range(n_base) if base[i]["merchant_id"] in agg_merchants]
    used = set(idx_agg)

    # 其余缺陷从剩余样本中抽样，互不重叠
    order = [i for i in range(n_base) if i not in used]
    rnd.shuffle(order)
    cur = 0

    def take(k: int) -> list:
        nonlocal cur
        seg = order[cur:cur + k]
        cur += k
        return seg

    idx_refund = take(36)     # 跨日退款
    idx_tz = take(18)         # 时区偏移
    idx_nokey = take(15)      # 主编号缺失
    idx_ver = take(12)        # 规则版本冲突
    idx_amt = take(16)        # 金额差异
    idx_dup = take(24)        # 重复订单
    idx_fee = take(8)         # 手续费分位差异（金额一致）
    idx_amb = take(7)         # 低置信（同额多候选）
    idx_oneside = take(9)     # 内部有、渠道无

    S = set
    s_agg = S(idx_agg)
    s_refund, s_tz, s_nokey = S(idx_refund), S(idx_tz), S(idx_nokey)
    s_ver, s_amt, s_dup = S(idx_ver), S(idx_amt), S(idx_dup)
    s_fee, s_amb, s_oneside = S(idx_fee), S(idx_amb), S(idx_oneside)

    # ---------- 3. 内部流水 ----------
    ledger = []
    for b in base:
        rule = "FEE-RULE-v1.1" if b["idx"] in s_ver else C.LATEST_RULE_VERSION
        fee = _fee(b["gross"], 65 if rule.endswith("v1.1") else 60, 1)
        ledger.append({
            "txn_id": "T20261027%06d" % b["idx"],
            "biz_no": "BIZ-20261027-%05d" % b["idx"],
            "merchant_id": b["merchant_id"],
            "merchant_order_no": b["merchant_order_no"],
            "channel_order_no": b["channel_order_no"],
            "gross_cents": b["gross"],
            "fee_cents": fee,
            "fee_rule_version": rule,
            "pay_time": _iso(b["pay"]),
            "status": "SUCCESS",
            "txn_type": "PAY",
            "truth": "D10" if b["idx"] in s_amb else "OK",
        })
        # 重复订单：内部多生成一笔（通知超时后商户重试）
        if b["idx"] in s_dup:
            ledger.append({
                "txn_id": "T20261027%06dD" % b["idx"],
                "biz_no": "BIZ-20261027-%05dD" % b["idx"],
                "merchant_id": b["merchant_id"],
                "merchant_order_no": b["merchant_order_no"],   # 同一商户订单号 → 内部重复单
                "channel_order_no": "",
                "gross_cents": b["gross"],
                "fee_cents": fee,
                "fee_rule_version": rule,
                "pay_time": _iso(b["pay"] + timedelta(minutes=3)),
                "status": "SUCCESS",
                "txn_type": "PAY",
                "truth": "D03",
            })
        # 低置信：制造同额、时间窗内的其他交易（小额重复场景真实存在）
        if b["idx"] in s_amb:
            for k in range(2):
                ledger.append({
                    "txn_id": "T20261027%06dA%d" % (b["idx"], k),
                    "biz_no": "BIZ-20261027-%05dA%d" % (b["idx"], k),
                    "merchant_id": "MER%04d" % (5000 + b["idx"] * 2 + k),
                    "merchant_order_no": "M%06d" % (900000 + b["idx"] * 2 + k),
                    "channel_order_no": "42000%011d" % (8000000 + b["idx"] * 2 + k),
                    "gross_cents": b["gross"],
                    "fee_cents": fee,
                    "fee_rule_version": rule,
                    "pay_time": _iso(b["pay"] + timedelta(minutes=7 + 11 * k)),
                    "status": "SUCCESS",
                    "txn_type": "PAY",
                    "truth": "D10",
                })

    # ---------- 4. 渠道结算文件 ----------
    channel = []
    for b in base:
        if b["idx"] in s_oneside:
            continue                                   # 渠道侧漏结算
        if b["idx"] in s_agg:
            continue                                   # 稍后按商户合并

        gross = b["gross"]
        fee = _fee(gross, 65 if b["idx"] in s_ver else 60, 1)
        mo, co, truth = b["merchant_order_no"], b["channel_order_no"], "OK"
        ctime, utc_flag = b["pay"] + timedelta(seconds=rnd.randint(1, 40)), False

        if b["idx"] in s_nokey:
            mo, truth = "", "D05"
        if b["idx"] in s_tz:
            utc_flag, truth = True, "D04"
        if b["idx"] in s_amt:
            gross, truth = gross - 50, "D07"       # 渠道多扣未登记通道费
        if b["idx"] in s_dup:
            truth = "D03"
        if b["idx"] in s_ver:
            truth = "D06"
        if b["idx"] in s_fee:
            fee, truth = fee + 1, "D07"          # 渠道分位四舍五入多收 1 分
        if b["idx"] in s_amb:
            # 渠道回单商户订单号录错一位 → 主键对不上，只剩金额+时间窗
            mo, co, truth = "M%06d" % (700000 + b["idx"]), "", "D10"

        channel.append({
            "row_id": "CS%05d" % (len(channel) + 1),
            "settle_date": C.SETTLE_DATE,
            "settle_batch": "B20261027-01",
            "merchant_id": b["merchant_id"],
            "merchant_order_no": mo,
            "channel_order_no": co,
            "gross_cents": gross,
            "fee_cents": fee,
            "net_cents": gross - fee,
            "txn_type": "PAY",
            "channel_time": _iso(ctime, utc=utc_flag),
            "truth": truth,
        })

    # 合并入账：同一商户当日交易合并为一条结算行
    for k, mid in enumerate(sorted(agg_merchants)):
        ids = per_merchant[mid]
        rows = [base[i] for i in ids]
        gross = sum(r["gross"] for r in rows)
        fee = sum(_fee(r["gross"], 60, 1) for r in rows)
        agg_id = "AGG20261027%03d" % (k + 1)
        channel.append({
            "row_id": "CS%05d" % (len(channel) + 1),
            "settle_date": C.SETTLE_DATE,
            "settle_batch": "B20261027-03",
            "merchant_id": mid,
            "merchant_order_no": "AGG/%s" % mid,      # 合并行不带单笔主编号
            "channel_order_no": agg_id,
            "gross_cents": gross,
            "fee_cents": fee,
            "net_cents": gross - fee,
            "txn_type": "PAY",
            "channel_time": _iso(max(r["pay"] for r in rows) + timedelta(minutes=30)),
            "truth": "D02",
        })

    # 跨日退款：渠道按支付日归属，在 D 日结算行冲销；内部 D 日无该笔
    refunds = []
    for k, i in enumerate(idx_refund):
        b = base[i]
        refunds.append({
            "refund_id": "RF20261028%04d" % (k + 1),
            "orig_merchant_order_no": b["merchant_order_no"],
            "orig_channel_order_no": b["channel_order_no"],
            "refund_cents": b["gross"],
            "refund_time": _iso(D0 + timedelta(days=1, hours=1, minutes=rnd.randint(0, 50))),
            "refund_status": "SUCCESS",
            "truth": "D01",
        })
        channel.append({
            "row_id": "CS%05d" % (len(channel) + 1),
            "settle_date": C.SETTLE_DATE,
            "settle_batch": "B20261027-02",
            "merchant_id": b["merchant_id"],
            "merchant_order_no": b["merchant_order_no"],
            "channel_order_no": b["channel_order_no"],
            "gross_cents": -b["gross"],
            "fee_cents": 0,
            "net_cents": -b["gross"],
            "txn_type": "REFUND",
            "channel_time": _iso(D0 + timedelta(hours=23, minutes=50)),
            "truth": "D01",
        })

    # 单边账（渠道有、内部无）：渠道多结算 10 笔
    for k in range(10):
        gross = rnd.randrange(1200, 30000, 100)
        fee = _fee(gross, 60, 1)
        channel.append({
            "row_id": "CS%05d" % (len(channel) + 1),
            "settle_date": C.SETTLE_DATE,
            "settle_batch": "B20261027-01",
            "merchant_id": "MER%04d" % (6000 + k),
            "merchant_order_no": "M9%05d" % (k + 1),
            "channel_order_no": "42000%011d" % (9000000 + k),
            "gross_cents": gross,
            "fee_cents": fee,
            "net_cents": gross - fee,
            "txn_type": "PAY",
            "channel_time": _iso(D0 + timedelta(hours=15, minutes=k * 3)),
            "truth": "D08",
        })

    channel.sort(key=lambda r: r["row_id"])

    # ---------- 5. 落盘 ----------
    _write(os.path.join(out_dir, "内部流水_ledger.csv"), ledger)
    _write(os.path.join(out_dir, "渠道结算_%s.csv" % C.CHANNEL), channel)
    _write(os.path.join(out_dir, "退款事件_refunds.csv"), refunds)
    _write(os.path.join(out_dir, "手续费规则_fee_rules.csv"), [
        {"version": v, "effective_from": f, "effective_to": t,
         "rate_bp": r, "min_fee_cents": m, "cap_fee_cents": c, "note": n}
        for (v, f, t, r, m, c, n) in FEE_RULES
    ])

    # 快照元数据：退款事件源滞后 26 小时 → 触发 D09“待刷新”
    sources = [
        {"source": "内部流水", "rows": len(ledger),
         "snapshot_time": _iso(D0 + timedelta(hours=23, minutes=59)), "lag_hours": 2, "status": "正常"},
        {"source": "渠道结算文件", "rows": len(channel),
         "snapshot_time": _iso(D0 + timedelta(hours=23, minutes=55)), "lag_hours": 1, "status": "正常"},
        {"source": "退款事件", "rows": len(refunds),
         "snapshot_time": _iso(D0 + timedelta(hours=1, minutes=30)), "lag_hours": 26, "status": "待刷新"},
        {"source": "手续费规则", "rows": len(FEE_RULES),
         "snapshot_time": _iso(D0 + timedelta(hours=9)), "lag_hours": 15, "status": "正常"},
    ]
    _write(os.path.join(out_dir, "数据源快照_sources.csv"), sources)

    return {
        "ledger_rows": len(ledger),
        "channel_rows": len(channel),
        "refund_rows": len(refunds),
        "agg_groups": len(agg_merchants),
        "dist": dict(Counter(r["truth"] for r in channel)),
        "sources": sources,
    }


def _write(path: str, rows: list) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
