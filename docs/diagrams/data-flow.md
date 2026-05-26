# Data Flow Diagrams

## 1. Chat Message Flow (Streaming)

```
User types message
      │
      ▼
SessionPanel.send_message()
      │
      ├─► Session.add_message("user", content)
      │       └─► Append "[ts] [user] <json>" → content.txt
      │
      ├─► ChatViewWidget.add_message("user", ...)
      │       └─► ChatBubbleWidget.__init__()
      │               └─► _render() → _render_web() → _markdown_to_html() → JS setHtml()
      │
      └─► ChatViewWidget.add_message("assistant", "")
              │
              └─► _start_stream()
                      │
                      ▼
              ChatWorker (QThread)
                  │
                  ▼
              asyncio.run(_task())
                  │
                  ├─► Session.build_context_messages()
                  │       └─► [system_prompt, summary, ...recent_messages]
                  │
                  └─► Agent.chat_stream(messages, session_id)
                          │
                          ▼
                  OpenAICompatAdapter.chat_stream()
                      │  httpx.stream("POST", ...)
                      │  aiter_lines() → SSE parsing
                      │
                      ▼ (each chunk)
                  chunk_received.emit(chunk)
                      │
                      ▼ (main thread)
                  SessionPanel._on_chunk(chunk)
                      │
                      ▼
                  ChatViewWidget.append_to_message(bubble, chunk)
                      │
                      ▼
                  ChatBubbleWidget.append_chunk(chunk)
                      │  _raw_text += chunk
                      │  _render() → _render_web()
                      │      └─► _markdown_to_html(_raw_text)
                      │      └─► JS setHtml(html)
                      │
                      ▼ (stream ends)
                  finished_reply.emit(reply)
                      │
                      ▼
                  SessionPanel._on_finished(reply)
                      ├─► ChatViewWidget.flush_stream_to_message(bubble)
                      ├─► Session.add_message("assistant", reply)
                      ├─► Session.maybe_compress_context()
                      └─► Session.save()
```

## 2. Session Load Flow

```
User selects session in sidebar
      │
      ▼
MainWindow._on_session_selected()
      │
      ▼
SessionPanel.load_session_by_id(session_id)
      │
      ▼
Session.load(session_id, store)
      │
      ├─► read_yaml(SESSION.yaml) → SessionMeta
      └─► parse_content_lines(content.txt) → List[Message]
              │
              ▼
SessionPanel._render_session(session)
      │
      ▼
For each Message:
      ChatViewWidget.add_message(role, content, render_latex=True)
          │
          ▼
      ChatBubbleWidget.__init__(role, content)
          │
          ├─► set_content(content, render_latex=True)
          ├─► _render() → if web not ready: _pending_render = True
          │
          ▼ (when QWebEngineView finishes loading)
      _on_web_loaded()
          └─► _render_web()
              └─► _markdown_to_html(_raw_text) → JS setHtml()
```

## 3. Agent Configuration Flow

```
User edits agent form
      │
      ▼
AgentPanel.save_agent()
      │
      ├─► read_form() → AgentConfig
      │       └─► Reads QLineEdit, QComboBox, QSpinBox values
      │
      ├─► agent_config_to_dict(config) → dict
      ├─► write_yaml(AGENT.yaml, dict)
      │
      └─► Signal: agents_changed
              │
              ▼
      MainWindow._on_agents_changed()
          ├─► Refresh sidebar agent list
          └─► SessionPanel.refresh_agents()
```

## 4. Key Resolution Flow

```
Agent.load(agent_id, store, vault)
      │
      ├─► read_yaml(AGENT.yaml)
      ├─► agent_config_from_dict(data)
      │       └─► config.model.api_key_ref = "vault:openai"
      │
      ├─► vault.resolve_key_ref("vault:openai")
      │       │  if ref.startswith("vault:"):
      │       │      alias = ref.split(":", 1)[1]   # "openai"
      │       │      return vault._data.get(alias, "")
      │       │
      │       └─► returns "sk-abc123..."
      │
      └─► LLMAdapterFactory.create(config.model, api_key)
              └─► OpenAICompatAdapter(base_url, api_key)
```
