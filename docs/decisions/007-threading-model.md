# 007: Threading Model (QThread + asyncio)

**Date:** 2025 (Phase 1 MVP)

**Status:** Accepted

## Context

LLM API calls are I/O-bound (HTTP requests) that may take seconds to minutes. Running them on the Qt main thread would freeze the GUI. The app needs a non-blocking approach.

## Decision

Use a **QThread + asyncio** hybrid: each chat request runs `asyncio.run()` inside a dedicated `QThread`.

```
Main Thread (Qt event loop)        ChatWorker (QThread)
├── UI updates                     └── asyncio.run(_task())
├── Signal/slot dispatch                ├── Agent.chat_stream()
└── Event processing                    │   └── LLMAdapter.chat_stream()
                                        │       └── SSE aiter_lines()
                                        ├── Emit chunk_received
                                        ├── Session.add_message()
                                        └── Emit finished_reply / failed
```

## Rationale

- **Qt main thread stays responsive**: UI updates, scrolling, input handling are never blocked
- **asyncio for I/O**: `httpx.AsyncClient` with async generators is the natural pattern for SSE streaming
- **Signal/slot for thread safety**: Qt signals are thread-safe — `chunk_received` and `finished_reply` are emitted from worker thread and safely delivered to main thread slots
- **QThread over asyncio-only**: Qt applications need a `QApplication` event loop; mixing `asyncio` event loop with Qt event loop directly causes issues (see Consequences)

## ChatWorker Implementation

```python
class ChatWorker(QThread):
    chunk_received = pyqtSignal(str)
    finished_reply = pyqtSignal(str)
    failed = pyqtSignal(str)

    def run(self):
        reply = asyncio.run(self._task())
        self.finished_reply.emit(reply)
```

## Consequences

- Each chat request creates a new `QThread` and `asyncio` event loop — acceptable for interactive use (not high-throughput)
- Cannot cancel in-progress requests cleanly (thread cancellation in Python is limited)
- `asyncio.run()` creates a fresh event loop per request, so no event loop conflicts
- Token usage is recorded in `finally` block of `Agent.chat_stream()`, ensuring it's captured even on error
