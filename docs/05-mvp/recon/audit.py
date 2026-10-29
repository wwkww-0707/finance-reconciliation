# -*- coding: utf-8 -*-
"""
审计留痕：哈希链式追加日志。

对齐 f45：每次建议保留业务编号、资料版本、事实引用、建议结果、人工改动和签核人，
且能重建“流水归集 → 渠道账单匹配 → 差异定位 → 工单确认 → 人工调整 → 复核”的整条链。
不记录口令与不必要的个人信息。

为什么用哈希链：单条日志可以被删改而不留痕；把每条记录的哈希指向前一条，
任何中段篡改都会让后续链条校验失败，审计时可以一键验证“这条链没被动过”。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

TZ8 = timezone(timedelta(hours=8))
GENESIS = "0" * 64


def _digest(payload: dict, prev_hash: str) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + raw).encode("utf-8")).hexdigest()


def append(chain: list, event: dict) -> dict:
    """向链条追加一条事件，返回新记录。"""
    seq = len(chain) + 1
    prev = chain[-1]["hash"] if chain else GENESIS
    rec = {
        "seq": seq,
        "ts": event.get("ts") or datetime.now(TZ8).isoformat(timespec="seconds"),
        "type": event["type"],
        "biz_no": event["biz_no"],
        "stage": event["stage"],
        "doc_version": event.get("doc_version"),
        "fact_refs": event.get("fact_refs", []),
        "suggestion": event.get("suggestion", ""),
        "manual_change": event.get("manual_change", ""),
        "signer": event.get("signer", "系统（只读建议）"),
        "prev_hash": prev,
    }
    rec["hash"] = _digest({k: v for k, v in rec.items()}, prev)
    chain.append(rec)
    return rec


def seed_from_diffs(diffs: list) -> list:
    """把差异清单写成初始建议事件（系统侧，无签核人）。"""
    chain = []
    for d in diffs:
        append(chain, {
            "type": "SUGGEST",
            "biz_no": d["biz_no"],
            "stage": "差异定位",
            "doc_version": "v%s" % d["snapshot_version"],
            "fact_refs": d["evidence_refs"],
            "suggestion": "[%s] %s" % (d["reason_code"], d["suggestion"]),
            "signer": "系统（只读建议）",
        })
    return chain


def ack(chain: list, biz_no: str, signer: str, change: str = "", stage: str = "工单确认") -> dict:
    """人工接手/改动事件：签核人必填，改动内容明示。"""
    return append(chain, {
        "type": "HUMAN_ACK",
        "biz_no": biz_no,
        "stage": stage,
        "fact_refs": [],
        "suggestion": "",
        "manual_change": change or "确认接手，按建议继续核对",
        "signer": signer,
    })


def verify(chain: list) -> dict:
    """校验哈希链完整性，返回 {ok, broken_at, checked}。"""
    prev = GENESIS
    for rec in chain:
        body = {k: v for k, v in rec.items() if k != "hash"}
        if body["prev_hash"] != prev or _digest(body, prev) != rec["hash"]:
            return {"ok": False, "broken_at": rec["seq"], "checked": rec["seq"]}
        prev = rec["hash"]
    return {"ok": True, "broken_at": None, "checked": len(chain)}


def dump(chain: list, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for rec in chain:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
