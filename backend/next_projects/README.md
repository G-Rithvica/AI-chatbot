# Next Projects Workspace (Isolated)

This folder contains standalone scaffolding for upcoming roadmap work:
- Project 6: image generation
- Project 7: RAG pipeline
- Project 8: data Q&A
- Agents track: LangChain/MCP/n8n examples

Design rules:
- No imports from current production routes/services unless explicitly needed later.
- No router registration in current app yet.
- No behavior changes to existing auth/chat/thread/attachments flow.

Integration plan:
1. Build and test features here.
2. Add contract tests.
3. Wire one feature at a time behind feature flags when ready.
