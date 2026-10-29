# -*- coding: utf-8 -*-
"""
分层匹配引擎（只读，不产生任何资金动作）。

分层设计对齐“先确定性、后概率性”的原则：
    L1 主键精确（商户订单号 + 金额）        → 高置信
    L2 渠道单号精确（渠道订单号 + 金额）    → 高置信
    L3 金额 + 时间窗                        → 中置信，低于阈值转人工
    AGG 合并入账单组拆分校验（和值 + 手续费双校验）
    REF 退款事件反查（识别跨日退款归属）

任何一层都不做“猜测性强制匹配”：对不上就出差异，而不是凑一笔对上去
（对齐 f40：不能用猜测匹配掩盖差异）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import config as C

TZ8 = timezone(timedelta(hours=8))
WINDOW = timedelta(hours=C.MATCH_WINDOW_HOURS)


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def run_match(ledger: list, channel: list, refunds: list, blocked: dict) -> dict:
    """返回 {results:[...], unmatched_ledger:[...], agg_groups:[...]}。"""
    by_mo, by_co = {}, {}
    for r in ledger:
        if r["txn_type"] != "PAY":
            continue
        by_mo.setdefault(r["merchant_order_no"], []).append(r)
        if r["channel_order_no"]:
            by_co.setdefault(r["channel_order_no"], []).append(r)

    refund_by_mo = {r["orig_merchant_order_no"]: r for r in refunds}
    claimed = set()
    results = []
    agg_found = []

    # 先处理合并入账单（它们占用较多流水，先拆避免误抢）
    for row in channel:
        if row["row_id"] in blocked:
            continue
        if not row["merchant_order_no"].startswith("AGG/"):
            continue
        res, members = _split_aggregate(row, ledger, claimed)
        claimed.update(m["txn_id"] for m in members)
        if members:
            agg_found.append({"row_id": row["row_id"], "members": [m["txn_id"] for m in members]})
        results.append(res)

    for row in channel:
        rid = row["row_id"]
        if rid in blocked:
            code = blocked[rid]
            # 被质控拦截的记录已进修复队列，其对应流水不算“内部单边账”，
            # 但也不参与自动匹配——只做占用标记，避免重复计数。
            for x in by_mo.get((row["merchant_order_no"] or "").strip(), []) + \
                    by_co.get((row["channel_order_no"] or "").strip(), []):
                if x["txn_id"] not in claimed:
                    claimed.add(x["txn_id"])
                    break
            results.append(_res(row, code, "质控拦截", 0.0, [], [],
                                note="字段级校验未通过，进入人工修复队列，不参与自动匹配（f33）"))
            continue
        if row["merchant_order_no"].startswith("AGG/"):
            continue

        # ---- 退款冲销行 ----
        if row["txn_type"] == "REFUND":
            ev = refund_by_mo.get(row["merchant_order_no"])
            if ev:
                same_day = _dt(ev["refund_time"]).astimezone(TZ8).date() == \
                    datetime.fromisoformat(row["settle_date"]).date()
                if same_day:
                    results.append(_res(row, "OK", "REF", 0.99,
                                        [ev["orig_merchant_order_no"]],
                                        [ev["refund_id"]],
                                        note="当日退款，归属期间一致"))
                else:
                    results.append(_res(
                        row, "D01", "REF", 0.98,
                        [ev["orig_merchant_order_no"], ev["refund_id"]],
                        [ev["refund_id"], ev["orig_channel_order_no"]],
                        note="退款时间 %s 晚于结算日 %s，渠道按支付日归属冲销，内部本结算日无该笔"
                             % (ev["refund_time"][:16], row["settle_date"])))
            else:
                results.append(_res(row, "D08", "NONE", 0.0, [], [],
                                    note="渠道冲销行未找到对应退款事件"))
            continue

        gross = row["gross_cents"]
        mo = (row["merchant_order_no"] or "").strip()

        # ---- L1 主键精确 ----
        cand = [x for x in by_mo.get(mo, []) if x["txn_id"] not in claimed] if mo else []
        if len(cand) == 1:
            led = cand[0]
            claimed.add(led["txn_id"])
            results.append(_classify(row, led, "L1", 0.995, by_mo))
            continue
        if len(cand) > 1:
            # 同一商户订单号多笔 → 重复订单（f11）
            for x in cand:
                claimed.add(x["txn_id"])
            results.append(_classify(row, cand[0], "L1-DUP", 0.95, by_mo,
                                     extra_refs=[x["txn_id"] for x in cand[1:]],
                                     force_code="D03"))
            continue

        # ---- L2 渠道单号精确 ----
        co = (row["channel_order_no"] or "").strip()
        cand2 = [x for x in by_co.get(co, []) if x["txn_id"] not in claimed] if co else []
        if len(cand2) == 1:
            led = cand2[0]
            claimed.add(led["txn_id"])
            results.append(_classify(row, led, "L2", 0.985, by_mo))
            continue

        # ---- L3 金额 + 时间窗 ----
        ct = _dt(row["channel_time"]).astimezone(TZ8)
        pool = [x for x in ledger
                if x["txn_type"] == "PAY"
                and x["txn_id"] not in claimed
                and x["gross_cents"] == gross
                and abs((_dt(x["pay_time"]).astimezone(TZ8) - ct)) <= WINDOW]
        if len(pool) == 1 and gross >= C.LOW_CONF_AMOUNT_CENTS:
            led = pool[0]
            claimed.add(led["txn_id"])
            results.append(_classify(row, led, "L3", 0.90, by_mo))
            continue
        if len(pool) > 1:
            results.append(_res(
                row, "D10", "L3-AMBIG", 0.0, [x["merchant_order_no"] for x in pool],
                [x["txn_id"] for x in pool],
                note="金额 %s 元在 ±%d 小时窗口内有 %d 笔同额候选，缺可独立核验的主键，不作匹配结论"
                     % (_yuan(gross), C.MATCH_WINDOW_HOURS, len(pool))))
            continue

        # ---- 单边账（渠道有、内部无）----
        results.append(_res(row, "D08", "NONE", 0.0, [], [],
                            note="内部流水在本结算日无该笔记录（含时间窗内），需回渠道侧取原始回单"))

    unmatched_ledger = [r for r in ledger if r["txn_id"] not in claimed]
    return {"results": results, "unmatched_ledger": unmatched_ledger, "agg_groups": agg_found}


# ---------------------------------------------------------------- 分类
def _classify(row, led, method, conf, by_mo, extra_refs=None, force_code=None) -> dict:
    """已匹配到具体流水后的原因判定（优先级：重复 > 版本冲突 > 金额差 > 正常）。"""
    gross = row["gross_cents"]
    refs = [led["biz_no"], row["row_id"], led["txn_id"]]
    refs += extra_refs or []

    if force_code:
        return _res(row, force_code, method, conf, [led["merchant_order_no"]], refs,
                    note="同一商户订单号在内部生成多笔支付记录，渠道仅一条成功记录")
    if len(by_mo.get(led["merchant_order_no"], [])) > 1:
        return _res(row, "D03", method, conf, [led["merchant_order_no"]], refs,
                    note="同一商户订单号在内部生成多笔支付记录，渠道仅一条成功记录")
    if led["fee_rule_version"] and led["fee_rule_version"] != C.LATEST_RULE_VERSION:
        return _res(row, "D06", method, conf,
                    [led["merchant_order_no"], led["fee_rule_version"]],
                    refs + [led["fee_rule_version"], C.LATEST_RULE_VERSION],
                    note="该笔按 %s 计费，与当前生效 %s 并存，两版生效期重叠"
                         % (led["fee_rule_version"], C.LATEST_RULE_VERSION))
    if led["gross_cents"] != gross:
        return _res(row, "D07", method, conf, [led["merchant_order_no"]], refs,
                    note="渠道结算金额 %s 元与内部交易金额 %s 元相差 %s 元"
                         % (_yuan(gross), _yuan(led["gross_cents"]),
                            _yuan(abs(gross - led["gross_cents"]))))
    # 金额一致不等于无差异：手续费分位差同样要报（否则会被当成“正常”溜过去）
    if int(led["fee_cents"]) != int(row["fee_cents"]):
        return _res(row, "D07", method, conf, [led["merchant_order_no"]], refs,
                    note="交易金额一致，但手续费相差 %d 分（内部 %s / 渠道 %s），疑分位取整规则不一致"
                         % (abs(int(led["fee_cents"]) - int(row["fee_cents"])),
                            _yuan(led["fee_cents"]), _yuan(row["fee_cents"])))
    return _res(row, "OK", method, conf, [led["merchant_order_no"]], refs,
                note="主键与金额一致")


def _res(row, code, method, conf, keys, refs, note="") -> dict:
    return {
        "row_id": row["row_id"],
        "settle_date": row["settle_date"],
        "biz_key": row["merchant_order_no"] or row["channel_order_no"],
        "channel_order_no": row["channel_order_no"],
        "txn_type": row["txn_type"],
        "amount_cents": row["gross_cents"],
        "reason_code": code,
        "method": method,
        "confidence": conf,
        "matched_keys": keys,
        "evidence_refs": refs,
        "note": note,
        "truth": row.get("truth", ""),
    }


# ---------------------------------------------------------------- 合并入账拆分
def _split_aggregate(row, ledger, claimed):
    """合并入账拆分：同一商户当日未占用流水，校验金额与手续费和值是否等于合并结算行。

    不做子集穷举——渠道是按商户按日汇总的，分组依据是“商户 + 结算日”；
    穷举组合会制造出偶然成立的伪匹配，正好踩中 f40“不能用猜测匹配掩盖差异”。
    """
    target_gross = row["gross_cents"]
    target_fee = row["fee_cents"]
    mid = (row["merchant_order_no"] or "")[4:]        # "AGG/MER0012" -> "MER0012"
    settle_day = row["settle_date"]

    pool = [x for x in ledger
            if x["txn_type"] == "PAY"
            and x["txn_id"] not in claimed
            and x.get("merchant_id") == mid
            and datetime.fromisoformat(x["pay_time"]).astimezone(TZ8).strftime("%Y-%m-%d") == settle_day]

    if 2 <= len(pool) <= C.AGG_MAX_ROWS:
        g = sum(x["gross_cents"] for x in pool)
        f = sum(x["fee_cents"] for x in pool)
        if g == target_gross and f == target_fee:
            return _res(row, "D02", "AGG", 0.97,
                        [x["merchant_order_no"] for x in pool],
                        [row["row_id"]] + [x["txn_id"] for x in pool],
                        note="渠道将商户 %s 当日 %d 笔交易合并为一条结算行（金额 %s 元、手续费 %s 元双校验通过），需逐笔拆分核销"
                             % (mid, len(pool), _yuan(g), _yuan(f))), pool
    return _res(row, "D02", "AGG-FAIL", 0.0, [], [row["row_id"]],
                note="合并结算行无法拆分：商户 %s 当日可核销流水 %d 笔，金额或手续费和值不匹配，转人工核对明细"
                     % (mid, len(pool))), []


def _yuan(cents: int) -> str:
    return "%.2f" % (cents / 100.0)
