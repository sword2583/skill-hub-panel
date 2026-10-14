#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skill Hub Panel — 核心引擎

职责: 扫描 / 添加 / 删除 / 同步 技能, 跨多个 Agent 目录统一管理。
仅使用 Python 标准库, 零第三方依赖。

设计要点:
  * 单一真实副本 (Single Source of Truth): 所有技能实体存放于 HUB/skills/
  * 通过目录联接 (Junction) 或符号链接分发到各 Agent 目录
  * Windows 普通用户权限下 symlink 不可用, 自动降级为 Junction
"""
from __future__ import annotations

import os
import re
import sys
import json
import time
import stat as stat_mod
import shutil
import zipfile
import tarfile
import platform
import subprocess
import tempfile
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"
HOME = Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or "~").expanduser()


def _now_iso() -> str:
    """本地时间的 ISO 字符串 (秒精度)"""
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _now_stamp() -> str:
    """用于备份目录名的时间戳 (文件系统安全)"""
    return time.strftime("%Y%m%d-%H%M%S")


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------
# Agent 预设库: 覆盖常见的技能消费端。首次运行时会**探测**哪些目录真实存在,
# 只有存在的才会写入初始配置, 避免给别人的机器塞一堆空目录。
# key 为稳定 id, value 为 (显示名, 相对 HOME 的路径片段)。
AGENT_PRESETS = [
    ("workbuddy",   "WorkBuddy",       (".workbuddy", "skills")),
    ("agents",      "Agents",          (".agents", "skills")),
    ("copilot",     "GitHub Copilot",  (".copilot", "skills")),
    ("claude",      "Claude Code",     (".claude", "skills")),
    ("codex",       "Codex",           (".codex", "skills")),
    ("cursor",      "Cursor",          (".cursor", "skills")),
    ("gemini",      "Gemini",          (".gemini", "skills")),
    ("windsurf",    "Windsurf",        (".windsurf", "skills")),
    ("cline",       "Cline",           (".cline", "skills")),
    ("aider",       "Aider",           (".aider", "skills")),
    ("dsh",         "DSH",             (".dsh", "skills")),
    ("trae",        "Trae CN",         (".trae-cn", "builtin", "global", "skills")),
    ("qwen",        "Qwen Code",       (".qwen", "skills")),
    ("iflow",       "iFlow",           (".iflow", "skills")),
    ("opencode",    "OpenCode",        (".opencode", "skills")),
    ("continue",    "Continue",        (".continue", "skills")),
]


def detect_agents() -> list:
    """探测本机实际存在的 agent 目录, 生成初始 agents 配置。

    若一个都不存在 (极干净的环境), 回退为全部预设, 交由使用者在界面里
    自行启用/禁用 —— 总比给出一个空的配置强。
    """
    found = []
    for aid, label, parts in AGENT_PRESETS:
        p = HOME.joinpath(*parts)
        if p.exists():
            found.append({"id": aid, "label": label, "path": str(p), "enabled": True})
    if found:
        return found
    return [{"id": aid, "label": label, "path": str(HOME.joinpath(*parts)), "enabled": False}
            for aid, label, parts in AGENT_PRESETS]


DEFAULT_CONFIG = {
    "hub_dir": str(HOME / ".skills-hub"),
    "port": 8899,
    "agents": detect_agents(),
}


class SkillHub:
    """技能仓库管理器"""

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or (Path(__file__).resolve().parent.parent / "config.json")
        self.config = self._load_config()
        self.hub = Path(self.config["hub_dir"])
        self.skills_dir = self.hub / "skills"

    # ---------------- 配置 ----------------
    def _load_config(self) -> dict:
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        if self.config_path.exists():
            try:
                user = json.loads(self.config_path.read_text(encoding="utf-8"))
                cfg.update({k: v for k, v in user.items() if k != "agents"})
                if user.get("agents"):
                    cfg["agents"] = user["agents"]
            except Exception:
                pass
        return cfg

    def save_config(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def ensure_hub(self):
        for sub in ("skills", "registry", "archived", "tools"):
            (self.hub / sub).mkdir(parents=True, exist_ok=True)

    # ---------------- Agent 配置管理 ----------------
    def find_agent(self, agent_id: str) -> dict | None:
        for a in self.config["agents"]:
            if a["id"] == agent_id:
                return a
        return None

    def add_agent(self, agent_id: str, label: str, path: str,
                  enabled: bool = True) -> dict:
        """新增一个 agent 目录"""
        agent_id = (agent_id or "").strip()
        label = (label or "").strip() or agent_id
        path = (path or "").strip()
        if not agent_id:
            return {"ok": False, "error": "agent id 不能为空"}
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$", agent_id):
            return {"ok": False, "error": "agent id 只能含字母/数字/._-"}
        if not path:
            return {"ok": False, "error": "目录路径不能为空"}
        if self.find_agent(agent_id):
            return {"ok": False, "error": f"agent 已存在: {agent_id}", "conflict": True}

        self.config["agents"].append({
            "id": agent_id, "label": label,
            "path": str(Path(path).expanduser()), "enabled": bool(enabled),
        })
        self.save_config()
        return {"ok": True, "agent": agent_id}

    def update_agent(self, agent_id: str, **fields) -> dict:
        """修改 agent 的 label / path / enabled"""
        a = self.find_agent(agent_id)
        if not a:
            return {"ok": False, "error": f"agent 不存在: {agent_id}"}
        if "label" in fields and fields["label"]:
            a["label"] = str(fields["label"]).strip()
        if "path" in fields and fields["path"]:
            a["path"] = str(Path(fields["path"]).expanduser())
        if "enabled" in fields and fields["enabled"] is not None:
            a["enabled"] = bool(fields["enabled"])
        self.save_config()
        return {"ok": True, "agent": a}

    def remove_agent(self, agent_id: str, purge_links: bool = False) -> dict:
        """从配置移除 agent。默认不动磁盘上的链接(安全)。"""
        a = self.find_agent(agent_id)
        if not a:
            return {"ok": False, "error": f"agent 不存在: {agent_id}"}

        removed_links = []
        if purge_links:
            d = Path(a["path"])
            if d.exists():
                for entry in list(d.iterdir()):
                    if entry.is_dir() and self.is_link(entry):
                        try:
                            if entry.is_symlink():
                                entry.unlink()
                            else:
                                shutil.rmtree(entry, ignore_errors=True)
                            removed_links.append(entry.name)
                        except Exception:
                            pass

        self.config["agents"] = [x for x in self.config["agents"]
                                 if x["id"] != agent_id]
        self.save_config()
        return {"ok": True, "agent": agent_id, "removed_links": removed_links}

    def available_presets(self) -> list:
        """列出预设库里尚未纳管的 agent, 供界面一键添加"""
        known = {a["id"] for a in self.config["agents"]}
        out = []
        for aid, label, parts in AGENT_PRESETS:
            if aid in known:
                continue
            p = HOME.joinpath(*parts)
            out.append({"id": aid, "label": label, "path": str(p),
                        "exists": p.exists()})
        return out

    # ---------------- 索引生成 ----------------
    def build_index(self, with_size: bool = True) -> dict:
        """生成索引数据 (纯数据, 不落盘)"""
        data = self.scan(with_size=with_size)
        generated = _now_iso()
        return {
            "generated_at": generated,
            "hub_dir": data["hub_dir"],
            "total": data["total_skills"],
            "skills": [
                {
                    "name": s["name"],
                    "description": s.get("description", ""),
                    "has_skill_md": s.get("has_skill_md", False),
                    "size_kb": s.get("size_kb", 0),
                    "owners": s.get("owners", []),
                    "mounted": len(s.get("owners", [])) > 0,
                }
                for s in data["skills"]
            ],
        }

    def render_index_md(self, with_size: bool = True) -> str:
        """把索引渲染为 Markdown 文本 (SKILLS.md 的内容)"""
        idx = self.build_index(with_size=with_size)
        lines = [
            "# 技能索引",
            "",
            "> 本文件由 Skill Hub 自动生成, 请勿手工编辑。",
            f"> 生成时间: {idx['generated_at']}",
            f"> 技能总数: {idx['total']}",
            "",
            "| 技能 | 说明 | 挂载 | 体积 |",
            "| --- | --- | --- | --- |",
        ]
        for s in idx["skills"]:
            desc = (s["description"] or "").replace("|", "\\|").replace("\n", " ")
            if len(desc) > 80:
                desc = desc[:77] + "..."
            owners = ", ".join(s["owners"]) if s["owners"] else "—"
            size = f"{s['size_kb']} KB" if with_size else "—"
            lines.append(f"| `{s['name']}` | {desc} | {owners} | {size} |")
        lines.append("")
        return "\n".join(lines)

    def write_index(self, with_size: bool = True) -> dict:
        """把索引写入 hub 根目录的 SKILLS.md, 并同步 JSON 版本"""
        self.ensure_hub()
        md_path = self.hub / "SKILLS.md"
        json_path = self.hub / "index.json"

        md_path.write_text(self.render_index_md(with_size=with_size),
                           encoding="utf-8")
        json_path.write_text(
            json.dumps(self.build_index(with_size=with_size),
                       ensure_ascii=False, indent=2),
            encoding="utf-8")
        return {"ok": True, "path": str(md_path),
                "json": str(json_path), "total": self.build_index(False)["total"]}

    # ---------------- 采纳(破坏性, 带防护) ----------------
    def adopt_preview(self) -> dict:
        """只读: 列出将被采纳的孤儿技能, 不移动任何文件"""
        items = []
        for a in self.config["agents"]:
            d = Path(a["path"])
            if not d.exists() or self.is_link(d):
                continue
            try:
                entries = list(d.iterdir())
            except Exception:
                continue
            for entry in entries:
                if not entry.is_dir() or self.is_link(entry):
                    continue
                ok, _err = self._validate_skill_dir(entry)
                if not ok:
                    continue
                already = (self.skills_dir / entry.name).exists()
                items.append({
                    "agent": a["id"],
                    "agent_label": a["label"],
                    "name": entry.name,
                    "source": str(entry),
                    "action": "link_only" if already else "copy_then_link",
                    "size_kb": round(self.dir_size(entry) / 1024, 1),
                })
        return {"ok": True, "items": items, "count": len(items)}

    def adopt(self, confirm: bool = False) -> dict:
        """采纳孤儿: 收进仓库并把原目录转为链接。

        破坏性操作, 需显式 confirm; 执行前自动备份原目录。
        """
        if not confirm:
            return {"ok": False,
                    "error": "采纳是破坏性操作, 需显式确认 (confirm=true)",
                    "hint": "先调用 preview 查看将被移动的内容"}

        preview = self.adopt_preview()
        items = preview["items"]
        if not items:
            return {"ok": True, "adopted": [], "relinked": [], "backup": None,
                    "message": "没有需要采纳的技能"}

        self.ensure_hub()
        backup_dir = self.hub / ".backup" / _now_stamp()
        backup_dir.mkdir(parents=True, exist_ok=True)

        adopted, relinked, errors = [], [], []
        for it in items:
            entry = Path(it["source"])
            dst = self.skills_dir / it["name"]
            try:
                # 1) 备份原目录 (仅 copy_then_link 需要 —— link_only 未改动内容)
                if it["action"] == "copy_then_link":
                    shutil.copytree(entry, backup_dir / it["name"],
                                    symlinks=False, dirs_exist_ok=True)
                    # 2) 收进仓库
                    shutil.copytree(entry, dst, symlinks=False, dirs_exist_ok=True)
                    adopted.append(f"{it['agent']}/{it['name']}")
                # 3) 原目录转链接
                shutil.rmtree(entry, ignore_errors=True)
                ok2, _how = self.make_link(entry, dst)
                if ok2:
                    relinked.append(f"{it['agent']}/{it['name']}")
                else:
                    errors.append(f"{it['agent']}/{it['name']}: 建立链接失败")
            except Exception as e:
                errors.append(f"{it['agent']}/{it['name']}: {e}")

        return {"ok": not errors, "adopted": adopted, "relinked": relinked,
                "backup": str(backup_dir), "errors": errors}

    # ---------------- 链接工具 ----------------
    _link_cache: dict = {}

    @staticmethod
    def link_type(path: Path) -> str:
        """快速判定路径的链接类型。

        返回 'junction' | 'symlink' | 'dir' | 'none'。
        用 os.readlink / st_reparse 原生判断, 不调用 subprocess
        (逐条调用 cmd dir 会让扫描慢上百倍)。
        """
        key = str(path).lower()
        cached = SkillHub._link_cache.get(key)
        if cached is not None:
            return cached

        result = "none"
        try:
            st = os.lstat(path)
            if os.path.islink(path):
                result = "symlink"
            elif IS_WINDOWS:
                # Windows 上 junction 的 st_reparse_tag 为 0xA0000003
                tag = getattr(st, "st_reparse_tag", 0)
                if tag == 0xA0000003:
                    result = "junction"
                elif tag == 0xA000000C:
                    result = "symlink"
                elif stat_mod.S_ISDIR(st.st_mode):
                    result = "dir"
            elif stat_mod.S_ISDIR(st.st_mode):
                result = "dir"
        except OSError:
            result = "none"

        SkillHub._link_cache[key] = result
        return result

    @staticmethod
    def is_link(path: Path) -> bool:
        return SkillHub.link_type(path) in ("junction", "symlink")

    @classmethod
    def clear_link_cache(cls):
        cls._link_cache.clear()

    @staticmethod
    def is_broken_link(path: Path) -> bool:
        """链接存在但目标不可访问"""
        if not SkillHub.is_link(path):
            return False
        if not path.exists():
            return True
        try:
            return not any(path.iterdir())
        except Exception:
            return True

    @staticmethod
    def make_link(link: Path, target: Path) -> tuple:
        """创建链接, 返回 (成功, 方式)。优先 Junction(免权限)"""
        if link.exists() or link.is_symlink():
            return True, "exists"
        if IS_WINDOWS:
            try:
                r = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                    capture_output=True, text=True, encoding="gbk",
                    errors="ignore", timeout=30,
                )
                if r.returncode == 0 and link.exists():
                    return True, "junction"
            except Exception:
                pass
        try:
            link.symlink_to(target, target_is_directory=True)
            return True, "symlink"
        except Exception:
            return False, "failed"

    # ---------------- 技能识别 ----------------
    @staticmethod
    def read_meta(skill_dir: Path) -> dict:
        """读取 SKILL.md frontmatter"""
        meta = {"name": skill_dir.name, "description": "", "has_skill_md": False}
        f = skill_dir / "SKILL.md"
        if not f.exists():
            return meta
        meta["has_skill_md"] = True
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return meta
        m = re.search(r"^---\s*\n(.*?)\n---", txt, re.S)
        if not m:
            return meta
        fm = m.group(1)
        nm = re.search(r"^name:\s*(.+)$", fm, re.M)
        dm = re.search(r"^description:\s*(.+?)(?=^\w+:|\Z)", fm, re.M | re.S)
        if nm:
            meta["name"] = nm.group(1).strip().strip("\"'")
        if dm:
            meta["description"] = " ".join(dm.group(1).split())
        return meta

    @staticmethod
    def dir_size(path: Path) -> int:
        """递归统计目录大小(轻量, 跳过链接避免重复计入)"""
        total = 0
        try:
            for root, dirs, files in os.walk(path, followlinks=False):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
        except Exception:
            pass
        return total

    # ---------------- 状态扫描 ----------------
    def hub_skills(self, with_size: bool = True) -> list:
        """仓库内所有技能"""
        if not self.skills_dir.exists():
            return []
        out = []
        for d in sorted(self.skills_dir.iterdir()):
            if not d.is_dir():
                continue
            meta = self.read_meta(d)
            out.append({
                "name": d.name,
                **meta,
                "size_kb": round(self.dir_size(d) / 1024, 1) if with_size else 0,
                "is_link": self.is_link(d),
            })
        return out

    def agent_skills(self, agent: dict) -> list:
        """某 agent 目录下的技能"""
        p = Path(agent["path"])
        if not p.exists():
            return []
        names = []
        try:
            for e in sorted(p.iterdir()):
                if e.is_dir():
                    names.append(e.name)
        except Exception:
            return []
        return names

    def scan(self, with_size: bool = True) -> dict:
        """全量扫描: 技能 + 各 agent 状态 + 归属关系

        性能要点:
          * 不调用 subprocess 判断链接类型 (原生 os.lstat)
          * 归属关系用集合一次算完, 避免 O(技能×Agent) 的线性查找
          * with_size=False 时跳过体积统计(体感最快)
        """
        hub = self.hub_skills(with_size=with_size)
        hub_names = {s["name"] for s in hub}

        agents = []
        owner_map: dict[str, list[str]] = {}
        for a in self.config["agents"]:
            p = Path(a["path"])
            exists = p.exists()
            is_link = self.is_link(p) if exists else False
            present = self.agent_skills(a) if exists else []
            for n in present:
                owner_map.setdefault(n, []).append(a["id"])
            agents.append({
                **a,
                "exists": exists,
                "is_link": is_link,
                "skill_count": len(present),
                "present": present,
                "orphan": [n for n in present if n not in hub_names],
            })

        # 一次赋值归属, 不做嵌套查找
        for s in hub:
            s["owners"] = owner_map.get(s["name"], [])

        return {
            "hub_dir": str(self.skills_dir),
            "skills": hub,
            "agents": agents,
            "total_skills": len(hub),
        }

    def stats(self) -> dict:
        """轻量统计: 跳过体积计算, 供界面快速刷新"""
        data = self.scan(with_size=False)
        mounted = sum(a["skill_count"] for a in data["agents"])
        shared = sum(1 for s in data["skills"] if len(s["owners"]) > 1)
        orphans = sum(len(a["orphan"]) for a in data["agents"])
        return {
            "total_skills": data["total_skills"],
            "mounted": mounted,
            "shared": shared,
            "orphans": orphans,
            "agents": len([a for a in data["agents"] if a["exists"]]),
        }

    # ---------------- 添加技能 ----------------
    def _validate_skill_dir(self, path: Path) -> tuple:
        """校验是否为合法技能目录"""
        if not path.is_dir():
            return False, "不是目录"
        if not (path / "SKILL.md").exists():
            return False, "缺少 SKILL.md"
        return True, ""

    def _find_skill_root(self, path: Path) -> Path | None:
        """在解压产物中定位真正的技能根目录(可能是嵌套的)"""
        if (path / "SKILL.md").exists():
            return path
        # 向下最多找 3 层
        for depth in range(1, 4):
            matches = list(path.glob("/".join(["*"] * depth) + "/SKILL.md"))
            if len(matches) == 1:
                return matches[0].parent
            if len(matches) > 1:
                return None  # 多个, 让调用方选择
        return None

    def find_candidates(self, path: Path) -> list:
        """列出路径下所有候选技能"""
        if (path / "SKILL.md").exists():
            return [path]
        out = []
        for md in path.rglob("SKILL.md"):
            if "node_modules" in str(md):
                continue
            out.append(md.parent)
        return sorted(set(out))

    def add_from_path(self, src: str, name: str | None = None,
                      overwrite: bool = False) -> dict:
        """从本地目录添加技能"""
        p = Path(src).expanduser()
        if not p.exists():
            return {"ok": False, "error": f"路径不存在: {p}"}

        ok, err = self._validate_skill_dir(p)
        if not ok:
            return {"ok": False, "error": f"无效技能: {err}"}

        target_name = name or p.name
        dst = self.skills_dir / target_name
        if dst.exists() and not overwrite:
            return {"ok": False, "error": f"技能已存在: {target_name}", "conflict": True}

        self.skills_dir.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(p, dst, symlinks=False, dirs_exist_ok=True)
        return {"ok": True, "name": target_name, "added": [target_name]}

    def add_from_archive(self, archive: str, name: str | None = None,
                         overwrite: bool = False) -> dict:
        """从 zip / tar.gz 添加技能(支持压缩包内含多个技能)"""
        p = Path(archive).expanduser()
        if not p.exists():
            return {"ok": False, "error": f"文件不存在: {p}"}

        tmp = Path(tempfile.mkdtemp(prefix="skillhub-"))
        try:
            if zipfile.is_zipfile(p):
                with zipfile.ZipFile(p) as z:
                    z.extractall(tmp)
            elif tarfile.is_tarfile(p):
                with tarfile.open(p) as t:
                    t.extractall(tmp)
            else:
                return {"ok": False, "error": "不支持的压缩格式(仅 zip / tar.gz)"}

            candidates = self.find_candidates(tmp)
            if not candidates:
                return {"ok": False, "error": "压缩包内未找到含 SKILL.md 的技能"}

            if name and len(candidates) == 1:
                return self.add_from_path(str(candidates[0]), name, overwrite)

            added, conflicts = [], []
            for c in candidates:
                r = self.add_from_path(str(c), None, overwrite)
                if r["ok"]:
                    added.extend(r.get("added", []))
                else:
                    conflicts.append(c.name)
            return {
                "ok": True,
                "added": added,
                "conflicts": conflicts,
                "found": len(candidates),
            }
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def add_from_git(self, url: str, name: str | None = None,
                     overwrite: bool = False) -> dict:
        """从 git 仓库添加技能"""
        if not shutil.which("git"):
            return {"ok": False, "error": "未检测到 git"}
        tmp = Path(tempfile.mkdtemp(prefix="skillhub-git-"))
        try:
            r = subprocess.run(
                ["git", "clone", "--depth", "1", url, str(tmp / "repo")],
                capture_output=True, text=True, timeout=180,
            )
            if r.returncode != 0:
                return {"ok": False, "error": f"克隆失败: {r.stderr.strip()[:200]}"}
            candidates = self.find_candidates(tmp / "repo")
            if not candidates:
                return {"ok": False, "error": "仓库内未找到含 SKILL.md 的技能"}

            # 单技能且指定了名字 -> 直接用
            if name:
                pick = None
                for c in candidates:
                    if c.name == name:
                        pick = c
                        break
                if pick is None and len(candidates) == 1:
                    pick = candidates[0]
                    return self.add_from_path(str(pick), name, overwrite)
                if pick is None:
                    return {
                        "ok": False,
                        "error": f"未找到名为 {name} 的技能",
                        "available": [c.name for c in candidates][:50],
                    }
                return self.add_from_path(str(pick), name, overwrite)

            added, conflicts = [], []
            for c in candidates:
                r2 = self.add_from_path(str(c), None, overwrite)
                if r2["ok"]:
                    added.extend(r2.get("added", []))
                else:
                    conflicts.append(c.name)
            return {"ok": True, "added": added, "conflicts": conflicts,
                    "found": len(candidates)}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "克隆超时"}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def add_from_text(self, name: str, description: str, body: str = "",
                      overwrite: bool = False) -> dict:
        """直接写一个 SKILL.md 创建技能"""
        if not name or not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$", name):
            return {"ok": False, "error": "技能名只能含字母/数字/._- , 且不能以符号开头"}
        dst = self.skills_dir / name
        if dst.exists() and not overwrite:
            return {"ok": False, "error": f"技能已存在: {name}", "conflict": True}
        dst.mkdir(parents=True, exist_ok=True)
        content = (
            f"---\nname: {name}\ndescription: {description}\n---\n\n"
            f"{body or '# ' + name}\n"
        )
        (dst / "SKILL.md").write_text(content, encoding="utf-8")
        return {"ok": True, "name": name, "added": [name]}

    # ---------------- 删除 ----------------
    def remove_skill(self, name: str, purge_links: bool = True) -> dict:
        """删除技能: 先摘除各 agent 的链接, 再删仓库实体"""
        target = self.skills_dir / name
        if not target.exists():
            return {"ok": False, "error": f"技能不存在: {name}"}

        removed_links = []
        if purge_links:
            for a in self.config["agents"]:
                lp = Path(a["path"]) / name
                if lp.exists() or lp.is_symlink():
                    try:
                        if lp.is_symlink() or self.is_link(lp):
                            lp.unlink()
                        else:
                            shutil.rmtree(lp, ignore_errors=True)
                        removed_links.append(a["id"])
                    except Exception:
                        pass

        try:
            shutil.rmtree(target)
        except Exception as e:
            return {"ok": False, "error": f"删除失败: {e}"}

        return {"ok": True, "name": name, "removed_links": removed_links}

    # ---------------- 同步 ----------------
    def sync_skill(self, name: str, agents: list | None = None) -> dict:
        """把某个技能挂到指定 agent(默认全部)"""
        src = self.skills_dir / name
        if not src.exists():
            return {"ok": False, "error": f"技能不存在: {name}"}

        results = []
        for a in self.config["agents"]:
            if agents and a["id"] not in agents:
                continue
            if not a.get("enabled", True):
                continue
            d = Path(a["path"])
            if not d.exists():
                results.append({"agent": a["id"], "status": "missing_dir"})
                continue
            link = d / name
            if link.exists() or link.is_symlink():
                if not self.is_broken_link(link):
                    results.append({"agent": a["id"], "status": "already"})
                    continue
                try:
                    if link.is_symlink():
                        link.unlink()
                    else:
                        shutil.rmtree(link, ignore_errors=True)
                except Exception:
                    pass
            ok, how = self.make_link(link, src)
            results.append({
                "agent": a["id"],
                "status": "linked" if ok else "failed",
                "how": how,
            })
        return {"ok": True, "name": name, "results": results}

    def sync_all(self, agents: list | None = None) -> dict:
        """把仓库全部技能挂到各 agent"""
        report = {}
        for s in self.hub_skills():
            report[s["name"]] = self.sync_skill(s["name"], agents)
        return {"ok": True, "report": report}

    def unsync_skill(self, name: str, agents: list | None = None) -> dict:
        """从指定 agent 摘除链接(保留仓库实体)"""
        removed = []
        for a in self.config["agents"]:
            if agents and a["id"] not in agents:
                continue
            link = Path(a["path"]) / name
            if link.exists() or link.is_symlink():
                try:
                    if link.is_symlink() or self.is_link(link):
                        link.unlink()
                    else:
                        shutil.rmtree(link, ignore_errors=True)
                    removed.append(a["id"])
                except Exception:
                    pass
        return {"ok": True, "name": name, "removed": removed}

    def adapt(self, root: str | None = None, confirm: bool = False) -> dict:
        """兼容入口: 采纳孤儿技能。

        已改为委托给带防护的 adopt() —— 不再静默执行。
        保留此方法名以兼容既有调用方 (CLI / 旧前端)。
        """
        return self.adopt(confirm=confirm)

    # ---------------- 健康检查 ----------------
    def health(self) -> dict:
        issues = []
        if not self.skills_dir.exists():
            issues.append({"level": "error", "msg": "仓库目录不存在"})
            return {"ok": False, "issues": issues}

        no_md = [s["name"] for s in self.hub_skills() if not s["has_skill_md"]]
        if no_md:
            issues.append({"level": "warn",
                           "msg": f"{len(no_md)} 个技能缺少 SKILL.md", "items": no_md[:10]})

        for a in self.config["agents"]:
            d = Path(a["path"])
            if not d.exists():
                issues.append({"level": "info", "msg": f"{a['label']} 目录不存在"})
                continue
            broken = []
            for entry in d.iterdir():
                if entry.is_dir() and self.is_link(entry) and self.is_broken_link(entry):
                    broken.append(entry.name)
                elif entry.is_dir() and not self.is_link(entry):
                    pass
            if broken:
                issues.append({"level": "error",
                               "msg": f"{a['label']} 有 {len(broken)} 个断链",
                               "items": broken[:10]})

        return {"ok": len([i for i in issues if i["level"] == "error"]) == 0,
                "issues": issues}

    def repair(self) -> dict:
        """修复断链"""
        fixed = []
        for a in self.config["agents"]:
            d = Path(a["path"])
            if not d.exists():
                continue
            for entry in list(d.iterdir()):
                if entry.is_dir() and self.is_link(entry) and self.is_broken_link(entry):
                    name = entry.name
                    try:
                        entry.unlink()
                    except Exception:
                        shutil.rmtree(entry, ignore_errors=True)
                    src = self.skills_dir / name
                    if src.exists():
                        ok, _ = self.make_link(entry, src)
                        if ok:
                            fixed.append(f"{a['id']}/{name}")
        return {"ok": True, "fixed": fixed}
