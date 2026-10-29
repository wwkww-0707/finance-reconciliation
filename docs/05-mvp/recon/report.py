# -*- coding: utf-8 -*-
"""
静态 HTML 复核台渲染。

单文件输出（数据内联 + 原生 JS 过滤/下钻），双击即可打开，
也可以由 server.py 直接复用同一套渲染做在线重跑。
"""

from __future__ import annotations

import json

DISPO_COLOR = {
    "ESCALATE": "#b42318",
    "HUMAN_CHECK": "#b54708",
    "REPAIR_QUEUE": "#3538cd",
    "AUTO_OK": "#067647",
}

TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#f4f6fa;color:#1b2431;font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:1240px;margin:0 auto;padding:26px 22px 60px}
.top{display:flex;flex-wrap:wrap;gap:14px;align-items:flex-end;justify-content:space-between;border-bottom:2px solid #1b3a63;padding-bottom:14px;margin-bottom:22px}
h1{margin:0;font-size:21px;letter-spacing:.2px}
.sub{color:#5b6779;font-size:12.5px;margin-top:4px}
.chips{display:flex;gap:8px;flex-wrap:wrap}
.chip{background:#fff;border:1px solid #dde3ec;border-radius:100px;padding:5px 12px;font-size:12px;color:#3b4759}
.chip b{color:#1b3a63}
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:24px}
.kpi{background:#fff;border:1px solid #e3e8f0;border-radius:10px;padding:14px 15px;position:relative;overflow:hidden}
.kpi:after{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:#1b3a63}
.kpi.ok:after{background:#0a8f4d}.kpi.warn:after{background:#c2410c}
.kpi .l{font-size:11.5px;color:#68748a;letter-spacing:.3px}
.kpi .v{font-size:22px;font-weight:650;margin:5px 0 2px;font-variant-numeric:tabular-nums}
.kpi .h{font-size:11px;color:#8a95a6;line-height:1.45}
h2{font-size:15px;margin:30px 0 12px;padding-left:10px;border-left:4px solid #1b3a63}
h2 span{font-weight:400;font-size:12px;color:#7a8598;margin-left:8px}
.card{background:#fff;border:1px solid #e3e8f0;border-radius:10px;padding:4px 0;overflow:hidden}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{background:#f7f9fc;color:#4a5568;font-weight:600;text-align:left;padding:9px 12px;border-bottom:1px solid #e8ecf3;white-space:nowrap}
td{padding:8px 12px;border-bottom:1px solid #f0f3f8;vertical-align:top}
tr:last-child td{border-bottom:0}
tr.d{ cursor:pointer}
tr.d:hover{background:#f8fafd}
.num{font-variant-numeric:tabular-nums;text-align:right}
.tag{display:inline-block;padding:1.5px 8px;border-radius:5px;font-size:11px;font-weight:600;color:#fff}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;color:#3d4a5f}
.filters{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:10px}
.f{background:#fff;border:1px solid #dde3ec;border-radius:6px;padding:4px 11px;font-size:12px;cursor:pointer;color:#3b4759}
.f.on{background:#1b3a63;border-color:#1b3a63;color:#fff}
.f b{margin-left:5px;opacity:.75}
.empty{padding:22px;text-align:center;color:#8a95a6;font-size:12.5px}
.note{font-size:11.5px;color:#7a8598;margin:8px 2px 0}
.detail{background:#fbfcfe;border:1px solid #e3e8f0;border-radius:10px;padding:16px 18px;margin-top:12px;display:none}
.detail.show{display:block}
.detail h3{margin:0 0 10px;font-size:13.5px}
.kv{display:grid;grid-template-columns:104px 1fr;gap:7px 12px;font-size:12.5px}
.kv dt{color:#7a8598}
.kv dd{margin:0;color:#25303f}
.spec{display:grid;grid-template-columns:130px 1fr;gap:0}
.spec div{padding:10px 14px;border-bottom:1px solid #f0f3f8;font-size:12.5px}
.spec div:nth-child(odd){color:#5b6779;background:#fbfcfe}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.hl{background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:11px 14px;font-size:12.5px;color:#8a5c00;margin-top:14px;line-height:1.65}
.hl b{color:#7c3d00}
footer{margin-top:34px;padding-top:14px;border-top:1px solid #e3e8f0;color:#8a95a6;font-size:11.5px;line-height:1.8}
.warnbox{background:#fef3f2;border:1px solid #fecdca;border-radius:8px;padding:11px 14px;font-size:12.5px;color:#912018;margin-top:14px}
@media (max-width:1000px){.kpis{grid-template-columns:repeat(3,1fr)}.two{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <h1>__PROJECT__</h1>
      <div class="sub">渠道账单与交易流水差异定位 · 离线回放复核台 · 只读，不产生任何资金操作</div>
    </div>
    <div class="chips">
      <div class="chip">渠道 <b>__CHANNEL__</b></div>
      <div class="chip">结算日 <b>__DATE__</b></div>
      <div class="chip">资料版本 <b>v__VER__</b></div>
      <div class="chip">规则 <b>__RULE__</b></div>
    </div>
  </div>
  <div class="kpis" id="kpis"></div>

  <h2>指标口径<span>口径不定则 99.9% 无法验收（REQ-3）</span></h2>
  <div class="card"><div class="spec" id="spec"></div></div>

  <h2>差异清单<span id="diffCount"></span></h2>
  <div class="filters" id="filters"></div>
  <div class="card"><table id="diffTable"></table></div>
  <div class="detail" id="detail"></div>

  <div class="two">
    <div>
      <h2>人工修复队列<span>不进入自动匹配样本（f33）</span></h2>
      <div class="card"><table id="repairTable"></table></div>
    </div>
    <div>
      <h2>字段级质量校验<span>匹配前置</span></h2>
      <div class="card"><table id="checkTable"></table></div>
    </div>
  </div>

  <h2>转人工工单<span>四类触发条件必须标注原因、接手人、确认时间（f44）</span></h2>
  <div class="card"><table id="ticketTable"></table></div>

  <h2>六节点耗时<span>系统实测 vs 访谈基线（基线为假设，不与实测混算）</span></h2>
  <div class="card"><table id="nodeTable"></table></div>

  <h2>审计留痕<span>哈希链，可重建“归集→复核”全链路（f45）</span></h2>
  <div class="card"><table id="auditTable"></table></div>
  <div id="auditMsg"></div>

  <footer>
    本报告基于合成样本生成，用于验证流程与口径，不代表真实业务结论。<br>
    生成时间 __GENERATED__ · 引擎 recon-engine __RULE__ · 仅只读建议，不参与退款、调账或资金划转（f05/f32/f52）
  </footer>
</div>
<script>
const DATA = __DATA__;
const DISPO = {ESCALATE:["#b42318","转人工"],HUMAN_CHECK:["#b54708","需确认"],REPAIR_QUEUE:["#3538cd","修复队列"],AUTO_OK:["#067647","自动通过"]};
const COLORS = __COLORS__;

function yuan(c){return (c/100).toFixed(2)}
function el(tag,cls,html){const e=document.createElement(tag);if(cls)e.className=cls;if(html!=null)e.innerHTML=html;return e}

// ---------- KPI ----------
const kw=document.getElementById('kpis');
DATA.kpi.kpi.forEach(k=>{
  const d=el('div','kpi'+(k.flag===true?' ok':(k.flag===false?' warn':'')));
  d.appendChild(el('div','l',k.label));
  d.appendChild(el('div','v',k.value));
  d.appendChild(el('div','h',k.hint||''));
  kw.appendChild(d);
});

// ---------- 口径 ----------
const sp=document.getElementById('spec');
Object.entries(DATA.kpi.spec).forEach(([k,v])=>{
  sp.appendChild(el('div',null,k));
  sp.appendChild(el('div',null,v));
});

// ---------- 差异清单 ----------
const diffs=DATA.diffs;
document.getElementById('diffCount').textContent='共 '+diffs.length+' 笔，其中未解释 '+DATA.kpi.unexplained+' 笔';
const counts={};diffs.forEach(d=>counts[d.reason_code]=(counts[d.reason_code]||0)+1);
let active='ALL';
const fw=document.getElementById('filters');
const mkF=(key,label,n)=>{
  const b=el('div','f'+(active===key?' on':''),label+' <b>'+n+'</b>');
  b.onclick=()=>{active=key;[...fw.children].forEach(c=>c.classList.remove('on'));b.classList.add('on');renderDiffs()};
  fw.appendChild(b);
};
mkF('ALL','全部',diffs.length);
Object.keys(counts).sort().forEach(c=>mkF(c,c+' '+(COLORS[c]?COLORS[c][0]:''),counts[c]));

function renderDiffs(){
  const t=document.getElementById('diffTable');
  const all=diffs.filter(d=>active==='ALL'||d.reason_code===active);
  const rows=all.slice(0,60);
  let h='<thead><tr><th>业务编号</th><th>原因码</th><th>原因</th><th>侧</th><th class="num">金额(元)</th><th>定位方法</th><th class="num">置信</th><th>处置</th><th>可查原因</th></tr></thead><tbody>';
  rows.forEach((d,i)=>{
    const c=DISPO[d.disposition]||['#667','—'];
    h+='<tr class="d" data-i="'+diffs.indexOf(d)+'">'
      +'<td class="mono">'+d.biz_no+'</td>'
      +'<td><span class="tag" style="background:'+c[0]+'">'+d.reason_code+'</span></td>'
      +'<td>'+d.reason_title+'</td>'
      +'<td>'+d.side+'</td>'
      +'<td class="num">'+yuan(d.amount_cents)+'</td>'
      +'<td class="mono">'+d.method+'</td>'
      +'<td class="num">'+(d.confidence?d.confidence.toFixed(2):'—')+'</td>'
      +'<td style="color:'+c[0]+';font-weight:600">'+c[1]+'</td>'
      +'<td>'+(d.explained?'<span style="color:#067647">✓ 齐全</span>':'<span style="color:#b42318">缺 '+d.missing_fields.join(',')+'</span>')+'</td></tr>';
  });
  if(all.length>rows.length){h+='<tr><td colspan="9" style="color:#7a8598;font-size:11.5px">仅显示前 60 笔，共 '+all.length+' 笔；完整清单见 sample/out/差异清单_diff_list.csv</td></tr>'}
  t.innerHTML=h+'</tbody>';
  [...t.querySelectorAll('tr.d')].forEach(tr=>tr.onclick=()=>showDetail(diffs[+tr.dataset.i]));
}
function showDetail(d){
  const box=document.getElementById('detail');
  const c=DISPO[d.disposition]||['#667','—'];
  box.innerHTML='<h3><span class="tag" style="background:'+c[0]+'">'+d.reason_code+'</span> '+d.reason_title
    +' <span class="mono" style="color:#7a8598">'+d.biz_no+'</span></h3>'
    +'<div class="kv">'
    +'<dt>根因</dt><dd>'+d.root_cause+'</dd>'
    +'<dt>本次观察</dt><dd>'+d.note+'</dd>'
    +'<dt>证据引用</dt><dd class="mono">'+d.evidence_refs.join('<br>')+'</dd>'
    +'<dt>建议动作</dt><dd>'+d.suggestion+'</dd>'
    +'<dt>规则版本</dt><dd>'+d.rule_version+' · 资料版本 v'+d.snapshot_version+'</dd>'
    +'<dt>校验器</dt><dd class="mono">'+d.checker+'</dd>'
    +'<dt>处置</dt><dd style="color:'+c[0]+';font-weight:600">'+c[1]+'</dd>'
    +'</div>'
    +'<div class="hl"><b>责任边界：</b>系统只给差异定位与建议，不执行退款、调账、划转；涉及资金动作的处置须双人复核（f40）。</div>';
  box.classList.add('show');
  box.scrollIntoView({behavior:'smooth',block:'center'});
}
renderDiffs();

// ---------- 修复队列 ----------
(function(){
  const t=document.getElementById('repairTable');
  const rows=DATA.quality.repair_tasks.slice(0,12);
  if(!rows.length){t.innerHTML='<tr><td class="empty">本轮无待修复记录</td></tr>';return}
  let h='<thead><tr><th>校验</th><th>对象</th><th>行号</th><th>问题</th></tr></thead><tbody>';
  rows.forEach(r=>{h+='<tr><td>'+r.check+'</td><td>'+r.target+'</td><td class="mono">'+r.row_id+'</td><td>'+r.detail+'</td></tr>'});
  t.innerHTML=h+'</tbody>';
})();

// ---------- 质量校验 ----------
(function(){
  const t=document.getElementById('checkTable');
  let h='<thead><tr><th>校验</th><th>检查什么</th><th class="num">命中</th></tr></thead><tbody>';
  DATA.quality.check_stats.forEach(c=>{
    h+='<tr><td><b>'+c.code+'</b> '+c.name+'</td><td style="color:#5b6779">'+c.desc+'</td><td class="num">'+c.hits+'</td></tr>';
  });
  t.innerHTML=h+'</tbody>';
})();

// ---------- 工单 ----------
(function(){
  const t=document.getElementById('ticketTable');
  const rows=DATA.tickets.slice(0,20);
  if(!rows.length){t.innerHTML='<tr><td class="empty">本轮无转人工工单</td></tr>';return}
  let h='<thead><tr><th>工单号</th><th>业务编号</th><th>触发条件</th><th>触发原因</th><th>岗位池/接手人</th><th>确认时间</th><th>SLA</th><th>双人复核</th></tr></thead><tbody>';
  rows.forEach(r=>{
    h+='<tr><td class="mono">'+r.ticket_id+'</td><td class="mono">'+r.biz_no+'</td>'
      +'<td><b>'+r.trigger_code+'</b> '+r.trigger_title+'</td><td style="color:#5b6779">'+r.trigger_text+'</td>'
      +'<td>'+r.pool+' / '+r.assignee+'</td>'
      +'<td>'+(r.confirm_time||'<span style="color:#b42318">待接手</span>')+'</td>'
      +'<td class="mono">'+(r.sla_deadline||'').slice(11,16)+'</td>'
      +'<td>'+(r.double_check?'<span style="color:#b42318;font-weight:600">须复核</span>':'—')+'</td></tr>';
  });
  t.innerHTML=h+'</tbody>';
})();

// ---------- 六节点 ----------
(function(){
  const t=document.getElementById('nodeTable');
  let h='<thead><tr><th>节点</th><th>环节</th><th>本轮方式</th><th class="num">系统耗时</th><th>现状基线（访谈口径，假设）</th></tr></thead><tbody>';
  DATA.kpi.nodes.forEach(n=>{
    h+='<tr><td><b>'+n.code+'</b></td><td>'+n.name+'</td><td>'+n.mode+'</td>'
      +'<td class="num">'+(n.system_text||'—')+'</td><td style="color:#5b6779">'+n.baseline+'</td></tr>';
  });
  t.innerHTML=h+'</tbody>';
})();

// ---------- 审计 ----------
(function(){
  const t=document.getElementById('auditTable');
  const rows=DATA.audit.chain.slice(-12).reverse();
  let h='<thead><tr><th>#</th><th>时间</th><th>类型</th><th>业务编号</th><th>环节</th><th>签核人</th><th>哈希</th></tr></thead><tbody>';
  rows.forEach(r=>{
    h+='<tr><td>'+r.seq+'</td><td class="mono">'+(r.ts||'').replace('T',' ').slice(0,19)+'</td>'
      +'<td>'+r.type+'</td><td class="mono">'+r.biz_no+'</td><td>'+r.stage+'</td>'
      +'<td>'+r.signer+'</td><td class="mono">'+r.hash.slice(0,12)+'…</td></tr>';
  });
  t.innerHTML=h+'</tbody>';
  const c=DATA.audit.check;
  document.getElementById('auditMsg').innerHTML='<div class="'+(c.ok?'hl':'warnbox')+'">'
    +'哈希链校验：'+(c.ok?'<b>通过</b>，共 '+c.checked+' 条记录，链路完整未被篡改':'<b>失败</b>，断点在第 '+c.broken_at+' 条')
    +'。每笔差异均记录业务编号、资料版本、事实引用、建议结果与签核人，可重建归集到复核的全链路。</div>';
})();
</script>
</body>
</html>
"""


def render(state: dict) -> str:
    from . import config as C
    data = {
        "kpi": state["kpi"],
        "diffs": state["diffs"],
        "tickets": state["tickets"],
        "quality": state["quality"],
        "audit": state["audit"],
        "meta": state["meta"],
    }
    data["audit"].pop("full_chain", None)
    colors = {k: [v[0]] for k, v in C.REASON_CODES.items()}
    js = json.dumps(data, ensure_ascii=False, default=str)
    html = TEMPLATE
    html = html.replace("__TITLE__", "对账差异定位复核台")
    html = html.replace("__PROJECT__", state["meta"]["project"])
    html = html.replace("__CHANNEL__", state["meta"]["channel"])
    html = html.replace("__DATE__", state["meta"]["settle_date"])
    html = html.replace("__VER__", str(state["meta"]["snapshot_version"]))
    html = html.replace("__RULE__", state["meta"]["rule_version"])
    html = html.replace("__GENERATED__", state["meta"]["generated_at"])
    html = html.replace("__COLORS__", json.dumps(colors, ensure_ascii=False))
    html = html.replace("__DATA__", js)
    return html
