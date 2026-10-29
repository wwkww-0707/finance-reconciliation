# -*- coding: utf-8 -*-
"""
生成《支付对账与差错追踪 · 行业分析》Word 文档。

用法：python tools/build_industry_docx.py
输出：docs/02-行业分析/支付对账差错追踪-行业分析.docx
"""

from __future__ import annotations

import os

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "02-行业分析", "支付对账差错追踪-行业分析.docx")

NAVY = RGBColor(0x1A, 0x3A, 0x6B)
INK = RGBColor(0x1B, 0x2C, 0x46)
GRAY = RGBColor(0x5D, 0x6D, 0x84)
ACCENT = RGBColor(0xB4, 0x23, 0x18)


# ---------------------------------------------------------------- 基础工具
def _font(run, name_cn="宋体", name_en="Times New Roman", size=10.5,
          bold=False, color=None):
    run.font.name = name_en
    run.font.size = Pt(size)
    run.bold = bold
    if color is not None:
        run.font.color.rgb = color
    rpr = run._element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.append(rf)
    rf.set(qn("w:eastAsia"), name_cn)


def _shade(cell, hex_color: str):
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcpr.append(shd)


def _cell_borders(cell, color="D8E0EA", sz=4):
    tcpr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement("w:%s" % edge)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(sz))
        el.set(qn("w:color"), color)
        borders.append(el)
    tcpr.append(borders)


def _emit(p, text, size=10.5, color=INK, cn="宋体", name_en="Times New Roman"):
    """把 **加粗** 标记解析成加粗 run，避免星号出现在正文里。"""
    for i, seg in enumerate(text.split("**")):
        if not seg:
            continue
        r = p.add_run(seg)
        _font(r, name_cn=cn, name_en=name_en, size=size, bold=(i % 2 == 1), color=color)


def para(doc, text, size=10.5, color=INK, bold=False, space_before=0,
         space_after=6, line=1.7, indent_first=0, align=None, cn="宋体"):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    pf.line_spacing = line
    if indent_first:
        pf.first_line_indent = Cm(indent_first)
    if align is not None:
        p.alignment = align
    if "**" in text:
        _emit(p, text, size=size, color=color, cn=cn)
    else:
        r = p.add_run(text)
        _font(r, name_cn=cn, size=size, bold=bold, color=color)
    return p


def rich_para(doc, chunks, size=10.5, line=1.7, space_before=0, space_after=6):
    """chunks: [(text, bold, color)]"""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(space_before)
    pf.space_after = Pt(space_after)
    pf.line_spacing = line
    for text, bold, color in chunks:
        r = p.add_run(text)
        _font(r, size=size, bold=bold, color=color)
    return p


def h1(doc, num, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run("%s  %s" % (num, text))
    _font(r, name_cn="微软雅黑", name_en="Segoe UI", size=15, bold=True, color=NAVY)
    # 下边框
    ppr = p._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), "1A3A6B")
    pbdr.append(bottom)
    ppr.append(pbdr)
    return p


def h2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(5)
    r = p.add_run(text)
    _font(r, name_cn="微软雅黑", name_en="Segoe UI", size=11.5, bold=True, color=INK)
    return p


def bullet(doc, text, bold_head=None):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Cm(0.75)
    pf.first_line_indent = Cm(-0.4)
    pf.space_after = Pt(4)
    pf.line_spacing = 1.6
    circled = bool(bold_head) and 0x2460 <= ord(bold_head[0]) <= 0x2473
    if not circled:
        r0 = p.add_run("· ")
        _font(r0, size=10.5, bold=True, color=NAVY)
    if bold_head:
        r1 = p.add_run(bold_head)
        _font(r1, size=10.5, bold=True, color=INK)
    _emit(p, text, size=10.5, color=INK)
    return p


def table(doc, headers, rows, widths, font_size=9, highlight_rows=()):
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    _fixed_layout(t, widths)
    trPr = t.rows[0]._tr.get_or_add_trPr()
    th = OxmlElement("w:tblHeader"); th.set(qn("w:val"), "true"); trPr.append(th)
    cs = OxmlElement("w:cantSplit"); cs.set(qn("w:val"), "true"); trPr.append(cs)
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after = Pt(3)
        r = p.add_run(h)
        _font(r, name_cn="微软雅黑", name_en="Segoe UI", size=font_size,
              bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
        _shade(hdr[i], "27456E")
        _cell_borders(hdr[i])
        hdr[i].width = Cm(widths[i])

    for ri, row in enumerate(rows):
        new_row = t.add_row()
        trPr2 = new_row._tr.get_or_add_trPr()
        cs2 = OxmlElement("w:cantSplit"); cs2.set(qn("w:val"), "true"); trPr2.append(cs2)
        cells = new_row.cells
        for ci, val in enumerate(row):
            cells[ci].text = ""
            p = cells[ci].paragraphs[0]
            p.paragraph_format.space_before = Pt(2.5)
            p.paragraph_format.space_after = Pt(2.5)
            p.paragraph_format.line_spacing = 1.3
            bold = ci == 0
            r = p.add_run(str(val))
            _font(r, name_cn="微软雅黑", name_en="Segoe UI", size=font_size - 0.3,
                  bold=bold, color=INK)
            _cell_borders(cells[ci])
            cells[ci].width = Cm(widths[ci])
            if ri in highlight_rows:
                _shade(cells[ci], "FDF3F2")
            elif ri % 2 == 1:
                _shade(cells[ci], "F7F9FC")
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def _fixed_layout(t, widths):
    """强制固定列宽，避免 Word 按内容自动撑宽导致溢出页边距。"""
    tbl = t._tbl
    tblPr = tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)
    tblW = OxmlElement("w:tblW")
    tblW.set(qn("w:type"), "dxa")
    tblW.set(qn("w:w"), str(int(sum(widths) * 567)))
    tblPr.append(tblW)
    grid = tbl.find(qn("w:tblGrid"))
    if grid is not None:
        for i, gc in enumerate(grid.findall(qn("w:gridCol"))):
            if i < len(widths):
                gc.set(qn("w:w"), str(int(widths[i] * 567)))


def caption(doc, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run(text)
    _font(r, name_cn="微软雅黑", name_en="Segoe UI", size=8.5, color=GRAY)
    return p


def callout(doc, title, body):
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    trPr = t.rows[0]._tr.get_or_add_trPr()
    cs = OxmlElement("w:cantSplit")
    cs.set(qn("w:val"), "true")
    trPr.append(cs)
    cell = t.rows[0].cells[0]
    _shade(cell, "F4F7FB")
    _cell_borders(cell, color="C9D6E6", sz=6)
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run(title)
    _font(r, name_cn="微软雅黑", name_en="Segoe UI", size=10, bold=True, color=NAVY)
    p2 = cell.add_paragraph()
    p2.paragraph_format.space_after = Pt(7)
    p2.paragraph_format.line_spacing = 1.6
    _emit(p2, body, size=10, color=INK)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def add_page_number_footer(section, text):
    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(text + "    第 ")
    _font(r, name_cn="微软雅黑", name_en="Segoe UI", size=8, color=GRAY)
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    run_el = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    sz = OxmlElement("w:sz"); sz.set(qn("w:val"), "16"); rpr.append(sz)
    run_el.append(rpr)
    t = OxmlElement("w:t"); t.text = "1"; run_el.append(t)
    fld.append(run_el)
    p._p.append(fld)
    r2 = p.add_run(" 页")
    _font(r2, name_cn="微软雅黑", name_en="Segoe UI", size=8, color=GRAY)


# ---------------------------------------------------------------- 文档构建
def build():
    doc = Document()

    # 页面：A4
    sec = doc.sections[0]
    sec.page_width = Cm(21)
    sec.page_height = Cm(29.7)
    sec.left_margin = Cm(2.4)
    sec.right_margin = Cm(2.4)
    sec.top_margin = Cm(2.4)
    sec.bottom_margin = Cm(2.2)
    add_page_number_footer(sec, "支付对账与差错追踪 · 行业分析")

    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(10.5)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

    # ---------------- 封面 ----------------
    for _ in range(5):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run("恒川支付运营 · 支付对账与差错追踪")
    _font(r, name_cn="微软雅黑", name_en="Segoe UI", size=12, color=GRAY)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    r = p.add_run("行业分析与技术可行性")
    _font(r, name_cn="微软雅黑", name_en="Segoe UI", size=32, bold=True, color=NAVY)

    p = doc.add_paragraph()
    r = p.add_run("渠道账单与交易流水差异定位 · 可比实践、口径辨析与适用性评估")
    _font(r, name_cn="微软雅黑", name_en="Segoe UI", size=12.5, color=GRAY)

    # 分隔线
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    ppr = p._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single"); bottom.set(qn("w:sz"), "12")
    bottom.set(qn("w:space"), "1"); bottom.set(qn("w:color"), "27456E")
    pbdr.append(bottom); ppr.append(pbdr)

    for _ in range(2):
        doc.add_paragraph()

    meta = [
        ("文档类型", "行业分析（Industry 视角）"),
        ("适用项目", "支付对账与差错追踪 · 单渠道离线差异定位"),
        ("配套文件", "业务需求发现报告 / 需求优先级与切入点 / 解决方案设计"),
        ("版本", "v1.0"),
        ("编制日期", "2026 年 10 月 29 日"),
        ("资料来源", "公开案例、厂商公开基准、行业调研摘要（见第八节）"),
    ]
    t = doc.add_table(rows=0, cols=2)
    t.autofit = False
    for k, v in meta:
        cells = t.add_row().cells
        cells[0].width = Cm(3.4)
        cells[1].width = Cm(12.4)
        p0 = cells[0].paragraphs[0]
        r0 = p0.add_run(k)
        _font(r0, name_cn="微软雅黑", name_en="Segoe UI", size=9.5, color=GRAY)
        p1 = cells[1].paragraphs[0]
        r1 = p1.add_run(v)
        _font(r1, name_cn="微软雅黑", name_en="Segoe UI", size=9.5, color=INK)

    doc.add_page_break()

    # ---------------- 一、结论摘要 ----------------
    h1(doc, "一", "结论摘要")
    para(doc, "本节先给结论，后文再给依据。所有数据均标注来源与统计口径，未标注来源的判断为本文分析。",
         color=GRAY, size=9.5)

    callout(doc, "一句话结论",
            "对账自动化是成熟品类而非试验性技术，但行业公开的自动匹配率天花板在 89%–95%，"
            "不存在“全部自动匹配”的成熟实践。本项目提出的“99.9% 匹配准确率”只有按“已匹配项中结论正确的比例”"
            "理解才成立；若被理解为“自动匹配覆盖率”，则超出当前行业水平，必须在验收前完成口径定义。")

    bullet(doc, "对账自动化已进入规模化落地阶段。Gartner 2025 年调研显示，68% 的财务负责人将对账自动化列为计划中的 AI 投入，41% 已在生产环境使用；"
                "在“已产生可衡量 ROI”的 AI 场景中，支付对账排名第二。",
           bold_head="技术已成熟，不是尝鲜。")
    bullet(doc, "BlackLine 2025 年企业客户基准 91%（上线满 12 个月）、Trintech Cadency 高频账户 93%、Xero 直通率 89%、"
                "结构化结算数据（Stripe / Adyen / Square）92%–96%。没有任何公开案例宣称全量自动匹配。",
           bold_head="自动匹配率的天花板是 89%–95%。")
    bullet(doc, "四川银行新一代对账系统 2025 年 5–12 月累计处理差错 5790 笔，其中系统自动处理 5681 笔、人工仅 109 笔，"
                "自动处理比例约 98.1%，对账效率从小时级降到分钟级。这说明“差错自动定性”在国内已有工程化先例。",
           bold_head="国内支付机构侧可达 98% 以上的差错自动处理。")
    bullet(doc, "Trintech 2025 年数据显示：参考字段一致的场景匹配率 91%，字段不一致或缺失时降到 76%，相差 15 个百分点，"
                "其变异性超过交易量、账户类型和行业因素。这与本项目“主编号关系不完整、时区不一致”的判断完全一致。",
           bold_head="决定匹配率的第一变量是数据质量，不是算法。")
    bullet(doc, "行业用 auto-match rate（覆盖率），本项目要求的是 precision（准确率）。前者可以通过放宽规则做高，"
                "后者只能通过收紧规则和前置质控做高——方向相反。口径不定义，两个方向都能“做出”漂亮数字。",
           bold_head="最大的风险是口径混用。")

    # ---------------- 二、行业背景 ----------------
    h1(doc, "二", "行业背景：对账为什么仍然靠人")

    h2(doc, "2.1 交易规模与对账数据倍率")
    para(doc, "支付对账的工作量并不等于交易笔数。四川银行案例披露，其支付通道对账涉及外部机构、行内支付系统、核心系统三方数据核对，"
              "每日处理的对账数据量为交易量的 3 倍。该行 2025 年 5–12 月累计处理支付交易 24255.19 万笔、金额 10.59 万亿元，"
              "日均 108.77 万笔，单日峰值 139.07 万笔。", indent_first=0.74)
    para(doc, "本项目现状为每日 80 万笔（f12），与上述案例处于同一量级。这意味着：单机批处理即可支撑，不需要引入分布式引擎；"
              "但“3 倍数据量、多源核对”的复杂度是真实存在的，不能按单表比对的思路设计。", indent_first=0.74)

    h2(doc, "2.2 为什么人工负荷没有随技术下降")
    para(doc, "J.P. Morgan 2025 年对 400 位企业财资与财务负责人的调研显示，61% 的受访者认为支付对账是其最耗时的手工流程，"
              "而 2022 年这一比例是 44%。比例上升的原因不是技术退步，而是数字支付渠道扩张带来的交易量增长没有伴随人头增长。", indent_first=0.74)
    para(doc, "国内中小微场景的对照数据更直观：邮储银行“收款伴侣”智能对账系统上线后，某批发零售企业月底对账周期从 3 人加班 3 天缩短到 5 小时。"
              "这类案例的共同点不是“算法多先进”，而是把“逐笔翻流水”换成了“系统归集 + 自动匹配 + 异常集中处理”。", indent_first=0.74)

    callout(doc, "对项目的含义",
            "本项目的价值不在“用 AI 替代人”，而在把 80 万笔中的绝大多数变成“无需人工介入的正常项”，"
            "把人力集中到真正需要判断的少数差异上。这与行业实践的方向一致。")

    # ---------------- 三、技术谱系 ----------------
    h1(doc, "三", "技术实践谱系：四代方案与各自边界")
    para(doc, "对账技术并非单点突破，而是沿着“确定性 → 概率性 → 规模化 → 归因化”演进的四层能力。"
              "理解每一层的边界，比选择某一层更重要。", indent_first=0.74)

    table(doc,
          ["代际", "核心方法", "典型能力", "失效条件", "本项目采用"],
          [
              ["第一代\n规则引擎", "主键 + 金额 + 交易类型精确比对",
               "覆盖 70%–85% 的正常交易，结果完全可解释",
               "主键缺失、时区不一致、合并入账时直接失效", "采用\n（L1 / L2 层）"],
              ["第二代\n模糊匹配", "金额 + 时间窗 + 商户号多键加权，相似度阈值",
               "回收主键缺失场景的 5%–10%",
               "同额多笔时产生误匹配，且难以自证", "有限采用\n（L3 层降级为候选）"],
              ["第三代\n分布式批处理", "分片并行（MapReduce / Spark），按渠道/日期切分",
               "支撑 10 亿级日交易，某平台把对账耗时从 4 小时压到 30 分钟",
               "解决的是吞吐问题，不解决口径与质量问题", "预留\n（当前单机足够）"],
              ["第四代\nAI 归因", "规则 + 模型对异常做原因归类，输出处置建议",
               "把“哪笔对不上”推进到“为什么对不上”",
               "幻觉、不可解释、审计难追溯", "采用保守形态\n（有限枚举 + 证据引用）"],
          ],
          widths=[2.0, 3.8, 4.0, 3.8, 2.4])
    caption(doc, "表 1  对账技术四代能力谱系与本项目取舍")

    para(doc, "值得单独说明两点：", indent_first=0.74)
    bullet(doc, "第四代的“AI 归因”在工程上最容易被做成黑箱。四川银行的做法是“系统自动识别并处理 99% 的常见差错”，"
                "即把 AI 能力约束在**已知差错类型**上，而不是让它自由生成结论。本项目采用“10 类有限原因码 + 证据引用”的设计，"
                "正是同一思路的低配版本：宁可少归因，不可乱归因。",
           bold_head="AI 归因要约束在已知类型上。")
    bullet(doc, "区块链“天然对账”在跨境与联盟链场景已有试点（如 JPM Coin 用于跨境实时清算），但前提是参与方共享同一账本。"
                "本项目面对的是外部渠道的既有结算文件，不具备该前提，不纳入技术选型。",
           bold_head="区块链方案不适用。")

    # ---------------- 四、标杆数据 ----------------
    h1(doc, "四", "标杆实践与公开基准数据")
    para(doc, "下表汇总可公开查证的自动匹配率数据。需要强调：这些数字的统计对象、分母与排除规则各不相同，"
              "**不能直接横向比较，更不能直接作为本项目的验收基线**。", indent_first=0.74)

    table(doc,
          ["来源 / 场景", "统计口径", "公开数据", "出处"],
          [
              ["四川银行 新一代对账系统", "支付通道三方对账，差错自动处理比例", "98.1%（5681 / 5790 笔）",
               "金融科技创新案例，2025"],
              ["BlackLine 企业客户", "交易匹配自动率，上线 ≥12 个月", "91%（新上线 <6 个月为 78%）", "BlackLine 2025 基准"],
              ["Trintech Cadency", "高频账户（>500 笔/月）", "93%（低频账户 84%）", "Trintech 2025 客户数据"],
              ["Xero", "银行流水匹配建议率 / 用户采纳率", "95% / 94%，直通率 89%", "Xero 2025 内部基准"],
              ["Stripe / Adyen / Square", "结构化结算数据 vs 收入记录", "92%–96%", "Levvel Research 2025"],
              ["AFP 支付调研", "需人工复核的例外率", "境内 9%，跨境 17%", "AFP 2025 Payments Survey"],
              ["IOFM", "成熟 AP 付款匹配直通率", "87%–92%（新上线 68%–75%）", "IOFM 2025 AP 基准"],
              ["邮储银行 收款伴侣", "中小微企业月底对账周期", "3 天 → 5 小时", "新华网，2025-12"],
          ],
          widths=[4.0, 4.4, 4.2, 3.4])
    caption(doc, "表 2  公开可查的自动匹配率与效率基准（口径各异，仅供区间参考）")

    para(doc, "从这张表可以读出三个稳定结论：", indent_first=0.74)
    bullet(doc, "无论厂商规模，公开的自动匹配率都落在 89%–96% 区间；超过 97% 的只有“差错自动处理”这类更窄的口径"
                "（只统计已识别为差错的部分，分母不含正常交易）。",
           bold_head="区间高度收敛。")
    bullet(doc, "BlackLine 新上线客户 78%，成熟客户 91%；IOFM 新上线 68%–75%，成熟 87%–92%。上线半年内的表现显著低于稳态，"
                "原因是模型需要积累纠正样本。本项目首期只有单渠道单日回放，**不具备达到稳态的条件**。",
           bold_head="成熟期与上线初期差 10–15 个百分点。")
    bullet(doc, "成熟厂商用 91% 的自动匹配率服务企业客户，同时把 9% 的例外交给人工，并把这 9% 定义为“正常运营成本”而非“系统缺陷”。"
                "本项目把 100% 可查原因作为质量标准，本质是把 9% 的例外也纳入了质量范围——这是更严的要求，需要更长的验证周期。",
           bold_head="例外率是设计的一部分。")

    # ---------------- 五、口径辨析 ----------------
    h1(doc, "五", "关键辨析：自动匹配率 ≠ 匹配准确率")
    para(doc, "这是本报告最重要的一节，也是决定 99.9% 能否验收的地方。", indent_first=0.74)

    table(doc,
          ["维度", "自动匹配率（auto-match rate）", "匹配准确率（precision）"],
          [
              ["定义", "系统自动给出结论的笔数 ÷ 全部笔数", "结论正确的笔数 ÷ 系统自动给出结论的笔数"],
              ["行业水平", "89%–96%（见表 2）", "四川银行差错自动处理正确率约 98.1%"],
              ["本项目要求", "未定义", "99.9%（f02 / f42）"],
              ["提高方式", "放宽匹配规则（金额+时间窗兜底更多）", "收紧规则 + 前置质控（牺牲覆盖率）"],
              ["典型风险", "把“匹配不上”伪装成“匹配上”", "通过排除规则把分母做小"],
              ["对应业务指标", "自动化程度、人工负荷", "结论可信度、复核返工率"],
          ],
          widths=[2.6, 6.8, 6.6], highlight_rows=(2,))
    caption(doc, "表 3  两种口径的定义、水平与风险对比")

    para(doc, "把这两个口径放在一起看，会发现一个必须写进验收文件的事实：", indent_first=0.74)
    callout(doc, "口径判定",
            "99.9% 只能按 precision 理解——即“系统给出的每 1000 条结论里，错误不超过 1 条”。"
            "若按 auto-match rate 理解，则意味着 99.9% 的结算行都能被自动匹配，这超出当前所有公开实践（最高 96%），"
            "在首期单渠道回放中不可达。")

    para(doc, "由此推出三条验收前提，缺一不可：", indent_first=0.74)
    bullet(doc, "分母必须固定为“进入自动匹配的笔数”，且排除项（修复队列、低置信转人工、快照过期）"
                "必须与指标同时披露。只报准确率不报排除项，等于允许通过扩大排除范围抬高比例（f53 已明确禁止）。",
           bold_head="① 分母固定。")
    bullet(doc, "差异“可查原因”必须有字段清单，缺任一字段即判为未解释。否则“有原因”会退化为一句模糊备注，"
                "与行业里“匹配上了但说不清为什么”的常见问题同源。",
           bold_head="② 字段固定。")
    bullet(doc, "首期应同时报告覆盖率与准确率：覆盖率说明自动化程度（对标行业 89%–96%），准确率说明结论可信度。"
                "只报一个数，管理层与风险侧会各自得出相反结论。",
           bold_head="③ 双指标并行。")

    # ---------------- 六、适用性差异 ----------------
    h1(doc, "六", "行业通用实践与本项目的适用性差异")
    para(doc, "行业方案默认的前提，在本项目里多数不成立。下表逐项对照，这是判断“能不能照搬”的依据。",
         indent_first=0.74)

    table(doc,
          ["维度", "行业通用实践", "本项目约束（事实依据）", "对方案的影响"],
          [
              ["数据质量", "结算文件结构化，参考字段完整，主键可直接关联",
               "交易号、商户订单号、渠道号关系不完整，时区不一致（f31）",
               "匹配率将明显低于行业基准；必须先做字段级质控，否则算法背锅数据问题"],
              ["数据接口", "API 准实时直连，或 T+1 全量文件",
               "每天两次只读快照，超期标“待刷新”（f34 / f35）",
               "不能承诺实时性；界面必须显式标注快照时间，匹配结果随快照版本变化"],
              ["权限模型", "系统账号 + 角色，按功能授权",
               "按岗位最小化，禁止借用他人账号（f41）",
               "需要按岗位裁剪视图，同一差异对不同岗位展示不同字段"],
              ["处置能力", "自动冲正、自动补单、自动生成调整分录",
               "只读，不进行任何自主资金操作（f05 / f52）",
               "行业方案的核心卖点（自动处置）在本项目全部不可用，只能做建议"],
              ["审计要求", "操作日志 + 审批流",
               "六要素可重建全链路、不记口令（f45）",
               "留痕要求高于通用产品，需要设计专门的审计数据结构"],
              ["复核机制", "按金额阈值分级审批",
               "资金调整强制双人复核，不可绕过（f40）",
               "必须在流程中设置硬约束，而不是依赖制度约束"],
          ],
          widths=[2.2, 4.6, 5.0, 4.2])
    caption(doc, "表 4  行业通用前提与本项目约束的逐项对照")

    para(doc, "这张表解释了一个常见误判：把行业产品的“自动匹配率 91%”直接搬来作为本项目承诺，"
              "却忽略了对方的数据前提（参考字段完整）和处置权限（可自动调账）。本项目两者都不具备，"
              "预期必须以“质控后的真实水平”重新校准。", indent_first=0.74)

    # ---------------- 七、可行性结论 ----------------
    h1(doc, "七", "可行性判定与建议动作")

    h2(doc, "7.1 四维可行性")
    table(doc,
          ["维度", "判定", "依据", "前置条件"],
          [
              ["技术可行性", "高",
               "单渠道单日 80 万笔量级，规则引擎 + 轻量模型即可；国内已有 98% 差错自动处理的工程先例",
               "无"],
              ["数据可行性", "中偏低",
               "主编号完整率、时区冲突率尚未实测；这两个指标直接决定匹配率上限",
               "先完成字段级质量校验回放（REQ-1）"],
              ["组织可行性", "中",
               "跨岗交接规则未固化，转人工分派机制未定（f23 / f25 / f44）",
               "书面确认分派与确认口径"],
              ["合规可行性", "高",
               "只读、无资金动作、双人复核与审计留痕可满足（f40 / f45）",
               "权限按岗位最小化落地"],
          ],
          widths=[2.4, 2.0, 7.0, 4.6], highlight_rows=(1,))
    caption(doc, "表 5  四维可行性判定")

    para(doc, "综合结论：**有条件可行**。条件不是技术能力，而是三件事——口径先定义、质控先回放、边界先固化。",
         indent_first=0.74)

    h2(doc, "7.2 建议的三个动作（按顺序，不可并行）")
    bullet(doc, "取单个渠道近两周真实账单与流水，跑字段级校验清单，统计主编号缺失率、时区冲突笔数、进修复队列比例。"
                "这一步产出的不是准确率，而是**匹配率的上限**——如果 30% 的记录主编号不完整，任何算法都到不了 99.9%。",
           bold_head="动作一：测上限。")
    bullet(doc, "用同一批数据分别计算“覆盖率”与“准确率”，把两个数放进同一张表给顾明岚与傅景看。"
                "预期结果是覆盖率 85%–93%、准确率 99% 以上——这个组合恰好对应行业基准，也能解释为什么不能承诺 99.9% 的覆盖率。",
           bold_head="动作二：双口径复算。")
    bullet(doc, "把表 2 的行业基准写进项目预期管理材料，明确“自动匹配率 89%–96% 是常态，例外率 4%–11% 是设计的一部分”。"
                "避免用覆盖率口径的承诺去承接准确率口径的验收。",
           bold_head="动作三：校准预期。")

    callout(doc, "对需求报告的回应",
            "需求报告 REQ-1 主张“先建质量校验再谈匹配优化”，本节数据给出了量化支撑：参考字段质量带来的匹配率差异达 15 个百分点，"
            "超过交易量、账户类型、行业等因素的影响。这条建议不是保守，而是行业数据支持的最优顺序。")

    # ---------------- 八、参考资料 ----------------
    h1(doc, "八", "参考资料")
    refs = [
        "四川银行：新一代对账系统——数字运营引领流程优化与产品体验跃升. 金科创新社, 2025.",
        "BlackLine 2025 Transaction Matching Benchmarks（企业客户自动匹配率基准）.",
        "Trintech Cadency 2025 Customer Success Data（高低频账户匹配率对比）.",
        "Xero 2025 Internal Benchmarks（银行流水匹配建议率与采纳率）.",
        "Levvel Research 2025：支付处理商结算数据匹配率研究.",
        "AFP 2025 Payments Survey（境内/跨境支付例外率）.",
        "IOFM 2025 State of AP（付款匹配直通率基准）.",
        "J.P. Morgan 2025 Treasury Services Benchmarking（400 位财资负责人调研）.",
        "Gartner 2025 CFO and Finance Technology Survey（对账 AI 投入与落地比例）.",
        "HighRadius：Bank / Credit Card Reconciliation Software 产品基准页, 2025.",
        "新华网：邮储银行遵义市分行“收款伴侣”智能对账系统案例, 2025-12.",
        "支付结算系统资金流水自动对账的底层逻辑与实战解析, 2025.",
    ]
    for i, r in enumerate(refs, 1):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.left_indent = Cm(0.9)
        pf.first_line_indent = Cm(-0.9)
        pf.space_after = Pt(3)
        pf.line_spacing = 1.5
        rr = p.add_run("[%d] %s" % (i, r))
        _font(rr, size=9, color=GRAY)

    para(doc, "说明：以上均为公开资料，统计口径互不相同，本文引用仅用于判断行业区间与量级，未做二次测算。"
              "涉及本项目的基线数据（80 万笔/日、5 小时、6 小时、26 万元预算等）均来自业务需求发现报告的事实编号，"
              "属访谈口径，尚未经实测验证。", size=9, color=GRAY, space_before=8)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    doc.save(OUT)
    print("已生成：%s" % OUT)
    return OUT


if __name__ == "__main__":
    build()
