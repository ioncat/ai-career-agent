# Architecture

```mermaid
flowchart TB
    subgraph Inputs
        RSS["services/job-monitor/\nwebhook push"]
        User["User · Telegram / PWA"]
    end

    subgraph "Career Agent"
        TG["Notification Channel\nTelegram (primary) · PWA"]
        RT["Router\nPydanticAI"]
        Tools["Tools\ncv_fetch · cv_analyze · cv_generate · cv_cover"]
        LLM["LLM Client\nClaude Sonnet 4.6\nprompt caching + extended thinking"]
        Web["Web Tracker\nFastAPI + HTMX"]
    end

    subgraph "services/"
        JDP["jd-parser/\nURL → Markdown\nHTTP POST /parse"]
        PDF["pdf/\nMarkdown → PDF\nHTTP POST /render"]
    end

    subgraph Storage
        DB[("SQLite\nvacancy metadata · llm_usage")]
        FS["Filesystem\nvacancies/ — JD · analysis · CV · cover"]
    end

    RSS --> RT
    User --> TG --> RT
    RT --> Tools
    Tools --> LLM
    Tools --> JDP
    Tools --> PDF
    Tools --> DB & FS
    Web --> DB
```

| Layer | Tech |
|-------|------|
| AI | Claude Sonnet 4.6 · PydanticAI · prompt caching (profile + all phase prompts) |
| UI | Telegram (aiogram 3.x) · Web tracker (FastAPI + HTMX) |
| HTTP | httpx async |
| Storage | SQLite + filesystem |
| Deploy | Docker Compose — career-agent · services/ |
