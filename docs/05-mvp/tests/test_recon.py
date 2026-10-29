# -*- coding: utf-8 -*-
"""
单元测试：只测“会让结论不可信”的地方。

运行：python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from recon import audit, config as C, datagen, differ, escalate, matcher, metrics, pipeline, quality


class ReconTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="recon_")
        cls.data = os.path.join(cls.tmp, "data")
        cls.summary = datagen.generate(cls.data, n_base=400, seed=7)
        cls.state = pipeline.run(cls.data, regenerate=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ------------------------------------------------ 可复现
    def test_generate_reproducible(self):
        other = os.path.join(self.tmp, "data2")
        s2 = datagen.generate(other, n_base=400, seed=7)
        self.assertEqual(s2["channel_rows"], self.summary["channel_rows"])
        self.assertEqual(s2["dist"], self.summary["dist"])

    # ------------------------------------------------ 质控前置
    def test_quality_blocks_missing_key_and_tz(self):
        blocked = [r for r in self.state["match"]["rows"] if r["method"] == "质控拦截"]
        self.assertGreater(len(blocked), 0, "质控应拦截主编号缺失与时区冲突记录")
        codes = {r["code"] for r in blocked}
        self.assertTrue(codes <= {"D04", "D05"}, "拦截码只允许 D04/D05，实际 %s" % codes)

    def test_repair_queue_not_in_denominator(self):
        k = self.state["kpi"]
        self.assertEqual(k["denominator"], k["total_rows"] - k["repair_count"] - k["low_conf_count"])

    # ------------------------------------------------ 关键场景
    def test_crossday_refund_detected(self):
        d01 = [d for d in self.state["diffs"] if d["reason_code"] == "D01"]
        self.assertGreater(len(d01), 0, "跨日退款应被识别")
        self.assertTrue(all(d["evidence_refs"] for d in d01), "跨日退款必须带退款事件证据")

    def test_duplicate_order_escalated(self):
        d03 = [d for d in self.state["diffs"] if d["reason_code"] == "D03"]
        self.assertGreater(len(d03), 0)
        tickets = [t for t in self.state["tickets"] if t["trigger_code"] == "E1"]
        self.assertEqual(len(tickets), len(d03), "重复订单必须全部转人工并标注 E1")

    def test_low_confidence_never_matched(self):
        rows = [r for r in self.state["match"]["rows"] if r["code"] == "D10"]
        for r in rows:
            self.assertEqual(r["method"], "L3-AMBIG")
        # 低置信不计入准确率分母
        self.assertEqual(
            len([r for r in self.state["match"]["rows"] if r["method"] == "质控拦截"]),
            self.state["kpi"]["repair_count"])

    # ------------------------------------------------ 差异可解释
    def test_all_diffs_explained(self):
        d = self.state["diffs"]
        self.assertGreater(len(d), 0)
        bad = [x for x in d if not x["explained"]]
        self.assertEqual(bad, [], "存在未解释差异：%s" % [b["biz_no"] for b in bad][:5])

    def test_required_fields_present(self):
        for x in self.state["diffs"]:
            for f in C.REASON_REQUIRED_FIELDS:
                self.assertIn(f, x)
            self.assertTrue(x["evidence_refs"], "差异 %s 缺证据" % x["biz_no"])

    # ------------------------------------------------ 兜底完整性
    def test_all_escalation_triggered_has_owner_and_sla(self):
        for t in self.state["tickets"]:
            self.assertTrue(t["assignee"])
            self.assertTrue(t["sla_deadline"])
            self.assertEqual(t["confirm_time"], "", "未接手前确认时间必须为空")
            self.assertIn(t["trigger_code"], C.ESCALATION_TRIGGERS)

    # ------------------------------------------------ 审计链
    def test_audit_chain_verifies(self):
        chain = self.state["audit"]["full_chain"]
        self.assertTrue(audit.verify(chain)["ok"])

    def test_audit_tamper_detected(self):
        chain = audit.seed_from_diffs(self.state["diffs"][:3])
        self.assertTrue(audit.verify(chain)["ok"])
        chain[1]["suggestion"] = "被篡改的建议"
        self.assertFalse(audit.verify(chain)["ok"], "篡改后哈希链必须校验失败")

    def test_ack_appends_signer(self):
        chain = audit.seed_from_diffs(self.state["diffs"][:1])
        rec = audit.ack(chain, "BIZ-TEST", "对账会计（唐映秋）", "改为按支付日归属")
        self.assertEqual(rec["signer"], "对账会计（唐映秋）")
        self.assertEqual(rec["type"], "HUMAN_ACK")
        self.assertTrue(audit.verify(chain)["ok"])

    # ------------------------------------------------ 只读边界
    def test_no_fund_action_fields(self):
        """MVP 不应出现任何资金操作动作（对齐 f05/f32/f52）。"""
        forbidden = ("refund(", "transfer(", "adjust(", "平账", "划转执行")
        src_dir = os.path.join(BASE, "recon")
        for fn in os.listdir(src_dir):
            if not fn.endswith(".py"):
                continue
            with open(os.path.join(src_dir, fn), encoding="utf-8") as fh:
                body = fh.read()
            for f in forbidden:
                self.assertNotIn(f, body, "%s 出现疑似资金操作：%s" % (fn, f))


if __name__ == "__main__":
    unittest.main(verbosity=2)
