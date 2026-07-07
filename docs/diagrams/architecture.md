# Architecture

```mermaid
flowchart TB
    subgraph Inputs
        RSS["services/job-monitor/\nRSS webhook push"]
        FL_IN["Flutter Desktop\nmanual URL input"]
    end

    subgraph "Career Agent"
        API["FastAPI Backend\nJSON API for Flutter"]
        Workers["Background Workers\nAnalysisWorker · CVWorker · CoverWorker\nasyncio.Queue + LLMSemaphore"]
        Tools["Tools\ncv_fetch · cv_analyze · cv_generate · cv_cover"]
        LLM["LLM Client (switchable via LLM_PROVIDER)\nClaude Sonnet 4.6 · Ollama · Claude CLI ($0)"]
        TG["Telegram\npush notifications only\n(removed in Phase D)"]
    end

    subgraph "Flutter Desktop"
        Inbox["Inbox — vacancy list\nstatus polling · unread badge"]
        Detail["Detail — analysis · CV · Cover · Activity"]
        Settings["Settings — provider · model · effort"]
    end

    subgraph "services/"
        JDP["jd-parser/\nURL → Markdown\nHTTP POST /parse"]
        PDF["pdf/\nMarkdown → PDF\nHTTP POST /render"]
    end

    subgraph Storage
        DB[("SQLite\nvacancies · llm_usage · user_settings")]
        FS["Filesystem\nvacancies/ — JD · analysis · CV · Cover"]
    end

    RSS --> Workers
    FL_IN --> API
    API --> Workers
    Workers --> Tools
    Tools --> LLM
    Tools --> JDP
    Tools --> PDF
    Tools --> DB & FS
    API --> DB
    Workers -.->|push notification| TG
    Inbox <-->|polling| API
    Detail <-->|on demand| API
    Settings <-->|PATCH /api/config| API
```

| Layer | Tech |
|-------|------|
| AI | Claude Sonnet 4.6 (default) · Ollama (`LLM_PROVIDER=ollama_api`) · Claude CLI (`LLM_PROVIDER=claude_cli`, $0) · prompt caching |
| UI | Flutter Desktop (primary) · Web tracker (FastAPI + HTMX, read-only) |
| Backend | FastAPI — JSON endpoints for Flutter + background worker orchestration |
| Workers | asyncio.Queue — AnalysisWorker · CVWorker · CoverWorker; shared LLMSemaphore |
| HTTP | httpx async (backend) · http (Flutter) |
| Storage | SQLite + filesystem |
| Deploy | Docker Compose — career-agent · services/ |
