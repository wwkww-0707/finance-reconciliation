# -*- coding: utf-8 -*-
"""
差异记录组装：把匹配结果翻译成“有原因的差异”。

关键约束（对齐 f42 / f45）：每条差异必须字段齐全，缺任一必填字段就计入
“未解释差异”，这是 99.9% 验收里最容易糊弄过去、也最不能被糊弄的一栏。
"""

from __future__ import annotations

from . import config as C


def build_diffs(match: dict, quality: dict, sources: list) -> list:
    """返回差异列表（reason_code != OK 的全部条目 + 内部单边账 + 快照类差异）。"""
    diffs = []

    # ---------- 1. 渠道结算侧的差异 ----------
    for r in match["results"]:
        code = r["reason_code"]
        if code == "OK":
            continue
        diffs.append(_make(
            biz_no=r["biz_key"] or r["row_id"],
            code=code,
            evidence=r["evidence_refs"] or [r["row_id"]],
            suggestion=_suggest(code, r),
            note=r["note"],
            amount=r["amount_cents"],
            row_id=r["row_id"],
            method=r["method"],
            confidence=r["confidence"],
            truth=r.get("truth", ""),
            side="渠道结算",
        ))

    # ---------- 2. 内部单边账 ----------
    for led in match["unmatched_ledger"]:
        if led.get("truth") in ("D03", "D10"):
            # 重复单与低置信候选的伴生流水，已在渠道侧差异里被引用，避免重复计数
            continue
        diffs.append(_make(
            biz_no=led["biz_no"],
            code="D08",
            evidence=[led["txn_id"], led["channel_order_no"] or led["merchant_order_no"]],
            suggestion="内部流水有、渠道结算无；回渠道侧确认是否漏结算或结算周期错配",
            note="内部流水在本结算日无对应渠道结算行",
            amount=led["gross_cents"],
            row_id=led["txn_id"],
            method="NONE",
            confidence=0.0,
            truth=led.get("truth", ""),
            side="内部流水",
        ))

    # ---------- 3. 快照类差异（D09）----------
    for s in quality["signals"]["stale_sources"]:
        diffs.append(_make(
            biz_no="SNAPSHOT/%s" % s["source"],
            code="D09",
            evidence=[s["source"], s["snapshot_time"], "lag=%sh" % s["lag_hours"]],
            suggestion="继续使用带时间戳的只读快照并显示“暂未更新”，重连后按业务编号去重补齐",
            note="%s 快照滞后 %s 小时，超过一个更新周期，不得作为实时承诺" % (s["source"], s["lag_hours"]),
            amount=0,
            row_id="SNAPSHOT",
            method="FRESHNESS",
            confidence=1.0,
            truth="D09",
            side="数据源",
        ))

    # 排序：先按处置紧急（ESCALATE > HUMAN_CHECK > REPAIR_QUEUE），再按金额倒序
    rank = {"ESCALATE": 0, "HUMAN_CHECK": 1, "REPAIR_QUEUE": 2}
    diffs.sort(key=lambda d: (rank.get(d["disposition"], 3), -abs(d["amount_cents"])))
    return diffs


def _make(biz_no, code, evidence, suggestion, note, amount, row_id,
          method, confidence, truth, side) -> dict:
    title, root_cause, default_sug, disposition = C.REASON_CODES[code]
    d = {
        "biz_no": biz_no,
        "reason_code": code,
        "reason_title": title,
        "root_cause": root_cause,
        "evidence_refs": [e for e in evidence if e],
        "rule_version": C.LATEST_RULE_VERSION,
        "snapshot_version": C.SNAPSHOT_VERSION,
        "suggestion": suggestion or default_sug,
        "disposition": disposition,
        "checker": "recon-engine/%s" % C.LATEST_RULE_VERSION,
        "method": method,
        "confidence": round(confidence, 3),
        "amount_cents": amount,
        "note": note,
        "row_id": row_id,
        "side": side,
        "truth": truth,
    }
    # 可查原因判定：必填字段齐全且证据非空
    missing = [f for f in C.REASON_REQUIRED_FIELDS if d.get(f) in (None, "", [], 0)]
    if not d["evidence_refs"]:
        missing.append("evidence_refs")
    d["missing_fields"] = missing
    d["explained"] = len(missing) == 0
    return d


def _suggest(code: str, r: dict) -> str:
    if code == "D01":
        return "关联退款事件与原支付单，确认是否按原支付日冲销；确认后决定是否调账（需双人复核）"
    if code == "D02":
        return "按合并批次拆分为 %d 笔逐笔核销，回填手续费明细" % len(r.get("matched_keys") or [])
    if code == "D03":
        return "以渠道成功记录为准，撤销内部重复单；触及资金动作须双人复核（f40）"
    if code == "D04":
        return "统一按内部 +08:00 口径重算时间窗后重新入队，本轮不参与自动匹配"
    if code == "D05":
        return "补齐商户订单号后重新入队；不进入自动推荐样本"
    if code == "D06":
        return "附 %s 与 %s 两版规则提交资金风险经理裁定，不自行选择较宽松条款" % (
            C.LATEST_RULE_VERSION, "旧版")
    if code == "D07":
        return "核对费率表，确认差额是否为未登记通道费；确认后更新规则版本再复测"
    if code == "D10":
        return "同额多候选，提请人工按渠道回单确认；系统不输出匹配结论"
    return "回渠道侧取原始回单，按差错登记流程处理"
