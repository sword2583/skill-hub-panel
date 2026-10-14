# Skill Hub

> 一处管理，多端分发 —— 统一管理散落在各个 AI Agent 目录中的技能（Skills）。

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-22c55e.svg)](./LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](#)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-0078d4.svg)](#)

如果你同时使用多个 AI 编程助手（Claude Code、Copilot、Gemini CLI、Trae、WorkBuddy……），
你大概遇到过这个麻烦：**同一个技能要在每个工具的目录里各放一份，改一处就得手动同步 N 遍。**

Skill Hub 用一个本地 Web 面板解决它：所有技能只保留**一份真实副本**，
再通过目录链接（Junction / Symlink）分发到各个 Agent 目录。

```
                    ~/.skills-hub/skills/     ← 唯一真实副本
                              │
        ┌──────────┬──────────┼──────────┬──────────┐
        ▼          ▼          ▼          ▼          ▼
     .agents   .copilot    .dsh     .gemini   .workbuddy
```

**改一处，所有 Agent 立即生效。** 不占额外磁盘空间，可逐端摘除，也可随时回退。

---

## 目录

- [特性](#特性)
- [快速开始](#快速开始)
- [界面功能](#界面功能)
- [添加技能](#添加技能)
- [技能索引](#技能索引)
- [工作原理](#工作原理)
- [命令行接口](#命令行接口)
- [配置文件](#配置文件)
- [常见问题](#常见问题)
- [项目结构](#项目结构)
- [开发](#开发)
- [贡献](#贡献)
- [许可](#许可)

---

## 特性

| 能力 | 说明 |
|---|---|
| **统一仓库** | 所有技能只存一份，消除多目录重复 |
| **一键分发** | 目录链接分发到任意数量的 Agent 目录，零拷贝 |
| **本地面板** | 浏览器图形界面，点选即可增删同步，无需记命令 |
| **四种导入** | 本地目录 / zip·tar.gz 压缩包 / Git 仓库 / 手写创建 |
| **自动索引** | 添加技能即自动生成 `SKILLS.md`，随时导出技能清单 |
| **Agent 可配置** | 预设 16 种常见 Agent，自动探测本机目录，界面内增删改 |
| **自动去重** | 识别多个 Agent 间的同名重复技能 |
| **收编旧技能** | 把散落的技能收回仓库并转为链接（预览确认 + 自动备份） |
| **健康体检** | 检测断链、缺失 SKILL.md，一键修复 |
| **逐端控制** | 单个技能可只挂到指定 Agent，也可单独摘除 |
| **零依赖** | 纯 Python 标准库，无需 pip install |
| **跨平台** | Windows 用 Junction（免管理员），macOS/Linux 用符号链接 |

---

## 快速开始

### 环境要求

- **Python 3.9+**（无需任何第三方包）
- 现代浏览器（Chrome / Edge / Firefox）

### 启动

```bash
git clone https://github.com/sword2583/skill-hub-panel.git
cd skill-hub-panel
python src/server.py
```

浏览器会自动打开 `http://127.0.0.1:8899`。也可以手动访问。

```bash
# 指定端口
python src/server.py --port 9000

# 不自动打开浏览器
python src/server.py --no-browser
```

不想敲命令？直接双击启动脚本：

| 系统 | 脚本 |
|---|---|
| Windows | `start.bat` |
| macOS / Linux | `./start.sh`（首次需 `chmod +x start.sh`） |

### 首次使用建议

第一次打开时，程序会**自动探测**本机已安装的 Agent 目录（WorkBuddy、Copilot、
Claude Code、Gemini、Cursor 等 16 种预设），只把真实存在的纳管进来。

各 Agent 目录里可能已有零散的技能。点击右上角 **Agent → 收编孤立技能…**，
程序会**先列出将被移动的每一项**供你确认，执行前自动备份，之后即可统一管理。

---

## 界面功能

打开的页面分为四个区域：

**① 统计栏** —— 一眼掌握全局

| 指标 | 含义 |
|---|---|
| 仓库技能 | 统一仓库内的技能总数 |
| 已挂载 | across 所有 Agent 的挂载点总数（含重复计数） |
| 活跃 Agent | 目录真实存在的 Agent 数量 |
| 多端共享 | 被 2 个以上 Agent 同时挂载的技能数 |
| 孤立技能 | 存在于 Agent 目录但未纳入仓库的技能 |

**② 工具条** —— 搜索、按 Agent 筛选、添加技能

**③ 技能卡片** —— 每个技能显示名称、描述、挂载到哪些 Agent、体积。
卡片上有三个操作：`查看` / `同步` / `删除`

**④ 技能详情** —— 点击「查看」打开：

- 文件清单、体积、被哪些 Agent 挂载
- 逐 Agent 的挂载开关（可只挂到某几个 Agent）
- `SKILL.md` 完整内容预览

顶部按钮：

- **索引** —— 查看并重新生成 `SKILLS.md` 技能清单
- **Agent** —— 管理各 Agent 目录：启停、改路径、增删，并列出可一键添加的预设
- **体检** —— 检查断链与异常，支持一键修复
- **全量同步** —— 把仓库所有技能推到各 Agent

---

## 添加技能

点「添加技能」，四种方式任选：

### 1. 本地目录

```
C:\my-skills\code-review
```

目录内需含 `SKILL.md`。若填的是父目录且其下有多个技能，会全部导入。

### 2. 压缩包

支持 `.zip` / `.tar.gz`。包内含一个或多个技能都可以，程序会自动定位技能根目录
（即使压缩包里多套了一层文件夹）。

### 3. Git 仓库

```
https://github.com/user/skills.git
```

浅克隆后自动扫描仓库内所有技能。仓库含多个技能时全部导入；
也可在「只导入指定技能」里填技能名来挑选单个。

### 4. 手动创建

直接填技能名、描述、正文，程序生成规范的 `SKILL.md`：

```markdown
---
name: my-skill
description: 一句话说明这个技能做什么、何时使用
---

# My Skill

指令内容……
```

> **提示**：添加后程序会询问是否立即同步到各 Agent，选「是」即可一步到位。
> 添加成功后，技能索引（`SKILLS.md`）会自动刷新。

---

## 技能索引

Skill Hub 会把当前仓库的内容导出成一份**机器可读的清单**，放在
`~/.skills-hub/SKILLS.md`（同时产出 `index.json`）：

```markdown
| 技能 | 说明 | 挂载 | 体积 |
| --- | --- | --- | --- |
| `code-review` | 对改动做系统性代码审查。 | copilot, gemini | 12.4 KB |
| `grill-with-docs` | 用连环追问打磨方案，并沉淀 ADR 与词汇表。 | — | 0.5 KB |
```

### 索引是自动的

**添加或删除技能后，程序会自动重写索引**，无需手动维护。也可以在顶栏点
**索引 → 重新生成**，或调用 `POST /api/index/write`。

### 索引为什么独立于 README

索引写进独立的 `SKILLS.md`，而不是 `README.md`。原因有三（详见
[ADR 0001](./docs/adr/0001-index-separate-from-readme.md)）：

1. **结构** —— README 是手写文档，被程序追加条目会冲乱章节结构；
2. **隐私** —— README 会随仓库公开，塞进技能清单等于公开你的技能库；
3. **职责** —— README 是静态文档，索引是动态状态，混在一起会让 README 变脏。

### 每台机器各自的索引

索引描述的是**本机仓库**的内容。你和同事各自在自己电脑上跑 Skill Hub，
就各自得到一份 `SKILLS.md`。因为格式统一，两份索引可以直接互相阅读、
对照或合并 —— 这也是本项目**面向所有使用者**的方式：不共享数据，只共享格式。

### 别忘了 gitignore

`SKILLS.md` 与 `index.json` 属于**本地产物**，含你的技能清单，建议加入
`.gitignore`。本仓库已默认忽略，只保留一份假数据的
[`SKILLS.example.md`](./SKILLS.example.md) 演示格式。

---

## 工作原理

### 核心思路：单一真实副本 + 链接分发

传统做法是每个 Agent 目录各放一份副本，于是产生同步问题。
Skill Hub 反过来：**实体只在仓库里存一份**，各 Agent 目录里放的是指向它的链接。

```
真实文件  ~/.skills-hub/skills/code-review/SKILL.md
   ↑
   ├─ 链接  ~/.agents/skills/code-review      (junction)
   ├─ 链接  ~/.copilot/skills/code-review     (junction)
   └─ 链接  ~/.workbuddy/skills/code-review   (junction)
```

读写任一链接，实际都作用在同一个真实文件上 —— 所以改一处，各处立即同步，
且不产生额外磁盘占用。

### 平台差异

| 平台 | 链接方式 | 说明 |
|---|---|---|
| Windows | **Junction**（目录联接） | 普通用户权限即可创建，无需开发者模式或管理员 |
| macOS / Linux | **Symbolic Link** | 原生支持 |

程序会自动选择可用方式，无需手动配置。

> **为什么 Windows 不用符号链接？**
> Windows 的 `mklink /D`（符号链接）需要管理员权限或开启开发者模式，
> 否则会创建失败。Junction 对目录链接而言功能等价，却不需要特殊权限。

---

## 命令行接口

面板底层是一组 REST 接口，可用脚本调用（默认 `http://127.0.0.1:8899`）。

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/scan` | 全量扫描：技能列表 + 各 Agent 状态 |
| `GET` | `/api/stats` | 轻量统计（比 scan 快，供界面刷新） |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/index` | 索引数据（`?md=1` 返回 Markdown 文本） |
| `GET` | `/api/agents` | 已纳管的 Agent + 可添加的预设 |
| `GET` | `/api/skill?name=<n>` | 单个技能详情与内容 |
| `GET` | `/api/candidates?path=<p>` | 列出路径下的候选技能 |
| `GET` | `/api/adopt/preview` | 预览将被收编的孤立技能（只读） |
| `POST` | `/api/add` | 添加技能（成功后自动刷新索引） |
| `POST` | `/api/remove` | 删除技能（含摘除链接，自动刷新索引） |
| `POST` | `/api/sync` | 同步（带 `name` 同步单个，否则全量） |
| `POST` | `/api/unsync` | 从指定 Agent 摘除链接 |
| `POST` | `/api/repair` | 修复断链 |
| `POST` | `/api/index/write` | 重新生成索引文件 |
| `POST` | `/api/agents/add` | 新增 Agent 目录 |
| `POST` | `/api/agents/update` | 修改 Agent（label / path / enabled） |
| `POST` | `/api/agents/remove` | 移除 Agent（默认不动磁盘链接） |
| `POST` | `/api/adopt` | 收编孤立技能（**需 `confirm:true`**，执行前自动备份） |

> `/api/adapt` 保留为 `/api/adopt` 的兼容别名，同样需要 `confirm`。

### 示例

```bash
# 查看统计
curl http://127.0.0.1:8899/api/stats

# 从目录添加技能
curl -X POST http://127.0.0.1:8899/api/add \
  -H "Content-Type: application/json" \
  -d '{"mode":"path","path":"C:/my-skills/code-review"}'

# 从 Git 仓库添加
curl -X POST http://127.0.0.1:8899/api/add \
  -H "Content-Type: application/json" \
  -d '{"mode":"git","url":"https://github.com/user/skills.git","name":"code-review"}'

# 同步单个技能到全部 Agent
curl -X POST http://127.0.0.1:8899/api/sync \
  -H "Content-Type: application/json" \
  -d '{"name":"code-review"}'

# 只挂到两个 Agent
curl -X POST http://127.0.0.1:8899/api/sync \
  -H "Content-Type: application/json" \
  -d '{"name":"code-review","agents":["copilot","gemini"]}'

# 从某个 Agent 摘除
curl -X POST http://127.0.0.1:8899/api/unsync \
  -H "Content-Type: application/json" \
  -d '{"name":"code-review","agents":["copilot"]}'

# 导出索引（Markdown）
curl "http://127.0.0.1:8899/api/index?md=1"

# 添加一个 Agent 目录
curl -X POST http://127.0.0.1:8899/api/agents/add \
  -H "Content-Type: application/json" \
  -d '{"id":"cursor","label":"Cursor","path":"~/.cursor/skills"}'

# 收编前先预览
curl http://127.0.0.1:8899/api/adopt/preview

# 确认收编（破坏性，会自动备份）
curl -X POST http://127.0.0.1:8899/api/adopt \
  -H "Content-Type: application/json" \
  -d '{"confirm":true}'
```

---

## 配置文件

首次启动会**自动探测**本机存在的 Agent 目录，生成项目根目录的 `config.json`：

```json
{
  "hub_dir": "C:\\Users\\you\\.skills-hub",
  "port": 8899,
  "agents": [
    { "id": "workbuddy", "label": "WorkBuddy",      "path": "C:\\Users\\you\\.workbuddy\\skills",  "enabled": true },
    { "id": "copilot",   "label": "GitHub Copilot", "path": "C:\\Users\\you\\.copilot\\skills",   "enabled": true },
    { "id": "gemini",    "label": "Gemini",         "path": "C:\\Users\\you\\.gemini\\skills",    "enabled": true }
  ]
}
```

| 字段 | 说明 |
|---|---|
| `hub_dir` | 统一仓库位置（技能实体存放处） |
| `port` | 服务端口，被占用时会自动递增寻找可用端口 |
| `agents[].id` | 内部标识，接口调用时使用 |
| `agents[].label` | 界面显示名 |
| `agents[].path` | 该 Agent 的 skills 目录 |
| `agents[].enabled` | 设为 `false` 则跳过该目录 |

> 除手动编辑外，这些配置都能在界面 **Agent** 面板里直接改。
> 内置 16 种预设（WorkBuddy / Copilot / Claude Code / Codex / Cursor / Gemini /
> Windsurf / Cline / Aider / Trae / Qwen Code / iFlow / OpenCode / Continue …），
> 未纳管的预设会列在面板下方，点「添加」即可。

> 想接入未收录的工具？把它的 `skills` 目录加进 `agents` 数组即可。

---

## 常见问题

**Q：会重复占用磁盘吗？**
不会。技能实体只有一份，各 Agent 目录里是指向它的链接，不产生数据副本。

**Q：删除技能时，各 Agent 里的会一起没吗？**
会。删除会先摘除所有链接，再删除实体。程序会二次确认。

**Q：只想从某个 Agent 移除，但保留技能，怎么办？**
在技能详情页点该 Agent 对应的「摘除」，或在卡片上使用 `/api/unsync`。
实体保留在仓库，随时可再挂回去。

**Q：Windows 上提示创建链接失败？**
Skill Hub 默认用 Junction，普通权限即可。若仍失败，检查目录是否被占用，
或该路径所在磁盘是否支持（网络驱动器通常不支持）。

**Q：能同步到局域网其他电脑吗？**
不直接同步内容 —— Skill Hub 只管理本机目录，不做网络传输。但每台机器
都会生成格式相同的 `SKILLS.md` 索引，可以互相阅读对照；想在机器间共享技能，
把 `~/.skills-hub/skills` 放进 Git 仓库自行管理即可。

**Q：技能索引在哪？为什么不在 README 里？**
索引在 `~/.skills-hub/SKILLS.md`（及 `index.json`），由程序自动生成，添加
技能后自动刷新。不放 README 是因为 README 会公开、且会随技能增删而变脏 ——
详见 [ADR 0001](./docs/adr/0001-index-separate-from-readme.md)。

**Q：收编孤立技能安全吗？会删我的文件吗？**
会移动文件，但有防护：执行前**先列出将被移动的每一项**供你确认，
并在 `~/.skills-hub/.backup/<时间戳>/` 留有备份。详见
[ADR 0002](./docs/adr/0002-adopt-destructive-guardrails.md)。

**Q：怎么把某个技能分享给别人？**
取决于你的渠道，本工具不内置分享。常见做法：把技能目录打包发给对方，
或放进 Git 仓库让对方用「Git 仓库」方式导入。

**Q：技能识别不了？**
技能目录内必须有 `SKILL.md`。这是通用约定；缺了它程序无法识别为技能。

**Q：扫描很慢？**
正常应在 1 秒内。若明显变慢，通常是某个 Agent 目录位于网络盘或含大量文件，
可在 `config.json` 中将该 Agent 的 `enabled` 设为 `false`。

---

## 项目结构

```
skill-hub-panel/
├── src/
│   ├── server.py            # HTTP 服务与路由（零依赖）
│   ├── skillhub.py          # 核心引擎：扫描 / 增删 / 同步 / 链接 / 索引
│   └── static/
│       ├── index.html       # 单页界面（原生 JS，无框架）
│       └── favicon.svg
├── docs/
│   └── adr/                 # 架构决策记录
├── CONTEXT.md               # 领域词汇表
├── SKILLS.example.md        # 索引格式示例（真实索引被 gitignore）
├── start.bat / start.sh     # 双击启动脚本
├── config.json              # 运行时生成（含本机路径，已 gitignore）
├── LICENSE
└── README.md
```

### 引擎 API

如需在自己的脚本里调用核心逻辑：

```python
from skillhub import SkillHub

hub = SkillHub()

hub.scan()                                  # 全量扫描
hub.stats()                                 # 轻量统计
hub.add_from_path("C:/path/to/skill")       # 从目录添加
hub.add_from_git("https://github.com/u/s")  # 从 Git 添加
hub.add_from_archive("skill.zip")           # 从压缩包添加
hub.add_from_text("name", "desc", "body")   # 手动创建
hub.sync_skill("name")                      # 同步单个
hub.sync_all()                              # 全量同步
hub.unsync_skill("name", ["copilot"])       # 从指定 Agent 摘除
hub.remove_skill("name")                    # 删除
hub.health()                                # 健康检查
hub.repair()                                # 修复断链

# 索引
hub.build_index()                           # 索引数据（dict）
hub.render_index_md()                       # 索引文本（Markdown）
hub.write_index()                           # 写入 SKILLS.md + index.json

# Agent 配置
hub.add_agent("cursor", "Cursor", "~/.cursor/skills")
hub.update_agent("cursor", enabled=False)
hub.remove_agent("cursor")
hub.available_presets()                     # 尚未纳管的预设

# 收编（破坏性，需 confirm；执行前自动备份）
hub.adopt_preview()                         # 只读预览
hub.adopt(confirm=True)                     # 确认执行
```

---

## 开发

项目刻意保持简单：**零第三方依赖、无构建步骤、无前端框架**。

```bash
# 启动
python src/server.py

# 改前端：直接编辑 src/static/index.html，刷新浏览器即可
# 改后端：重启服务
```

代码组织：

- `skillhub.py` —— 纯逻辑，不涉及 HTTP，可单独 import 使用
- `server.py` —— 只做 HTTP 路由与静态文件，业务转发给引擎
- `index.html` —— 单文件界面，样式与脚本内联

领域词汇（Hub / Agent / 挂载 / 孤儿 / 索引……）见 [`CONTEXT.md`](./CONTEXT.md)；
重要决策记录在 [`docs/adr/`](./docs/adr/)。

### Roadmap

- [ ] 索引支持自定义导出路径与模板
- [ ] 技能版本与更新检测
- [ ] 批量选择与批量挂载
- [ ] 收纳更多 Agent 预设（欢迎 PR）

---

## 贡献

欢迎提 Issue 和 PR。

- **新增 Agent 适配**最能帮到别人 —— 只需在 `src/skillhub.py` 的 `AGENT_PRESETS`
  里加一条 `(id, 显示名, 相对 HOME 的路径片段)`。
- 提交前请确认：`python -m py_compile src/*.py` 通过、界面里核心流程可用。
- 涉及**破坏性行为**的改动，请附上 ADR（参照 `docs/adr/` 格式）。

---

## 许可

[MIT](./LICENSE)

---

<sub>若这个项目对你有帮助，欢迎点个 ⭐️</sub>
