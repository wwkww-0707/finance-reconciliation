# -*- coding: utf-8 -*-
"""
本地复核服务（stdlib http.server，无框架依赖）。

端点：
    GET  /              复核台页面（每次请求实时渲染）
    GET  /api/state     当前状态 JSON
    POST /api/rerun     重新生成样本并重跑（演示口径变化）
    POST /api/ack       人工接手：写入签核人、确认时间与审计事件
    GET  /api/audit     审计链 JSONL（便于离线复算）
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import audit, config as C, pipeline, report

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "sample", "data")
OUT_DIR = os.path.join(BASE_DIR, "sample", "out")

_lock = threading.Lock()
STATE = {"state": None}


def _ensure():
    if STATE["state"] is None:
        STATE["state"] = pipeline.run(DATA_DIR, regenerate=False)
    return STATE["state"]


class Handler(BaseHTTPRequestHandler):
    server_version = "ReconConsole/%s" % "0.1.0"

    def log_message(self, fmt, *args):        # 静默访问日志，保持控制台干净
        pass

    # ------------------------------------------------ 工具
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"),
                   "application/json; charset=utf-8")

    # ------------------------------------------------ 路由
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            with _lock:
                st = _ensure()
            html = report.render(st)
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/state":
            with _lock:
                st = _ensure()
            self._json({"meta": st["meta"], "kpi": st["kpi"]["kpi"],
                        "counts": {"diffs": len(st["diffs"]), "tickets": len(st["tickets"])}})
            return
        if path == "/api/audit":
            with _lock:
                st = _ensure()
            lines = "\n".join(json.dumps(r, ensure_ascii=False) for r in st["audit"]["chain"])
            self._send(200, lines.encode("utf-8"), "application/x-ndjson; charset=utf-8")
            return
        if path == "/health":
            self._json({"ok": True})
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)

        if u.path == "/api/rerun":
            with _lock:
                STATE["state"] = pipeline.run(DATA_DIR, regenerate=False)
                st = STATE["state"]
            self._json({"ok": True, "diffs": len(st["diffs"]), "kpi": st["kpi"]["kpi"]})
            return

        if u.path == "/api/ack":
            biz = (qs.get("biz_no") or [""])[0]
            signer = (qs.get("signer") or ["对账会计（唐映秋）"])[0]
            change = (qs.get("change") or [""])[0]
            if not biz:
                self._json({"error": "缺少 biz_no"}, 400)
                return
            with _lock:
                st = _ensure()
                chain = st["audit"]["full_chain"]
                rec = audit.ack(chain, biz, signer, change)
                st["audit"]["chain"] = chain[-200:]
                st["audit"]["check"] = audit.verify(chain)
                hit = None
                for t in st["tickets"]:
                    if t["biz_no"] == biz and t["status"] == "待接手":
                        t["confirm_time"] = rec["ts"]
                        t["status"] = "已接手"
                        hit = t["ticket_id"]
                        break
            self._json({"ok": True, "ticket": hit, "seq": rec["seq"], "hash": rec["hash"][:16]})
            return

        self._json({"error": "not found"}, 404)


def serve(port: int = 8787, open_browser: bool = True) -> None:
    with _lock:
        _ensure()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d/" % port
    print("对账差异定位台已启动：%s" % url)
    print("渠道 %s · 结算日 %s · 只读模式" % (C.CHANNEL, C.SETTLE_DATE))
    print("按 Ctrl+C 停止")
    if open_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
