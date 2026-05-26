# ACTs — Agent Creat Tools构建文档 v1.1 (已确认)

 日期: 2026-05-24
 技术栈: Python 3.10+
 UI: PyQt6

### 文档目录

 - [项目概述](#s1)

 - [技术栈与依赖](#s2)

 - [系统架构总览](#s3)

 - [数据存储与文件结构](#s4)

 - [核心模块设计](#s5)

 - [LLM API 适配层](#s6)

 - [Agent 通信协议](#s7)

 - [AgentTeam 调度引擎](#s8)

 - [Session 生命周期](#s9)

 - [PyQt6 界面设计](#s10)

 - [安全方案](#s11)

 - [构建路线图](#s12)

 - [待确认事项汇总](#s13)

## 1. 项目概述

**ACTs**（Agent Creat Tools）是一款用户自定义搭建 AI Agent 智能体的桌面软件。用户提供自己的 LLM API 密钥，即可在本地构建、调试、编排多个 Agent，并组建成 AgentTeam 完成复杂任务。

 **核心语言** Python 3.10+
 **桌面 UI** PyQt6
 **配置格式** YAML
 **数据存储** 文件系统 + SQLite

### 1.1 核心对象模型

对象定义存储

 **Agent**
 单个 AI 智能体，绑定 LLM API、System Prompt、Skills。是执行任务的最小单元。
 `Acts/Agents/{agent_id}/AGENT.yaml`

 **AgentTeam**
 多个 Agent 组成的团队。含 1 个队长 Agent 负责接收任务、拆解并分派给成员。
 `Acts/Team/{team_id}.yaml`

 **Session**
 一次对话/任务会话。记录调用的 Agent/Team、历史上下文、生成的文件与数据。
 `Acts/Sessions/{session_id}/`

### 1.2 核心理念

 - **用户自托管** — 用户提供自己的 LLM API 密钥，所有数据存储在本地。

 - **文件即配置** — YAML 文件驱动，无需数据库即可完整恢复状态。

 - **可组合** — Agent + Skill 可自由组合；Agent 可加入多个 Team。

 - **AI 友好** — 文档结构化，支持 AI / 代码生成工具直接解析并构建。

## 2. 技术栈与依赖

层级技术选型用途
UI 框架PyQt6桌面 GUI，主窗口 + 多面板 + 对话框
配置解析PyYAML读写 YAML 配置文件
LLM 调用httpx / aiohttp异步 HTTP 请求 LLM API
任务调度asyncio异步并发控制
本地索引SQLite (aiosqlite)Agent / Team / Session 快速检索
加密cryptographyAPI 密钥 AES 加密存储
模板引擎Jinja2System Prompt 模板渲染
测试pytest / pytest-asyncio单元测试与集成测试

### 2.1 推荐目录结构（源码）

```plaintext
acts/ # 项目根目录
├── src/
│ ├── core/ # 核心引擎
│ │ ├── agent.py # Agent 类
│ │ ├── team.py # AgentTeam 类
│ │ ├── session.py # Session 类
│ │ ├── skill.py # Skill 执行器
│ │ └── orchestrator.py # Team 调度引擎
│ ├── llm/ # LLM 适配层
│ │ ├── base.py # 抽象基类
│ │ ├── openai_compat.py # OpenAI 兼容协议适配
│ │ └── factory.py # 适配器工厂
│ ├── storage/ # 存储层
│ │ ├── yaml_io.py # YAML 读写
│ │ ├── file_store.py # 文件系统管理
│ │ └── db.py # SQLite 索引
│ ├── security/ # 安全模块
│ │ └── vault.py # 密钥加密存储
│ ├── ui/ # PyQt6 界面
│ │ ├── main_window.py
│ │ ├── agent_panel.py
│ │ ├── team_panel.py
│ │ ├── session_panel.py
│ │ └── chat_widget.py
│ └── utils/
│ ├── id_gen.py # ID 生成（UUID v4）
│ └── logger.py
├── tests/
├── main.py # 入口
└── requirements.txt
```

## 3. 系统架构总览

架构分层

```plaintext
┌─────────────────────────────────────────────┐
│ PyQt6 UI Layer │ ← 用户交互
├─────────────────────────────────────────────┤
│ Core Engine (Agent / Team / │
│ Session / Orchestrator) │ ← 业务逻辑
├──────────────┬──────────────┬───────────────┤
│ LLM Adapter │ Storage │ Security │ ← 基础设施
│ Layer │ Layer │ Vault │
└──────────────┴──────────────┴───────────────┘
```

关键数据流：

 - **用户操作** → UI 发出信号 → Core Engine 处理 → Storage 持久化 → LLM Adapter 调用外部 API → 结果回流 UI。

 - **Team 任务** → Orchestrator 接收任务 → 队长 Agent 分析分解 → 分发子任务给成员 Agent → 汇总结果。

## 4. 数据存储与文件结构

### 4.1 数据目录（运行时）

```plaintext
Acts/
├── Agents/ # 所有 Agent 配置
│ ├── a1b2c3d4/ # Agent 目录（ID=UUID前8位）
│ │ ├── AGENT.yaml # 核心配置
│ │ └── Skills/
│ │ └── translate.yaml
│ └── ...
│
├── Team/
│ ├── t1e5f6a7.yaml
│ └── ...
│
└── Sessions/
 ├── s9d3f2g1/
 │ ├── SESSION.yaml # 元数据
 │ └── content/
 │ ├── content.txt # 对话历史
 │ ├── output_report.pdf
 │ └── data.json
 └── ...
```

### 4.2 YAML Schema 定义

#### AGENT.yaml

```plaintext
# AGENT.yaml — Agent 核心配置
id: "a1b2c3d4" # UUID 前8位
name: "代码助手" # 显示名称
description: "擅长 Python 和 JavaScript 的编程助手"
system_prompt: |
 你是一个专业的编程助手...
model:
 provider: "openai" # openai / anthropic / custom
 name: "gpt-4o" # 模型名称
 temperature: 0.7
 max_tokens: 4096
llm_api:
 base_url: "https://api.openai.com/v1" # API 端点
 api_key_ref: "vault:openai_main" # 密钥引用（不存明文）
 timeout_seconds: 120
skills:
 - "translate" # 引用的 Skill 名称列表
 - "code_review"
created_at: "2026-05-24T10:00:00Z"
updated_at: "2026-05-24T10:00:00Z"
```

#### Skill YAML (Skills/translate.yaml)

```plaintext
# Skill 定义文件
name: "translate"
description: "多语言翻译能力"
type: "system_prompt_extension" # 类型：prompt扩展 / 工具调用 / 脚本执行
prompt_extension: |
 你具备多语言翻译能力。当用户需要翻译时，请先识别源语言，再输出目标语言译文。
 支持的语言：中文、英文、日文、韩文、法文、德文。
```

#### Team YAML (Team/xxx.yaml)

```plaintext
# Team 配置
id: "t1e5f6a7"
name: "内容创作团队"
description: "从选题到最终发布的完整内容创作流程"
captain: "a1b2c3d4" # 队长 Agent ID
members:
 - agent_id: "a1b2c3d4" # 队长同时也是成员
 - agent_id: "b5c6d7e8" # 文案 Agent
 role: "内容撰写"
 - agent_id: "c9d0e1f2" # 校对 Agent
 role: "审校润色"
created_at: "2026-05-24T10:30:00Z"
```

#### SESSION.yaml

```plaintext
# Session 元数据
id: "s9d3f2g1"
name: "产品需求文档撰写"
target_type: "team" # "agent" 或 "team"
target_id: "t1e5f6a7" # 调用的 Agent/Team ID
status: "active" # active / paused / completed
created_at: "2026-05-24T11:00:00Z"
updated_at: "2026-05-24T12:30:00Z"
tags: ["产品", "PRD"]
```

### 4.3 SQLite 索引表 存储层

SQLite 作为辅助索引加速检索，数据结构与文件系统保持同步。文件系统为 **Single Source of Truth**。

```plaintext
-- 索引表设计
CREATE TABLE agents (
 id TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 description TEXT,
 model_provider TEXT,
 model_name TEXT,
 created_at TEXT,
 updated_at TEXT
);

CREATE TABLE teams (
 id TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 captain_id TEXT,
 member_count INTEGER,
 created_at TEXT
);

CREATE TABLE team_members (
 team_id TEXT,
 agent_id TEXT,
 role TEXT,
 PRIMARY KEY (team_id, agent_id),
 FOREIGN KEY (team_id) REFERENCES teams(id),
 FOREIGN KEY (agent_id) REFERENCES agents(id)
);

CREATE TABLE sessions (
 id TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 target_type TEXT CHECK(target_type IN ('agent','team')),
 target_id TEXT,
 status TEXT CHECK(status IN ('active','paused','completed')),
 created_at TEXT,
 updated_at TEXT
);
```

## 5. 核心模块设计

### 5.1 Agent 模块

Agent 类接口

```plaintext
class Agent:
 """单个 AI 智能体"""

 id: str # 唯一标识
 name: str # 显示名称
 config: AgentConfig # 从 AGENT.yaml 加载的配置
 llm: LLMAdapter # LLM 调用适配器

 @classmethod
 async def load(cls, agent_id: str) -> "Agent":
 """从文件系统加载 Agent"""

 async def chat(
 self,
 messages: list[dict],
 tools: list[dict] | None = None
 ) -> str:
 """发送消息并获取回复（流式 / 非流式）"""

 async def chat_stream(
 self,
 messages: list[dict]
 ) -> AsyncGenerator[str, None]:
 """流式对话，逐 token yield"""

 def get_skills(self) -> list[Skill]:
 """返回该 Agent 绑定的所有 Skill"""
```

### 5.2 AgentTeam 模块

AgentTeam 类接口

```plaintext
class AgentTeam:
 """Agent 团队"""

 id: str
 name: str
 captain: Agent # 队长 Agent
 members: list[Agent] # 成员 Agent 列表

 @classmethod
 async def load(cls, team_id: str) -> "AgentTeam":
 """从 Team YAML + Agents 目录加载团队"""

 async def execute(self, task: str) -> TeamResult:
 """执行任务：队长分解 → 分派成员 → 汇总结果"""
```

### 5.3 Session 模块

Session 类接口

```plaintext
class Session:
 """一次对话会话"""

 id: str
 name: str
 target: Agent | AgentTeam # 调用的对象
 messages: list[Message] # 对话历史
 files: list[str] # 关联文件路径

 @classmethod
 async def create(cls, name: str, target) -> "Session": ...

 async def add_message(self, role: str, content: str): ...

 async def save(self): ...
```

## 6. LLM API 适配层

### 6.1 设计策略

**全面适配主流 LLM 提供商**，覆盖以下四类协议：

适配器覆盖的提供商协议
`OpenAICompatAdapter`OpenAI / DeepSeek / Qwen / GLM / Moonshot / 豆包 / 百川 / Step 等OpenAI 兼容协议 (Chat Completions API)
`AnthropicAdapter`Anthropic Claude 系列Anthropic Messages API
`GoogleAdapter`Google Gemini 系列Google Generative AI SDK
`CustomAdapter`用户自定义端点（兼容 OpenAI 协议子集）用户配置的 HTTP 端点

工厂类 `LLMAdapterFactory` 根据 `AGENT.yaml` 中 `model.provider` 字段自动选择适配器，对上层透明。

### 6.2 适配器接口

```plaintext
class LLMAdapter(ABC):
 """LLM 调用抽象基类"""

 @abstractmethod
 async def chat(
 self,
 messages: list[dict],
 model: str,
 temperature: float,
 max_tokens: int,
 tools: list[dict] | None = None,
 stream: bool = False
 ) -> LLMResponse: ...

 @abstractmethod
 async def chat_stream(
 self,
 messages: list[dict],
 model: str,
 temperature: float,
 max_tokens: int
 ) -> AsyncGenerator[str, None]: ...

class OpenAICompatAdapter(LLMAdapter):
 """OpenAI 兼容协议适配器
 适用于：OpenAI / DeepSeek / Qwen / GLM / Moonshot / 自定义端点
 """
 def __init__(self, base_url: str, api_key: str, timeout: int = 120):
 ...

class LLMAdapterFactory:
 """根据 provider 类型返回对应适配器"""

 @staticmethod
 def create(config: LLMConfig, api_key: str) -> LLMAdapter: ...
```

### 6.3 API 密钥管理

 - 密钥不存储在 YAML 中，YAML 仅存 `api_key_ref: "vault:xxx"` 引用。

 - 密钥实际存储在加密的本地 Key Vault 中（见 [第 11 章](#s11)）。

 - 首次配置 Agent 时，UI 引导用户输入密钥 → 加密存储 → 写入引用。

**多密钥管理已确认。**每个 Agent 可绑定不同的 API 密钥（不同提供商或同一提供商的不同 Key），Vault 以 `{key_id}` 索引多条密钥。UI 中提供密钥管理器面板，可添加/删除/查看密钥别名（不暴露明文）。

## 7. Agent 通信协议

ACTs 为本地桌面软件，Agent 运行在同一进程内，通信采用**进程内直接函数调用**。队长 Agent 通过 Orchestrator 直接调用成员 Agent 的 `chat()` 方法，消息通过内存中的 `Message` 对象传递，无需消息队列或 WebSocket。

### 7.1 消息格式

```plaintext
@dataclass
class Message:
 role: str # "user" / "assistant" / "system" / "tool"
 content: str # 消息正文
 timestamp: datetime # 时间戳
 metadata: dict # 扩展元数据（如来源 Agent ID）

@dataclass
class SubTask:
 """队长分派的子任务"""
 id: str
 agent_id: str # 目标 Agent
 instruction: str # 任务指令
 context: list[Message] # 上下文消息
 status: str # pending / running / done / failed
 result: str | None # 执行结果
```

## 8. AgentTeam 调度引擎（Orchestrator）

### 8.1 调度流程

 - **接收任务** — 用户向 Team 发送一个复杂任务。

 - **队长分析** — 队长 Agent 收到任务描述 + 所有成员的能力描述，输出子任务分解方案。

 - **分派执行** — Orchestrator 解析队长的分解方案，将子任务路由给对应成员 Agent。

 - **结果汇总** — 队长 Agent 收集所有子任务结果，整合为最终回复。

**LLM 推理分解。**队长 Agent 收到原始任务后，通过一次 LLM 调用输出结构化子任务列表（JSON）。每个子任务包含目标 Agent ID 和任务指令。队长输出格式固定为 JSON Schema，Orchestrator 解析后自动调度。若队长分配了不存在的 Agent ID 或指令格式错误，触发重试（最多 2 次）。

### 8.2 队长任务分解 Prompt 模板

```plaintext
你是一个 Agent 团队的队长。你的团队有以下成员：

{% for member in members %}
- {{ member.agent_id }}: {{ member.role }} — {{ member.description }}
{% endfor %}

现在用户向你提交了以下任务：

{{ task }}

请将任务分解为子任务，分配给最合适的团队成员。输出严格的 JSON 格式：

{
 "subtasks": [
 {
 "agent_id": "...",
 "instruction": "..."
 }
 ]
}
```

### 8.3 执行策略

策略说明适用场景
串行 (Sequential)按队长指定顺序逐个执行，后一个可看到前一个的结果有依赖关系的子任务
并行 (Parallel)无依赖的子任务同时分发给多个 Agent独立子任务（默认）
混合 (Hybrid)队长在分解时标注依赖关系，Orchestrator 按 DAG 调度复杂流程

Phase 1 实现**串行 + 并行**两种模式，默认并行执行。队长检测到子任务间依赖时自动降级为串行。混合 DAG 调度留到 Phase 2。

## 9. Session 生命周期

### 9.1 状态机

```plaintext
[创建] → active ←→ paused
 ↓
 completed
```

状态说明允许操作
`active`活跃会话，可发送消息发送消息、追加文件、暂停
`paused`已暂停，保留上下文恢复、归档
`completed`已完成/归档查看历史、导出

### 9.2 content.txt 格式

会话内容以纯文本行存储，每行一条消息，便于 AI 解析：

```plaintext
# Session: 产品需求文档撰写
# Created: 2026-05-24T11:00:00Z

[2026-05-24 11:00:12] [user] 请帮我写一份智能音箱的产品需求文档

[2026-05-24 11:00:45] [captain:a1b2c3d4] 正在分析任务并分派给团队成员...
 → [agent:b5c6d7e8] 请撰写智能音箱PRD的功能需求部分
 → [agent:c9d0e1f2] 请在完成后对文档进行审校润色

[2026-05-24 11:03:20] [agent:b5c6d7e8] 功能需求部分已完成：
 1. 语音交互模块 ...
 2. 智能家居控制 ...

[2026-05-24 11:05:00] [agent:c9d0e1f2] 审校完成，已修正3处表达并优化结构
```

Phase 1 **单 Session 活跃**。同一时间只能有一个 active Session，其他 Session 可处于 paused 状态。切换 Session 时自动 pause 当前并恢复目标。Phase 2 支持多 Session 并发（多 Tab 切换）。

## 10. PyQt6 界面设计

### 10.1 主窗口布局

```plaintext
┌──────────┬──────────────────────────────┐
│ │ │
│ 导航栏 │ 主内容区 │
│ (左侧) │ (右侧) │
│ │ │
│ ┌──────┐ │ ┌────────────────────────┐ │
│ │Agents│ │ │ │ │
│ │Teams │ │ │ 聊天 / 配置面板 │ │
│ │Sess. │ │ │ │ │
│ │ │ │ │ │ │
│ │ │ │ └────────────────────────┘ │
│ │ │ │ ┌────────────────────────┐ │
│ │ │ │ │ 输入区域 │ │
│ └──────┘ │ └────────────────────────┘ │
└──────────┴──────────────────────────────┘
```

### 10.2 核心面板

面板标签功能
**Agent 管理** 核心列表 + 详情创建/编辑/删除 Agent，配置 LLM 参数、System Prompt、Skills
**Team 管理** 核心列表 + 详情创建/编辑/删除 Team，选择队长和成员
**Session 面板** 核心列表 + 聊天创建/切换/归档 Session，查看历史记录
**聊天区** UI对话气泡显示当前 Session 的对话历史，支持流式输出
**输入区** UI文本框 + 发送用户输入消息，支持多行、文件拖入
**设置面板** 配置对话框全局设置：数据目录、Vault 管理、主题切换

### 10.3 UI 组件树（简化）

```plaintext
MainWindow (QMainWindow)
├── QSplitter (horizontal)
│ ├── NavigationPanel (QWidget) # 左侧导航
│ │ ├── QListWidget (Agents / Teams / Sessions 切换)
│ │ └── QPushButton (新建按钮)
│ └── QStackedWidget # 右侧内容区
│ ├── AgentManagerPage
│ │ ├── AgentListWidget + AgentDetailForm
│ │ └── SkillEditorDialog
│ ├── TeamManagerPage
│ │ ├── TeamListWidget + TeamDetailForm
│ │ └── MemberComposer (拖拽选人)
│ └── SessionPage
│ ├── SessionListWidget
│ └── ChatView
│ ├── ChatBubbleWidget (QScrollArea 内)
│ └── InputBar (QTextEdit + QPushButton)
└── QMenuBar + QStatusBar
```

## 11. 安全方案

### 11.1 API 密钥加密存储

环节方案
加密算法AES-256-GCM（通过 `cryptography` 库）
主密钥来源首次启动时生成随机 256-bit 密钥，存入系统凭据管理器（Windows Credential Manager / macOS Keychain）
密钥存储文件`Acts/.vault.enc` — AES 加密的 JSON，存储所有 API 密钥
运行时访问密钥仅在调用 LLM 时从 Vault 解密到内存，用完即丢弃，不落盘

[待确认] 主密钥管理策略

Windows 环境下建议使用 Windows Credential Manager（通过 `keyring` 库），无需用户记忆主密码。macOS 同理使用 Keychain。

建议方案：使用 `keyring` 库自动对接系统凭据管理器。降级方案：若系统凭据管理器不可用，引导用户设置主密码（PBKDF2 派生密钥）。

### 11.2 安全边界

 - **数据全本地** — 所有 Agent 配置、Session 内容、文件均存储在本地 `Acts/` 目录，不上传至任何服务器。

 - **Skill 安全** — Phase 1 仅支持 **Prompt 扩展型 Skill**（纯文本追加到 System Prompt），不开放脚本执行。Phase 2 引入脚本执行时采用 `subprocess` 独立子进程 + 超时限制（默认 60s）+ 文件系统访问白名单。

## 12. 构建路线图

### Phase 1 — MVP（最小可行产品）

#任务预估工时产出
1项目骨架搭建：目录结构、依赖安装、日志系统0.5d可运行的 main.py
2Storage 层：YAML 读写 + 文件系统管理 + SQLite 索引1dstorage/ 模块
3Security 层：Key Vault（加密存储 + keyring 集成）0.5dsecurity/vault.py
4LLM 适配层：OpenAI 兼容 + Anthropic + Google Gemini + Custom 四类适配器2dllm/ 模块
5Core — Agent 模块：加载、配置、对话（含流式）1.5dcore/agent.py
6Core — Session 模块：创建、消息管理、持久化1dcore/session.py
7UI — 主窗口框架 + 导航栏 + 页面路由1dui/main_window.py
8UI — Agent 管理面板（创建/编辑/删除 + LLM 配置表单）1.5dui/agent_panel.py
9UI — Session 聊天面板（对话气泡 + 输入框 + 流式渲染）1.5dui/session_panel.py
10集成测试 + 端到端调试1dtests/
**Phase 1 合计****~11.5d**可用的单 Agent 对话 + 管理功能 + 多 LLM 适配

### Phase 2 — Team 协作

#任务预估工时
11Core — AgentTeam 模块：加载、队长调度、成员管理1.5d
12Core — Orchestrator：任务分解解析 + 并行/串行调度2d
13UI — Team 管理面板（创建/编辑 + 成员拖拽编排）1.5d
14UI — Team 聊天视图（显示子任务分配和执行过程）1d
15集成测试0.5d
**Phase 2 合计****~6.5d**

### Phase 3 — 增强功能

功能预计工时
Skill 市场（导入/导出 Skill YAML）1d
多 Session 并发（Tab 页切换）1.5d
DAG 混合调度1.5d
Session 导出（Markdown / PDF）0.5d
暗色/亮色主题切换0.5d

## 13. 已确认的架构决策

以下事项已确认，文档正文已同步更新为最终方案：

#事项最终方案影响模块

 1
 **LLM 提供商支持范围**
 全面适配 — OpenAI 兼容协议 + Anthropic + Google Gemini + Custom，Phase 1 全部实现
 LLM 适配层

 2
 **多密钥管理**
 支持，Vault 管理多密钥，UI 提供密钥管理器
 Security / UI

 3
 **Agent 间通信机制**
 进程内直接函数调用，消息通过内存对象传递
 Core / Orchestrator

 4
 **队长任务分解策略**
 LLM 推理分解，输出固定 JSON Schema，Orchestrator 解析调度
 Orchestrator

 5
 **执行策略粒度**
 Phase 1 串行+并行（默认并行，依赖检测降级）；Phase 2 DAG
 Orchestrator

 6
 **Session 并发支持**
 Phase 1 单 Session 活跃；Phase 2 多 Tab 并发
 Session / UI

 7
 **Skill 脚本执行安全**
 Phase 1 仅 Prompt 扩展型 Skill；Phase 2 加 subprocess 沙箱
 Skill / Security

---

本文档为 ACTs 软件构建规格说明书，所有架构决策已确认，可直接作为编码蓝图使用。