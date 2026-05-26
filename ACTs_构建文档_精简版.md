# ACTs 构建文档（AI Agent 精简版）

> 版本 1.1 | 2026-05-24 | Python 3.10+ / PyQt6

## 项目定义

**ACTs** — 桌面 Agent 搭建工具。用户提供 LLM API Key，本地构建/调试/编排多 Agent 并组队执行复杂任务。

**核心对象**：
- **Agent** — 单 AI 智能体，绑定 LLM + System Prompt + Skills | 存于 `Acts/Agents/{agent_id}/AGENT.yaml`
- **AgentTeam** — 多 Agent 团队，含队长负责拆解分派 | 存于 `Acts/Team/{team_id}.yaml`
- **Session** — 一次会话，记录 Agent/Team、历史、文件 | 存于 `Acts/Sessions/{session_id}/`

**理念**：用户自托管 | YAML 文件即配置 | Agent+Skill 可组合 | AI 友好结构化

## 技术栈

| 层 | 技术 | 用途 |
|---|---|---|
| UI | PyQt6 | 桌面 GUI |
| 配置 | PyYAML | YAML 读写 |
| LLM 调用 | httpx/aiohttp | 异步 HTTP |
| 调度 | asyncio | 异步并发 |
| 索引 | SQLite (aiosqlite) | 快速检索 |
| 加密 | cryptography | AES-256-GCM |
| 模板 | Jinja2 | Prompt 渲染 |
| 测试 | pytest | 单元/集成测试 |

**源码目录**：`acts/src/{core,llm,storage,security,ui,utils}/` + `main.py` + `tests/`

## 系统架构

```
PyQt6 UI → Core Engine (Agent/Team/Session/Orchestrator)
            ├── LLM Adapter Layer (OpenAI/Anthropic/Google/Custom)
            ├── Storage Layer (YAML + SQLite)
            └── Security Vault (AES加密)
```

数据流：UI 信号 → Core 处理 → Storage 持久化 / LLM 调用 → 结果回流 UI

## 数据存储

### 目录结构
```
Acts/
├── Agents/{agent_id}/
│   ├── AGENT.yaml          # Agent 核心配置
│   └── Skills/{name}.yaml
├── Team/{team_id}.yaml
└── Sessions/{session_id}/
    ├── SESSION.yaml
    └── content/
        └── content.txt
```

### 核心 YAML Schema

**AGENT.yaml**：id, name, description, system_prompt, model{provider, name, temperature, max_tokens}, llm_api{base_url, api_key_ref, timeout_seconds}, skills[], created_at, updated_at

**Skill YAML**：name, description, type("system_prompt_extension"), prompt_extension

**Team YAML**：id, name, description, captain(agent_id), members[{agent_id, role}], created_at

**SESSION.yaml**：id, name, target_type("agent"|"team"), target_id, status("active"|"paused"|"completed"), created_at, updated_at, tags[]

### SQLite 索引（辅助，文件系统为 Single Source of Truth）

4 张表：`agents`, `teams`, `team_members`, `sessions`（字段与 YAML 对应，用于加速检索）

## 核心模块接口

### Agent
```python
class Agent:
    id, name, config: AgentConfig, llm: LLMAdapter
    @classmethod async def load(cls, agent_id) → Agent
    async def chat(messages, tools=None) → str
    async def chat_stream(messages) → AsyncGenerator[str]
    def get_skills() → list[Skill]
```

### AgentTeam
```python
class AgentTeam:
    id, name, captain: Agent, members: list[Agent]
    @classmethod async def load(team_id) → AgentTeam
    async def execute(task: str) → TeamResult
```

### Session
```python
class Session:
    id, name, target: Agent|AgentTeam, messages: list[Message], files: list[str]
    @classmethod async def create(name, target) → Session
    async def add_message(role, content)
    async def save()
```

## LLM API 适配层

| 适配器 | 覆盖 | 协议 |
|---|---|---|
| `OpenAICompatAdapter` | OpenAI/DeepSeek/Qwen/GLM/Moonshot/豆包/百川/Step | OpenAI Chat Completions |
| `AnthropicAdapter` | Claude | Anthropic Messages API |
| `GoogleAdapter` | Gemini | Google Generative AI SDK |
| `CustomAdapter` | 用户自定义端点 | OpenAI 兼容子集 |

`LLMAdapterFactory.create(config, api_key)` 根据 `model.provider` 自动选择。

**密钥管理**：YAML 仅存 `api_key_ref: "vault:xxx"`，密钥加密存储在 `Acts/.vault.enc`（AES-256-GCM），通过系统凭据管理器管理主密钥。支持多密钥，UI 提供密钥管理器面板。

## Agent 通信协议

**进程内直接调用** — 队长通过 Orchestrator 直接调成员 `chat()`，消息为内存 `Message` 对象。

```python
@dataclass
class Message:
    role: str       # user/assistant/system/tool
    content: str
    timestamp: datetime
    metadata: dict

@dataclass
class SubTask:
    id, agent_id, instruction: str
    context: list[Message]
    status: str     # pending/running/done/failed
    result: str|None
```

## Orchestrator 调度引擎

**流程**：用户任务 → 队长 LLM 推理分解 → 输出 JSON 子任务列表 → Orchestrator 解析调度 → 汇总结果

队长输出固定 JSON Schema：`{"subtasks": [{"agent_id": "...", "instruction": "..."}]}`。分配无效 agent_id 或格式错误时最多重试 2 次。

**执行策略**：
- 串行：有依赖时按序执行
- 并行（默认）：无依赖子任务并发
- 混合 DAG：Phase 2 实现，队长标注依赖关系

Phase 1 实现串行+并行，默认并行，队长检测依赖自动降级。

## Session 状态机

```
[创建] → active ←→ paused → completed
```

- `active`：活跃，可发消息/追加文件
- `paused`：暂停，可恢复/归档
- `completed`：完成，只读查看

Phase 1 单 Session 活跃（切换自动 pause/resume），Phase 2 支持多 Tab 并发。

## UI 布局

```
┌──────────┬──────────────────────────┐
│ 导航栏    │ 主内容区 (QStackedWidget) │
│ Agents    │ ┌────────────────────┐  │
│ Teams     │ │ 聊天/配置面板       │  │
│ Sessions  │ └────────────────────┘  │
│           │ ┌────────────────────┐  │
│ [新建]    │ │ 输入区域            │  │
└──────────┴──────────────────────────┘
```

**核心面板**：Agent管理(CRUD+LLM配置) | Team管理(队长/成员编排) | Session(聊天+历史) | 设置(数据目录/Vault/主题)

**组件树**：MainWindow → QSplitter → NavigationPanel(左) + QStackedWidget(右, 含 AgentManagerPage/TeamManagerPage/SessionPage → ChatView+InputBar)

## 安全方案

- **密钥加密**：AES-256-GCM，主密钥存系统凭据管理器（Windows Credential Manager），运行时解密到内存用完即弃
- **数据全本地**：不上传任何服务器
- **Skill 安全**：Phase 1 仅 Prompt 扩展型（纯文本追加 System Prompt）；Phase 2 脚本执行用 subprocess 子进程 + 60s 超时 + 文件白名单

## 构建路线图

### Phase 1 MVP (~11.5d)

| # | 任务 | 工时 |
|---|---|---|
| 1 | 项目骨架 + 日志 | 0.5d |
| 2 | Storage 层 (YAML+SQLite) | 1d |
| 3 | Security Vault | 0.5d |
| 4 | LLM 适配层 (4类适配器) | 2d |
| 5 | Agent 模块 | 1.5d |
| 6 | Session 模块 | 1d |
| 7 | 主窗口框架+导航 | 1d |
| 8 | Agent 管理面板 | 1.5d |
| 9 | Session 聊天面板 | 1.5d |
| 10 | 集成测试 | 1d |

产出：可用的单 Agent 对话 + 管理功能 + 多 LLM 适配

### Phase 2 Team 协作 (~6.5d)

| # | 任务 | 工时 |
|---|---|---|
| 11 | AgentTeam 模块 | 1.5d |
| 12 | Orchestrator | 2d |
| 13 | Team 管理面板 | 1.5d |
| 14 | Team 聊天视图 | 1d |
| 15 | 集成测试 | 0.5d |

### Phase 3 增强

Skill 市场(1d) | 多 Session 并发(1.5d) | DAG 混合调度(1.5d) | Session 导出(0.5d) | 主题切换(0.5d)

## 已确认架构决策

| # | 事项 | 方案 |
|---|---|---|
| 1 | LLM 支持范围 | 全面适配：OpenAI兼容+Anthropic+Gemini+Custom，Phase 1 全实现 |
| 2 | 多密钥管理 | 支持，Vault 管理 + UI 密钥管理器 |
| 3 | Agent 间通信 | 进程内函数调用，消息走内存 |
| 4 | 队长任务分解 | LLM 推理 → 固定 JSON Schema，Orchestrator 解析调度 |
| 5 | 执行策略 | Phase 1 串行+并行(默认并行，依赖检测降级)；Phase 2 DAG |
| 6 | Session 并发 | Phase 1 单 Session 活跃；Phase 2 多 Tab |
| 7 | Skill 安全 | Phase 1 仅 Prompt 扩展；Phase 2 加 subprocess 沙箱 |