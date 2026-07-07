# User Journey

New jobs arrive automatically via RSS and are analyzed in the background. The user only makes decisions — approve or skip — inside the Flutter Desktop app.

```mermaid
flowchart LR
    RSS["services/job-monitor/\nRSS auto-discovery"] -->|"webhook push"| AW["AnalysisWorker\nauto Phase 1+2"]
    AW -->|"analysis ready"| Inbox["Flutter Inbox\nfit score · recommendation · barriers"]

    Inbox -->|"open vacancy"| Detail["Flutter Detail\nfull analysis · CV · Cover · Activity"]

    Detail -->|"✅ Generate CV"| CVW["CVWorker\nPhase 3+3.5"]
    CVW --> CVView["CV preview in Flutter\n+ Download PDF"]

    Detail -->|"✉️ Generate Cover"| CovW["CoverWorker\nPhase 4"]
    CovW --> CovView["Cover preview in Flutter\n+ Download PDF"]

    Detail -->|"❌ Skip / Decline"| Arc["Archived"]

    Manual["Manual option\nURL paste in Flutter"] -.->|fallback| AW
```

**The user's only job:** review the analysis, approve or skip. Everything else runs automatically.
