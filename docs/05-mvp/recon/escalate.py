# -*- coding: utf-8 -*-
"""
人工兜底网关：四类触发条件必须转人工，且必须标注触发原因、接手人、确认时间。

对齐 f44（触发条件与标注要求）、f25（跨岗问题须明确下一责任人、超时升级）、
f40（涉及资金动作双人复核）。系统在这里只“发单”，不“处置”。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import config as C

TZ8 = timezone(timedelta(hours=8))
BASE_TIME = datetime(2026, 10, 28, 9, 0, 0, tzinfo=TZ8)   # 对账作业开始时间


def build_tickets(diffs: list) -> list:
    tickets = []
    seq = 0
    for d in diffs:
        trig = _trigger_of(d)
        if not trig:
            continue
        seq += 1
        pool, owner = C.ASSIGNEE_POOL.get(d["reason_code"], ("对账会计池", "唐映秋"))
        created = BASE_TIME + timedelta(minutes=seq * 2)
        code, title, text = trig
        tickets.append({
            "ticket_id": "WO20261028%03d" % seq,
            "biz_no": d["biz_no"],
            "reason_code": d["reason_code"],
            "reason_title": d["reason_title"],
            "trigger_code": code,
            "trigger_title": title,
            "trigger_text": text,
            "evidence_refs": d["evidence_refs"],
            "pool": pool,
            "assignee": owner,
            "created_at": created.isoformat(timespec="minutes"),
            "sla_deadline": (created + timedelta(minutes=C.SLA_MINUTES)).isoformat(timespec="minutes"),
            "confirm_time": "",          # 未接手前必须为空，不允许默认“已完成”
            "status": "待接手",
            "escalate_to": C.ESCALATE_TO,
            "escalated": False,
            "double_check": d["reason_code"] in ("D03", "D06"),   # 涉及资金动作须双人复核
        })
    return tickets


def _trigger_of(d: dict):
    code = d["reason_code"]
    if code == "D03":
        e = C.ESCALATION_TRIGGERS["E1"]
        return ("E1", e[0], e[1])
    if code == "D06":
        e = C.ESCALATION_TRIGGERS["E3"]
        return ("E3", e[0], e[1])
    if code == "D09":
        e = C.ESCALATION_TRIGGERS["E4"]
        return ("E4", e[0], e[1])
    if code == "D10" or not d.get("explained", True):
        e = C.ESCALATION_TRIGGERS["E2"]
        return ("E2", e[0], e[1])
    return None
