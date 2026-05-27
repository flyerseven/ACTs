# ACTs 构建文档

本文档按工程文件逐项梳理 ACTs 的功能、核心类与函数职责，以及每个模块采用的实现策略。重点覆盖 Python 脚本与测试文件，同时补充文档、资源与运行时目录的用途，方便快速理解整个工程的组成与运行方式。

## 1. 工程总览

ACTs 是一个基于 PyQt6 的桌面端多 Agent 工具。主流程是：入口脚本读取命令行参数，初始化文件存储与加密 Vault，再启动主窗口；UI 层负责管理 Agent、Session 与聊天流式输出；Core 层封装 Agent、Session、Token 统计与领域数据结构；LLM 层统一不同提供方的请求方式；Storage 层负责 YAML 与 SQLite；Security 层负责密钥加密保存；Scripts 提供离线资源下载与辅助工具；Tests 覆盖核心行为与渲染逻辑。

### 运行时数据流

1. `main.py` 解析启动参数并初始化日志、文件结构、Vault 与 TokenTracker。
2. `src/ui/main_window.py` 构建主界面，联动 AgentPanel 与 SessionPanel。
3. 用户在 `src/ui/session_panel.py` 中发送消息后，`src/core/session.py` 先持久化用户消息。
4. `src/core/agent.py` 通过 `src/llm/factory.py` 选择适配器，最终由 `src/llm/openai_compat.py` 或 `MockAdapter` 发送请求。
5. 流式回复由 Qt 线程传回 UI，再由 `src/ui/chat_widget.py` 渲染 Markdown、代码高亮与 LaTeX。
6. 会话结束后，Session 会保存消息与摘要，TokenTracker 会记录用量和估算成本。

## 2. 根目录文件

| 文件 | 作用 | 主要内容 | 实现策略 |
|---|---|---|---|
| [main.py](main.py) | 应用入口 | 命令行解析、应用初始化、窗口启动 | 先处理健康检查和 token 统计，再建立 `FileStore`、`Vault`、`TokenTracker`，最后启动 `QApplication` 与 `MainWindow`。 |
| [README.md](README.md) | 快速上手说明 | 安装、运行、健康检查、数据目录 | 面向首次使用者，提供最短路径的启动说明。 |
| [Plan.md](Plan.md) | 开发计划 | Phase 1/2/3 任务清单 | 用勾选式任务跟踪项目进度，并给出验收标准。 |
| [build.md](build.md) | 工程说明文档 | 本文件本身 | 汇总所有脚本、类、函数和策略，作为工程级总览。 |

## 3. 文档目录

| 文件 | 作用 | 内容重点 | 实现策略 |
|---|---|---|---|
| [docs/index.md](docs/index.md) | 文档索引 | 架构、决策记录、目录结构 | 作为文档入口，帮助从总览进入细节。 |
| [docs/architecture.md](docs/architecture.md) | 架构总览 | 分层、数据流、线程模型、依赖 | 以图和表说明系统结构、主流程与关键设计决策。 |
| [docs/decisions/001-yaml-first-persistence.md](docs/decisions/001-yaml-first-persistence.md) | 决策记录 | YAML 作为主持久化格式 | 强调文件即真相，SQLite 仅做辅助索引。 |
| [docs/decisions/002-llm-adapter-pattern.md](docs/decisions/002-llm-adapter-pattern.md) | 决策记录 | 适配器模式 | 把不同 LLM 提供方统一为同一接口。 |
| [docs/decisions/003-vault-api-key-management.md](docs/decisions/003-vault-api-key-management.md) | 决策记录 | API Key 加密管理 | 使用 AES-256-GCM 和 `vault:<alias>` 引用方式。 |
| [docs/decisions/004-webengine-katex-chat-rendering.md](docs/decisions/004-webengine-katex-chat-rendering.md) | 决策记录 | 聊天渲染路径 | WebEngine 负责富渲染，QTextBrowser 负责回退。 |
| [docs/decisions/005-session-message-format.md](docs/decisions/005-session-message-format.md) | 决策记录 | 消息文件格式 | 采用追加写入的逐行格式保存消息。 |
| [docs/decisions/006-context-compression.md](docs/decisions/006-context-compression.md) | 决策记录 | 上下文压缩 | 通过摘要和保留最近消息控制上下文长度。 |
| [docs/decisions/007-threading-model.md](docs/decisions/007-threading-model.md) | 决策记录 | Qt 线程与 asyncio 混合模型 | 避免 LLM 请求阻塞 GUI 主线程。 |

## 4. 核心模块：src/core

### 4.1 [src/core/models.py](src/core/models.py)

| 类 / 函数 | 作用 |
|---|---|
| `utc_now_iso()` | 生成 UTC 时间戳字符串，统一对象创建与更新时间格式。 |
| `LLMConfig` | 描述模型提供方、模型名、温度、最大 token、基础 URL、密钥引用与超时。 |
| `AgentConfig` | 描述 Agent 的身份、系统提示词、模型配置、技能列表与时间戳。 |
| `SessionMeta` | 描述 Session 的元信息，包括目标 Agent、分组、标签、压缩参数和摘要。 |
| `Message` | 单条消息数据结构，包含角色、内容、时间戳和元数据。 |
| `llm_config_from_dict()` / `llm_config_to_dict()` | 在字典与 `LLMConfig` 之间转换。 |
| `agent_config_from_dict()` / `agent_config_to_dict()` | 在 YAML 字典与 `AgentConfig` 之间转换。 |
| `session_meta_from_dict()` / `session_meta_to_dict()` | 在 YAML 字典与 `SessionMeta` 之间转换。 |

实现策略：
- 使用 dataclass 作为领域模型，减少手写样板代码。
- 提供显式的 dict 转换函数，避免让存储层直接依赖 dataclass 序列化细节。
- 所有时间统一用 UTC ISO 格式，便于排序与跨机器读取。

### 4.2 [src/core/agent.py](src/core/agent.py)

| 类 / 函数 | 作用 |
|---|---|
| `LoadedSkill` | 预留的技能加载结果结构，用于未来技能系统扩展。 |
| `Agent` | 代表一个可执行的 Agent 实例，绑定配置、LLM 适配器与 token 统计器。 |
| `Agent.load()` | 从存储中读取 Agent YAML，解析配置，按密钥引用创建适配器。 |
| `Agent.chat()` | 一次性聊天，返回完整字符串回复。 |
| `Agent.chat_stream()` | 流式聊天，逐块 yield 回复内容。 |
| `Agent._record_usage()` | 将模型用量写入 TokenTracker。 |

实现策略：
- Agent 本身不直接知道 HTTP 细节，只依赖 `LLMAdapter` 接口。
- `load()` 负责把 YAML、Vault 和适配器工厂串起来，构成完整运行对象。
- `chat_stream()` 在 finally 中记录用量，保证流式调用结束后也能统计 token。

### 4.3 [src/core/session.py](src/core/session.py)

| 类 / 函数 | 作用 |
|---|---|
| `Session` | 会话对象，持有元数据、消息列表和存储引用。 |
| `Session.create()` | 新建会话、分配 ID、写入初始元数据并立即保存。 |
| `Session.delete()` | 删除会话目录。 |
| `Session.load()` | 从 YAML 与内容文件恢复会话和消息。 |
| `Session.add_message()` | 追加消息并刷新更新时间。 |
| `Session.build_context_messages()` | 根据系统提示、摘要和最近消息构造 LLM 上下文。 |
| `Session.maybe_compress_context()` | 按压缩间隔和保留窗口决定是否生成摘要。 |
| `Session._count_turns()` | 统计 assistant 回合数，用于压缩触发判断。 |
| `Session.save()` | 写回会话 YAML 与消息内容文件。 |
| `render_content_lines()` | 将消息渲染成可追加的文本格式。 |
| `parse_content_lines()` | 从保存文件中反解析消息对象。 |
| `summarize_messages()` | 将旧消息压缩成摘要文本，限制长度。 |

实现策略：
- 会话元数据与正文分离，元数据放在 YAML，消息放在 content.txt。
- 保存格式采用逐行追加风格，便于写入和恢复。
- 上下文压缩不是依赖外部模型，而是先用本地摘要策略保留最近窗口，降低复杂度。
- 读取时兼容新旧内容路径，保证老数据可继续打开。

### 4.4 [src/core/token_tracker.py](src/core/token_tracker.py)

| 类 / 函数 | 作用 |
|---|---|
| `MODEL_PRICING` | 已知模型的近似单价表。 |
| `_model_price_key()` | 根据模型名模糊匹配定价键。 |
| `_calculate_cost()` | 按输入和输出 token 估算成本。 |
| `TokenUsage` | 单条用量记录的数据结构。 |
| `UsageStats` | 聚合统计结构，包含请求数、token 数、成本和按模型分组数据。 |
| `TokenTracker` | 读写 token 用量日志并提供统计查询。 |
| `TokenTracker.record()` | 写入一条 JSONL 记录。 |
| `TokenTracker._iter_records()` | 读取并过滤日志记录。 |
| `TokenTracker.get_session_stats()` | 按 session 聚合统计。 |
| `TokenTracker.get_total_stats()` | 全量聚合统计。 |
| `TokenTracker.get_recent()` | 读取最近若干条记录。 |
| `TokenTracker.clear()` | 清空日志文件。 |

实现策略：
- 使用 JSONL 作为轻量日志格式，写入简单、追加安全。
- 定价通过模糊匹配模型名，适配命名变化。
- 统计逻辑完全从日志回放聚合，不额外依赖数据库。

### 4.5 [src/core/team.py](src/core/team.py)

| 类 / 函数 | 作用 |
|---|---|
| `AgentTeam` | Team 的最小数据结构，包含队长与成员列表。 |

实现策略：
- 目前只是 Phase 2 的占位模型，没有调度逻辑。
- 用 dataclass 保持未来扩展时的序列化兼容性。

### 4.6 [src/core/skill.py](src/core/skill.py)

| 类 / 函数 | 作用 |
|---|---|
| `Skill` | 技能定义的最小数据结构。 |

实现策略：
- 与 Team 一样是占位结构，为未来技能系统预留模型入口。

## 5. LLM 层：src/llm

### 5.1 [src/llm/base.py](src/llm/base.py)

| 类 / 函数 | 作用 |
|---|---|
| `LLMResponse` | 单次模型调用结果，包含内容、原始响应与用量。 |
| `LLMAdapter` | 抽象基类，定义统一的聊天接口。 |
| `MockAdapter` | 无需真实 API 的模拟实现，会回显最后一条 user 消息。 |

实现策略：
- 用抽象接口隔离上层业务与具体 API 协议。
- MockAdapter 作为默认回退，方便本地测试和无密钥环境启动。
- 流式输出按词切块，足够支持 UI 流式渲染测试。

### 5.2 [src/llm/factory.py](src/llm/factory.py)

| 类 / 函数 | 作用 |
|---|---|
| `LLMAdapterFactory.create()` | 根据配置和 API key 选择具体适配器。 |

实现策略：
- 使用 provider 字符串路由适配器。
- 对 openai 兼容类 provider，如果没有 key 就自动退回 MockAdapter。
- 不支持的 provider 直接抛出异常，避免静默失败。

### 5.3 [src/llm/openai_compat.py](src/llm/openai_compat.py)

| 类 / 函数 | 作用 |
|---|---|
| `OpenAICompatAdapter` | 面向 OpenAI 兼容接口的 HTTP 客户端。 |
| `OpenAICompatAdapter.chat()` | 发起非流式请求并返回完整结果。 |
| `OpenAICompatAdapter.chat_stream()` | 使用 SSE 风格流式读取增量 token。 |

实现策略：
- 基于 `httpx.AsyncClient` 实现异步请求。
- 统一请求体为 OpenAI 兼容的 `chat/completions` 格式。
- 对 HTTP 错误做二次包装，尽量带出服务端返回的错误详情。
- 流式接口逐行解析 `data:` 段，并在收到 usage 时更新 `last_usage`。

## 6. 存储层：src/storage

### 6.1 [src/storage/file_store.py](src/storage/file_store.py)

| 类 / 函数 | 作用 |
|---|---|
| `FileStore` | 管理工程运行时目录结构与常用路径。 |
| `ensure_structure()` | 创建 Agents、Sessions 和 Team 目录。 |
| `agent_dir()` / `agent_yaml_path()` | Agent 存储路径。 |
| `team_yaml_path()` | Team YAML 路径。 |
| `session_dir()` / `session_yaml_path()` | Session 基础路径。 |
| `session_content_dir()` / `session_content_path()` | Session 正文路径。 |
| `session_legacy_content_path()` | 兼容旧格式的 content.txt 路径。 |
| `list_agents()` / `list_sessions()` | 枚举已有对象 ID。 |
| `new_agent_id()` / `new_session_id()` | 生成新的短 ID。 |

实现策略：
- 将磁盘布局集中到一个类里，所有调用方都从这里拿路径，降低路径拼接散落问题。
- 默认根目录指向项目中的 Acts 运行时目录。
- 同时兼容新旧消息路径，减少迁移成本。

### 6.2 [src/storage/yaml_io.py](src/storage/yaml_io.py)

| 类 / 函数 | 作用 |
|---|---|
| `read_yaml()` | 安全读取 YAML，缺失文件时返回空字典。 |
| `write_yaml()` | 写出 YAML，并保留键顺序。 |

实现策略：
- 只提供最薄封装，避免把业务逻辑塞进 IO 层。
- 统一使用 UTF-8 编码。
- 写入时不转义 Unicode，保证可读性和可编辑性。

### 6.3 [src/storage/db.py](src/storage/db.py)

| 类 / 函数 | 作用 |
|---|---|
| `CREATE_TABLES` | agents 与 sessions 两张索引表的建表语句。 |
| `init_db()` | 初始化 SQLite 索引数据库。 |
| `upsert_agent()` | 写入或更新 agent 索引行。 |
| `upsert_session()` | 写入或更新 session 索引行。 |

实现策略：
- SQLite 作为补充索引而非主存储，和 YAML 源数据并存。
- 使用 UPSERT 保证重复写入时自动更新。
- 所有操作都通过异步连接执行，方便未来在事件循环中复用。

## 7. 安全层：src/security

### 7.1 [src/security/vault.py](src/security/vault.py)

| 类 / 函数 | 作用 |
|---|---|
| `_get_keyring()` | 懒加载系统 keyring 模块。 |
| `VaultEntry` | Vault 中单个 alias/value 记录。 |
| `Vault` | 加密密钥仓库，负责加载、保存、增删与解析引用。 |
| `Vault._load_master_key()` | 从 keyring 或本地 `.key` 文件获取主密钥。 |
| `Vault.load()` | 读取加密 vault 文件并解密。 |
| `Vault.save()` | 将当前数据加密后写回磁盘。 |
| `Vault.list_keys()` | 列出所有别名。 |
| `Vault.set_key()` / `Vault.delete_key()` | 增删密钥。 |
| `Vault.resolve_key_ref()` | 解析 `vault:<alias>` 引用或直接返回明文值。 |
| `Vault._encrypt()` / `Vault._decrypt()` | 基于 AES-256-GCM 的加解密实现。 |

实现策略：
- 主密钥优先放系统 keyring，失败时退回本地 `.key` 文件。
- Vault 内容本身是 JSON，再整体加密，结构简单且易于恢复。
- API key 在 YAML 中以引用形式保存，避免明文散落。

## 8. UI 层：src/ui

### 8.1 [src/ui/main_window.py](src/ui/main_window.py)

| 类 / 函数 | 作用 |
|---|---|
| `MainWindow` | 应用主窗口，负责侧边栏、内容区、创建与选择联动。 |
| `_build_title_bar()` | 顶部标题栏。 |
| `_build_sidebar()` | 侧边栏与 tab 切换区。 |
| `_build_list_panel()` | 构建列表区域和新增按钮。 |
| `_set_active_tab()` | 切换当前显示的内容页。 |
| `refresh_agent_list()` | 重新读取 Agent 列表并刷新 UI。 |
| `refresh_session_list()` | 重新读取 Session 列表并按分组/更新时间排序。 |
| `_on_agent_selected()` / `_on_session_selected()` | 处理侧边栏选择事件。 |
| `_create_agent()` / `_create_session()` | 触发新建流程。 |
| `_on_agents_changed()` / `_on_sessions_changed()` / `_on_session_edited()` | 响应子面板信号并刷新列表。 |
| `_on_session_context_menu()` | 会话右键菜单。 |
| `_rename_session()` / `_edit_session_params()` / `_delete_session()` | 会话重命名、参数编辑和删除。 |
| `_build_placeholder()` | Phase 2 占位页。 |

实现策略：
- 左侧列表与右侧主内容用 `QSplitter` 分离，便于调整宽度。
- 通过 signal/slot 驱动列表刷新，避免直接耦合内部状态。
- 会话列表支持分组标题和上下文菜单，兼顾浏览与管理。
- Team 页先用占位实现，保持导航结构稳定。

### 8.2 [src/ui/agent_panel.py](src/ui/agent_panel.py)

| 类 / 函数 | 作用 |
|---|---|
| `AgentPanel` | Agent 创建、编辑、删除和列表展示面板。 |
| `refresh_agents()` | 从存储加载 Agent 列表。 |
| `on_select_agent()` | 选中列表项后加载表单。 |
| `load_agent_by_id()` | 按 ID 读取配置并灌入表单。 |
| `load_form()` | 把 `AgentConfig` 映射到 UI 控件。 |
| `read_form()` | 从 UI 控件反向组装 `AgentConfig`。 |
| `save_agent()` | 保存当前 Agent 配置到 YAML。 |
| `create_agent()` | 生成默认 Agent 并立即落盘。 |
| `delete_agent()` | 删除 Agent 目录及其文件。 |
| `_section_label()` / `_section_divider()` / `_form_label()` | 复用的界面构件辅助函数。 |

实现策略：
- 表单读取与表单写回分离，避免 UI 与模型混在一起。
- 新建 Agent 时立即创建最小可用 YAML，保证列表与详情视图同步。
- 删除时直接清理目录树，保持文件系统状态一致。

### 8.3 [src/ui/session_panel.py](src/ui/session_panel.py)

| 类 / 函数 | 作用 |
|---|---|
| `ChatWorker` | 独立 QThread，执行异步 Agent 聊天请求并回传流式 chunk。 |
| `SessionPanel` | Session 管理与聊天面板。 |
| `SessionPanel.eventFilter()` | 处理 Enter 发送、Shift+Enter 换行。 |
| `refresh_agents()` | 刷新 Agent 下拉框。 |
| `_sync_create_agents()` | 把 Agent 列表同步给创建 Session 页面。 |
| `refresh_sessions()` | 刷新 Session 下拉框。 |
| `show_create_page()` / `show_chat_page()` | 切换创建页与聊天页。 |
| `_handle_create_requested()` | 根据表单数据创建新 Session。 |
| `send_message()` | 发送用户消息、写入会话并启动流式 worker。 |
| `_start_stream()` | 禁用输入并启动聊天线程。 |
| `_on_chunk()` / `_on_finished()` / `_on_failed()` | 处理流式回复、结束和错误。 |
| `_enable_input()` | 恢复输入控件。 |
| `load_selected_session()` / `load_session_by_id()` | 加载当前或指定 Session。 |
| `_render_session()` | 首屏渲染消息并滚到底部。 |
| `_load_more_messages()` | 顶部滚动时按页加载更早历史。 |
| `edit_session_meta()` | 修改 Session 元数据并写回 YAML。 |
| `delete_session()` | 删除 Session 并刷新 UI。 |

实现策略：
- UI 与后台对话分离，聊天请求放进 QThread，内部再用 `asyncio.run()` 运行异步 LLM 调用。
- 先落盘用户消息，再发起请求，确保即使程序崩溃也保留输入。
- 回复采用 chunk 流式更新，体验接近真实模型输出。
- 通过分页加载历史消息，降低长会话渲染压力。

### 8.4 [src/ui/session_create_panel.py](src/ui/session_create_panel.py)

| 类 / 函数 | 作用 |
|---|---|
| `SessionCreateData` | 创建 Session 时从表单汇总出的数据结构。 |
| `SessionCreateWidget` | Session 创建页。 |
| `set_agents()` | 注入可选 Agent 列表。 |
| `reset()` | 恢复默认表单值。 |
| `_on_create()` | 收集表单并发出创建请求信号。 |

实现策略：
- 独立的创建页避免与聊天页表单状态混杂。
- 通过 signal 把数据交回 `SessionPanel`，保持组件边界清晰。

### 8.5 [src/ui/chat_widget.py](src/ui/chat_widget.py)

| 类 / 函数 | 作用 |
|---|---|
| `DELIM_PAIRS` | LaTeX 分隔符集合。 |
| `_is_escaped()` | 判断某位置的分隔符是否被转义。 |
| `_find_unmatched_open()` | 查找未闭合的数学分隔符位置。 |
| `StreamingBuffer` | 流式缓冲器，在分隔符未闭合时暂缓渲染。 |
| `ChatBubbleWidget` | 单条消息气泡，支持头像、复制按钮、Markdown、代码高亮和 LaTeX。 |
| `set_content()` | 重置整条消息内容并重绘。 |
| `append_chunk()` | 追加流式片段并重绘。 |
| `flush_stream()` | 流结束后做最终渲染。 |
| `set_max_width()` / `resizeEvent()` / `_apply_width_constraints()` | 控制气泡宽度与高度。 |
| `_render()` / `_render_web()` / `_on_web_loaded()` | WebEngine 渲染路径。 |
| `_request_web_height()` / `_apply_web_height()` / `_apply_web_width()` | 通过 JavaScript 回读尺寸并回写 Qt 尺寸。 |
| `_copy_content()` | 复制原始文本。 |
| `_avatar_text()` / `_role_name()` | 角色展示文本。 |
| `_apply_role_style()` | 按角色应用配色与样式。 |
| `ChatRowWidget` | 控制左右对齐的一行消息容器。 |
| `ChatViewWidget` | 可滚动消息列表。 |
| `clear()` | 清空消息。 |
| `add_message()` | 新增消息气泡。 |
| `prepend_message()` | 在顶部插入历史消息。 |
| `update_message()` / `append_to_message()` / `flush_stream_to_message()` | 更新流式消息。 |
| `scroll_to_bottom()` / `_scroll_to_bottom()` | 滚动到底部。 |
| `_on_scroll_value_changed()` | 滚动到顶部时触发分页加载信号。 |
| `_katex_dir()` / `_katex_available()` | 检查本地 KaTeX 资源。 |
| `_katex_shell_html()` | 构造 WebEngine HTML 外壳，注入 KaTeX 和 highlight.js。 |
| `_markdown_to_html()` | Markdown 转 HTML，并在转换前后保护数学块。 |
| `_restore_block()` | 恢复被占位的数学块。 |

实现策略：
- 优先走 WebEngine 富渲染路径，保底用 QTextBrowser。
- 先暂存数学块，再交给 Markdown 处理，避免下划线、星号等符号被误解释。
- 通过 JS 端二次渲染 KaTeX 与高亮，确保数学和代码样式都正确。
- 流式场景使用缓冲器处理未闭合分隔符，减少闪烁和错误渲染。

### 8.6 [src/ui/chat_widget_bak.py](src/ui/chat_widget_bak.py)

| 类 / 函数 | 作用 |
|---|---|
| `ChatBubbleWidget` | 旧版聊天气泡实现。 |
| `ChatRowWidget` | 旧版消息行布局。 |
| `ChatViewWidget` | 旧版消息列表。 |
| `_katex_dir()` / `_katex_available()` / `_katex_shell_html()` | 旧版 KaTeX 渲染外壳。 |
| `_markdown_to_html()` | 旧版 Markdown 处理逻辑。 |

实现策略：
- 这是一个备份版本，保留了更早的流式实现思路。
- 和当前版本相比，它更偏向单一渲染流程，适合作为回退参考。
- 当前主程序使用的是 [src/ui/chat_widget.py](src/ui/chat_widget.py)。

### 8.7 [src/ui/styles.py](src/ui/styles.py)

| 类 / 函数 | 作用 |
|---|---|
| `APP_STYLE` | 全局暗色主题 QSS。 |

实现策略：
- 把窗口、输入框、按钮、列表、滚动条等样式统一管理。
- 使用属性选择器区分主按钮、危险按钮、幽灵按钮和小按钮。
- 与聊天渲染和主窗口配色统一，形成一致的视觉基调。

## 9. 工具层：src/utils

### 9.1 [src/utils/id_gen.py](src/utils/id_gen.py)

| 类 / 函数 | 作用 |
|---|---|
| `new_id()` | 生成 8 位十六进制短 ID。 |

实现策略：
- 直接从 `uuid4()` 截取，简单且足够避免冲突。
- 用于 Agent 与 Session 的本地标识。

### 9.2 [src/utils/logger.py](src/utils/logger.py)

| 类 / 函数 | 作用 |
|---|---|
| `LOG_FORMAT` | 日志格式模板。 |
| `setup_logging()` | 设置基础 logging 配置。 |

实现策略：
- 只做最小日志初始化，避免引入复杂日志框架。
- 统一日志格式便于本地排查。

## 10. 包标记文件

| 文件 | 作用 |
|---|---|
| [src/__init__.py](src/__init__.py) | 包标记文件，无运行时逻辑。 |
| [src/core/__init__.py](src/core/__init__.py) | 包标记文件，无运行时逻辑。 |
| [src/llm/__init__.py](src/llm/__init__.py) | 包标记文件，无运行时逻辑。 |
| [src/storage/__init__.py](src/storage/__init__.py) | 包标记文件，无运行时逻辑。 |
| [src/security/__init__.py](src/security/__init__.py) | 包标记文件，无运行时逻辑。 |
| [src/ui/__init__.py](src/ui/__init__.py) | 包标记文件，无运行时逻辑。 |
| [src/utils/__init__.py](src/utils/__init__.py) | 包标记文件，无运行时逻辑。 |
| [tests/__init__.py](tests/__init__.py) | 测试包标记文件，无运行时逻辑。 |

## 11. Scripts 目录

### 11.1 [scripts/fetch_highlight.py](scripts/fetch_highlight.py)

| 类 / 函数 | 作用 |
|---|---|
| 脚本主体 | 下载 highlight.js 和 GitHub Dark 主题 CSS。 |

实现策略：
- 从 jsDelivr 拉取静态资源并写入 `src/ui/assets/highlight/`。
- 使用 SSL 宽松上下文，方便在不同环境下下载。
- 目标是让聊天渲染在离线环境也可用。

### 11.2 [scripts/fetch_katex.py](scripts/fetch_katex.py)

| 类 / 函数 | 作用 |
|---|---|
| 脚本主体 | 下载 KaTeX 核心脚本、样式与字体。 |

实现策略：
- 将 KaTeX 所需的 CSS、JS 和字体一次性写入本地 assets。
- 让 WebEngine 渲染不依赖运行时网络。

### 11.3 [scripts/fetch_mathjax.py](scripts/fetch_mathjax.py)

| 类 / 函数 | 作用 |
|---|---|
| 脚本主体 | 下载 MathJax 备用资源。 |

实现策略：
- 作为替代数学渲染方案保留。
- 让工程在 KaTeX 不可用时仍有迁移或实验空间。

### 11.4 [scripts/test_markdown_math.py](scripts/test_markdown_math.py)

| 类 / 函数 | 作用 |
|---|---|
| 脚本主体 | 快速验证 `_markdown_to_html()` 是否保留数学分隔符。 |

实现策略：
- 通过构造包含多种数学语法的字符串，直接打印 HTML 和检查结果。
- 适合在不跑完整 GUI 的情况下做渲染前检查。

### 11.5 [scripts/track_claude.py](scripts/track_claude.py)

| 类 / 函数 | 作用 |
|---|---|
| `cmd_record()` | 记录一次 Claude Code token 消耗。 |
| `cmd_stats()` | 显示累计 token 统计。 |
| `cmd_recent()` | 显示最近记录。 |
| `cmd_models()` | 列出已知模型单价。 |
| `main()` | 解析子命令并分发。 |

实现策略：
- 把 TokenTracker 包装成命令行工具，方便手工记录和查看成本。
- 子命令分工清晰，避免单一入口过于复杂。

## 12. Tests 目录

### 12.1 [tests/conftest.py](tests/conftest.py)

| 类 / 函数 | 作用 |
|---|---|
| 脚本主体 | 将 `src` 加入 `sys.path`，让测试可直接导入工程模块。 |

实现策略：
- 以最小方式解决测试导入路径问题。

### 12.2 [tests/test_agent.py](tests/test_agent.py)

| 类 / 函数 | 作用 |
|---|---|
| `test_agent_mock_chat()` | 验证 Agent 可以加载并通过 MockAdapter 返回包含用户输入的回复。 |

实现策略：
- 用临时目录构建最小 Agent 配置，避免依赖真实 API。
- 验证 `Agent.load()` 与 `Agent.chat()` 的主链路。

### 12.3 [tests/test_session.py](tests/test_session.py)

| 类 / 函数 | 作用 |
|---|---|
| `test_session_save_and_load()` | 验证 Session 创建、消息追加、保存与恢复。 |

实现策略：
- 直接检查保存后的消息数量与元数据是否可恢复。
- 覆盖持久化主路径。

### 12.4 [tests/test_storage.py](tests/test_storage.py)

| 类 / 函数 | 作用 |
|---|---|
| `test_filestore_structure()` | 验证运行时目录创建。 |
| `test_yaml_roundtrip()` | 验证 YAML 读写闭环。 |

实现策略：
- 把文件系统布局与 YAML 工具拆开测试，便于定位问题。

### 12.5 [tests/test_db.py](tests/test_db.py)

| 类 / 函数 | 作用 |
|---|---|
| `test_init_db()` | 验证 SQLite 索引文件可初始化。 |

实现策略：
- 只验证 schema 初始化这一条主线，确保补充索引可创建。

### 12.6 [tests/test_parse_state_machine.py](tests/test_parse_state_machine.py)

| 类 / 函数 | 作用 |
|---|---|
| `is_escaped()` | 测试转义规则。 |
| `find_unmatched_open()` | 测试未闭合分隔符检测。 |
| `StreamingBuffer` | 测试流式缓冲策略。 |
| `TestEscapeHandling` | 覆盖反斜杠和美元符号等转义边界。 |
| `TestFindUnmatchedOpen` | 覆盖不同数学分隔符的配对与失配场景。 |
| `TestStreamingBuffer` | 覆盖分块输入、跨块闭合、flush 等流式行为。 |
| `TestMarkdownMathStashing` | 覆盖 Markdown 转换前的数学块保护。 |
| `TestSessionSaveFormat` | 覆盖含数学内容的保存与恢复。 |

实现策略：
- 把 UI 中的 JS 状态机逻辑移植成 Python 版，确保边界条件可单测。
- 重点验证流式输入不会提前渲染未闭合数学内容。
- 把保存格式与数学内容的往返也纳入测试。

### 12.7 [tests/test_latex_streaming_visual.py](tests/test_latex_streaming_visual.py)

| 类 / 函数 | 作用 |
|---|---|
| `SHELL_HTML` | 视觉测试用的独立 HTML 壳。 |
| `_tc()` / `_tc_words()` | 构造字符级或单词级流式测试用例。 |
| `TEST_CASES` | 覆盖常见数学、转义、混合和边界场景。 |
| `LatexStreamingTestWindow` | 交互式测试窗口。 |
| `_load_case()` | 载入测试样例。 |
| `_toggle_run()` / `_start()` / `_stop()` / `_step()` / `_reset()` / `_flush_remaining()` | 控制流式播放。 |
| `_on_speed_changed()` | 调整播放速度。 |
| `_feed_next_chunk()` / `_push_chunk()` | 推送流式 chunk 到 WebEngine 或回退文本框。 |
| `_update_state_display()` / `_on_state()` | 读取前端状态并显示调试信息。 |
| `main()` | 启动独立的可视化测试程序。 |

实现策略：
- 这是一个人工观察用工具，不是自动化单元测试。
- 通过逐字符或逐词喂入，模拟真实 LLM 流式输出。
- 同时展示原始文本、chunk 序列和前端状态，便于排查渲染抖动与状态机问题。

## 13. 运行时目录与静态资源

| 路径 | 作用 |
|---|---|
| [Acts/](Acts/) | 运行时数据根目录。 |
| [Acts/Agents/](Acts/Agents/) | Agent 配置存放目录。 |
| [Acts/Sessions/](Acts/Sessions/) | Session 数据存放目录。 |
| [Acts/Team/](Acts/Team/) | Team 配置存放目录。 |
| [Acts/.vault.enc](Acts/.vault.enc) | 加密后的密钥仓库。 |
| [Acts/index.db](Acts/index.db) | SQLite 辅助索引。 |
| [src/ui/assets/highlight/](src/ui/assets/highlight/) | highlight.js 离线资源。 |
| [src/ui/assets/katex/](src/ui/assets/katex/) | KaTeX 离线资源。 |
| [src/ui/assets/mathjax/](src/ui/assets/mathjax/) | MathJax 备用资源。 |

实现策略：
- 运行时目录与源码分离，避免把用户数据和代码混在一起。
- 静态资源本地化，减少对网络的依赖。

## 14. 代码层面的主要实现模式

### 14.1 数据建模
- 用 dataclass 表达配置、消息、统计和占位实体。
- 通过显式转换函数控制 YAML 和 JSON 的边界。

### 14.2 存储策略
- YAML 作为主数据源，SQLite 仅做补充索引。
- 会话正文使用可追加的行式文本，便于恢复与调试。
- 加密 vault 将密钥明文从配置中剥离。

### 14.3 LLM 调用策略
- 统一接口由 `LLMAdapter` 提供，业务层不关心具体供应商。
- MockAdapter 用于本地启动、测试和无密钥场景。
- OpenAI 兼容适配器同时支持普通请求与流式 SSE。

### 14.4 UI 渲染策略
- 主 UI 由 Qt 控件搭建，渲染层通过 WebEngine 提升 Markdown 与数学体验。
- 流式消息以 chunk 更新，结合缓冲器处理未闭合数学分隔符。
- 采用暗色主题和统一 QSS，保证视觉一致性。

### 14.5 测试策略
- 单元测试覆盖配置、存储、会话、适配器与状态机。
- 视觉测试脚本专门覆盖 LaTeX 流式渲染这类难以纯断言的场景。

## 15. 总结

这个工程的设计核心很清晰：
- 主持久化靠 YAML 文件。
- LLM 调用靠适配器抽象。
- 密钥用 Vault 加密保存。
- UI 聊天支持流式输出与 LaTeX 渲染。
- TokenTracker 负责用量统计与成本估算。
- 测试覆盖了从文件系统到渲染状态机的关键路径。

如果后续继续扩展 Phase 2，优先补齐 Team / Skill / Orchestrator 的模型与调度逻辑，然后再把 UI 面板和测试补上。
