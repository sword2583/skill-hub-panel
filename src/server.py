#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skill Hub Panel — 本地 Web 服务

零依赖 HTTP 服务, 提供 GUI 所需的 REST API 与静态页面。
启动后浏览器访问 http://127.0.0.1:<port>
"""
from __future__ import annotations

import os
import sys
import json
import socket
import webbrowser
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skillhub import SkillHub  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
HUB: SkillHub | None = None


class Handler(BaseHTTPRequestHandler):
    server_version = "SkillHubPanel/1.0"
    protocol_version = "HTTP/1.1"

    # 防止个别连接卡死拖垮整体
    timeout = 30

    def handle_one_request(self):
        """包装单次请求处理, 避免单个坏连接抛出异常"""
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True
        except Exception:
            self.close_connection = True

    # ---------- 工具 ----------
    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _text(self, s: str, ctype="text/markdown; charset=utf-8", status=200):
        body = s.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _file(self, path: Path, ctype="text/html; charset=utf-8"):
        if not path.exists():
            self._json({"error": "not found"}, 404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _read_raw_body(self) -> bytes:
        """可靠且不阻塞地读取请求体。

        不用 Content-Length 作为唯一依据: 该值偏大时会永久阻塞,
        偏小时会截断 JSON 导致静默失败。
        策略: 优先用 Content-Length 作为上限, 但在短超时内读满即返回;
        读不满也返回已读部分, 交由 _body() 容错解析。
        """
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            return self._read_chunked()

        raw_len = self.headers.get("Content-Length")
        try:
            n = int(raw_len) if raw_len else 0
        except ValueError:
            n = 0
        if n <= 0:
            return b""

        # 用短超时逐个读取, 拿满或超时即停, 绝不无限等待
        try:
            self.connection.settimeout(0.5)
        except Exception:
            pass
        buf = bytearray()
        try:
            while len(buf) < n:
                try:
                    chunk = self.rfile.read1(min(n - len(buf), 65536))
                except Exception:
                    break
                if not chunk:
                    break
                buf.extend(chunk)
        finally:
            try:
                self.connection.settimeout(None)
            except Exception:
                pass
        return bytes(buf)

    def _read_chunked(self) -> bytes:
        chunks = []
        try:
            while True:
                line = self.rfile.readline().strip()
                if not line:
                    break
                size = int(line.split(b";")[0], 16)
                if size == 0:
                    self.rfile.readline()
                    break
                chunks.append(self.rfile.read(size))
                self.rfile.readline()
        except Exception:
            pass
        return b"".join(chunks)

    def _body(self) -> dict:
        raw = self._read_raw_body()
        if not raw:
            return {}
        for enc in ("utf-8", "gbk"):
            try:
                return json.loads(raw.decode(enc))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        # 最后尝试: 容忍尾部多余字节
        try:
            s = raw.decode("utf-8", errors="ignore")
            start = s.find("{")
            end = s.rfind("}")
            if start >= 0 and end > start:
                return json.loads(s[start:end + 1])
        except Exception:
            pass
        return {}

    def log_message(self, fmt, *args):
        """静默常规日志, 仅记录错误"""
        if args and str(args[1]).startswith(("4", "5")):
            sys.stderr.write("  [%s] %s\n" % (self.log_date_time_string(), fmt % args))

    # ---------- 路由 ----------
    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        q = parse_qs(u.query)

        if p in ("/", "/index.html"):
            return self._file(STATIC / "index.html")
        if p == "/favicon.ico":
            return self._file(STATIC / "favicon.svg", "image/svg+xml")
        if p.startswith("/static/"):
            rel = p[len("/static/"):]
            ctype = "text/plain; charset=utf-8"
            if rel.endswith(".css"):
                ctype = "text/css; charset=utf-8"
            elif rel.endswith(".js"):
                ctype = "application/javascript; charset=utf-8"
            elif rel.endswith(".svg"):
                ctype = "image/svg+xml"
            return self._file(STATIC / rel, ctype)

        # ---- API ----
        if p == "/api/scan":
            return self._json(HUB.scan())
        if p == "/api/stats":
            return self._json(HUB.stats())
        if p == "/api/health":
            return self._json(HUB.health())
        if p == "/api/config":
            return self._json(HUB.config)
        if p == "/api/skill":
            name = (q.get("name") or [""])[0]
            if not name:
                return self._json({"ok": False, "error": "缺少 name"}, 400)
            d = HUB.skills_dir / name
            if not d.exists():
                return self._json({"ok": False, "error": "技能不存在"}, 404)
            md = d / "SKILL.md"
            files = []
            for f in sorted(d.rglob("*")):
                if f.is_file():
                    files.append(str(f.relative_to(d)).replace("\\", "/"))
            return self._json({
                "ok": True, "name": name,
                "meta": HUB.read_meta(d),
                "content": md.read_text(encoding="utf-8", errors="ignore") if md.exists() else "",
                "files": files[:200],
                "size_kb": round(HUB.dir_size(d) / 1024, 1),
            })
        if p == "/api/candidates":
            path = (q.get("path") or [""])[0]
            if not path:
                return self._json({"ok": False, "error": "缺少 path"}, 400)
            cands = HUB.find_candidates(Path(path).expanduser())
            return self._json({
                "ok": True,
                "candidates": [
                    {"name": c.name, "path": str(c),
                     "meta": HUB.read_meta(c)} for c in cands
                ],
            })
        # ---- 索引 ----
        if p == "/api/index":
            # 返回索引数据; ?md=1 时返回渲染后的 Markdown 文本
            if (q.get("md") or ["0"])[0] == "1":
                return self._text(HUB.render_index_md())
            return self._json({"ok": True, "index": HUB.build_index()})
        if p == "/api/agents":
            return self._json({
                "ok": True,
                "agents": HUB.config["agents"],
                "presets": HUB.available_presets(),
            })
        # ---- 采纳预览 (只读) ----
        if p == "/api/adopt/preview":
            return self._json(HUB.adopt_preview())

        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        p = u.path
        body = self._body()

        if p == "/api/add":
            mode = body.get("mode", "path")
            name = body.get("name") or None
            ow = bool(body.get("overwrite"))
            # 请求体缺失时明确报错, 避免静默按 path 模式处理产生误导信息
            if not body:
                return self._json(
                    {"ok": False, "error": "请求体为空或格式错误(JSON 解析失败)"}, 400)
            if mode == "path":
                res = HUB.add_from_path(body.get("path", ""), name, ow)
            elif mode == "archive":
                res = HUB.add_from_archive(body.get("path", ""), name, ow)
            elif mode == "git":
                res = HUB.add_from_git(body.get("url", ""), name, ow)
            elif mode == "text":
                res = HUB.add_from_text(
                    body.get("name", ""), body.get("description", ""),
                    body.get("body", ""), ow)
            else:
                return self._json({"ok": False, "error": f"未知模式: {mode}"}, 400)

            # 添加成功后自动刷新索引 (SKILLS.md) —— 这是"算法写入索引"的落点
            if res.get("ok"):
                try:
                    res["index"] = HUB.write_index()
                except Exception as e:
                    res["index_warning"] = str(e)
            return self._json(res)

        if p == "/api/remove":
            res = HUB.remove_skill(body.get("name", ""), body.get("purge_links", True))
            if res.get("ok"):
                try:
                    res["index"] = HUB.write_index()
                except Exception as e:
                    res["index_warning"] = str(e)
            return self._json(res)

        if p == "/api/sync":
            name = body.get("name")
            agents = body.get("agents")
            if name:
                return self._json(HUB.sync_skill(name, agents))
            return self._json(HUB.sync_all(agents))

        if p == "/api/unsync":
            return self._json(HUB.unsync_skill(
                body.get("name", ""), body.get("agents")))

        if p == "/api/repair":
            return self._json(HUB.repair())

        # ---- 索引 ----
        if p == "/api/index/write":
            return self._json(HUB.write_index())

        # ---- Agent 配置 CRUD ----
        if p == "/api/agents/add":
            return self._json(HUB.add_agent(
                body.get("id", ""), body.get("label", ""),
                body.get("path", ""), body.get("enabled", True)))
        if p == "/api/agents/update":
            return self._json(HUB.update_agent(
                body.get("id", ""),
                label=body.get("label"), path=body.get("path"),
                enabled=body.get("enabled")))
        if p == "/api/agents/remove":
            return self._json(HUB.remove_agent(
                body.get("id", ""), body.get("purge_links", False)))

        # ---- 采纳 (破坏性, 需 confirm) ----
        if p == "/api/adopt":
            return self._json(HUB.adopt(confirm=bool(body.get("confirm"))))

        if p == "/api/adapt":
            # 兼容旧前端: 同样需要显式确认
            return self._json(HUB.adapt(confirm=bool(body.get("confirm"))))

        if p == "/api/config":
            # 更新启用的 agents
            if "agents" in body:
                HUB.config["agents"] = body["agents"]
                HUB.save_config()
            return self._json({"ok": True, "config": HUB.config})

        return self._json({"error": "not found"}, 404)


class Server(ThreadingHTTPServer):
    """多线程服务: 浏览器会并发发起多个请求, 单线程易被单个连接阻塞"""
    daemon_threads = True
    allow_reuse_address = True


def find_port(start: int, tries: int = 20) -> int:
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError("找不到可用端口")


def serve(port: int | None = None, open_browser: bool = True):
    global HUB
    HUB = SkillHub()
    HUB.ensure_hub()

    desired = port or HUB.config.get("port", 8899)
    actual = find_port(desired)
    httpd = Server(("127.0.0.1", actual), Handler)
    url = f"http://127.0.0.1:{actual}"

    print("=" * 58)
    print("  Skill Hub Panel")
    print("=" * 58)
    print(f"  仓库: {HUB.skills_dir}")
    print(f"  地址: {url}")
    print(f"  端口: {actual}" + ("  (原端口被占用, 已自动切换)" if actual != desired else ""))
    print()
    print("  按 Ctrl+C 停止")
    print("=" * 58)

    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
        httpd.shutdown()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Skill Hub Panel")
    ap.add_argument("--port", type=int, help="指定端口")
    ap.add_argument("--no-browser", action="store_true", help="不自动开浏览器")
    a = ap.parse_args()
    serve(a.port, not a.no_browser)
