# User Journey

New jobs arrive automatically via RSS. The user only makes decisions — approve or skip.
Manual URL input is a fallback, not the default.

```mermaid
flowchart LR
    M["services/job-monitor/\nRSS auto-discovery"] -->|"pushes new vacancy"| A
    A["🔔 Telegram\nNew job at X — Analyze?"]
    A -->|✅ Yes| C["Deep JD Analytics\nScore · Verdict · Barriers"]
    C --> D["Telegram\nGenerate CV?"]
    D -->|📄 Yes| E["AI drafts CV\n+ self-review pass"]
    E --> F["User approves\nvia Telegram"]
    F --> G["📎 PDF delivered"]
    G --> H["Telegram\nCover letter?"]
    H -->|✉️ Yes| I["Cover letter\ndelivered"]
    A -->|❌ Skip| Z["Archived"]
    U["Manual option\nTelegram URL / JD.md drop"] -.->|fallback| A
```

**The user's only job:** approve or skip. Everything else runs automatically.
