# AI Chatbot Plan

## Goal
Build and stabilize a full-stack chatbot app with authentication, protected chat, streaming responses, persistent history, and thread management, then publish to GitHub.

## Plan
1. Scaffold project structure for backend and frontend.
2. Implement backend foundation:
- FastAPI app setup
- configuration and environment loading
- database session and models
- API router organization
3. Implement authentication:
- Google OAuth sign-in
- email/password login
- email/password signup with domain restriction
- JWT httpOnly cookie session
- protected auth dependency and /me endpoint
4. Implement chat core:
- chat streaming endpoint
- message persistence to database
- history loading endpoint
5. Implement thread management:
- create thread
- list threads on login
- rename thread
- delete thread
- auto-name thread from first user message
6. Implement frontend:
- login page with Google and email/password
- signup mode without breaking existing login flow
- protected /chat route
- thread sidebar and chat UI
- streaming response rendering
7. Debug and stabilize integration:
- fix OAuth/session issues
- fix model access/config issues
- fix duplicate frontend component definitions
- fix duplicate backend function definitions
- fix schema drift (missing messages.thread_id)
- add startup schema reconciliation for missing thread_id/index
8. Validate end-to-end behavior:
- backend health check
- frontend build/type-check
- login/signup flow
- chat streaming flow
- thread CRUD flow
9. Prepare repository for GitHub:
- initialize git
- ensure safe .gitignore entries
- commit on main
- add remote
- push to GitHub

## Non-Functional Guardrails
- Do not break working login/chat behavior while adding features.
- Keep secrets and local artifacts out of version control.
- Keep backend and frontend runnable independently during debugging.

## Current Completion State
- All core features implemented and verified.
- Signup added without removing existing functionality.
- Network/chat issues fixed by backend schema reconciliation and process cleanup.
- Code pushed successfully to GitHub.

## Status Matrix (Against Requested Projects)
- Project 1: Done
- Project 2: Done
- Project 3: Done
- Project 4: Done (previous-5 memory window enforced)
- Project 5: Done
- Project 6: Not started
- Project 7: Not started (dependencies/scaffolding only)
- Project 8: Not started
- Agents track (LangChain agents, Tic-Tac-Toe, MCP example, n8n agents): Not started

## Execution Roadmap (Proceeding From Current State)

### Phase A: Close Core Gaps (Project 1 + Project 4)
Scope:
- Refactor chat orchestration to LangChain-first flow (prompt template + chain wrapper)
- Enforce memory window = previous 5 conversations per thread

Deliverables:
- LangChain chain module under backend app AI chains package
- Memory policy module under backend app AI memory package
- Chat service integration with configurable memory window defaulted to 5

Acceptance Criteria:
- Every assistant response is generated through LangChain chain invocation
- Only last 5 conversation pairs (or equivalent bounded context policy) are sent to model
- Existing streaming and thread behavior remain unchanged from user perspective

### Phase B: Multimodal Inputs + Image Generation (Project 5 + Project 6)
Scope:
- Add attachment ingestion in chat UI and backend (images, videos, tables, formulas/code docs)
- Add Gemini image-generation action from chat

Deliverables:
- Upload API endpoints and storage policy (size/type validation)
- Frontend attachment picker + preview + send pipeline
- Image generation API route and UI action button/cards

Acceptance Criteria:
- User can upload at least one file per message and see attachment metadata in chat
- AI can generate an image and return renderable image output in chat
- Validation rejects unsupported file types and oversized files with clear messages

### Phase C: RAG + Data Q&A (Project 7 + Project 8)
Scope:
- PDF upload and RAG chat using ChromaDB + OpenAI text-embedding-3-large
- Natural-language DB Q&A (NL-to-SQL with guarded execution)
- Excel/GSheet Q&A as tabular knowledge sources
- Rule-based image extraction/compliance checks

Deliverables:
- Document ingestion pipeline (chunking, embeddings, vector write/read)
- Retrieval-augmented answer route with citations/snippets
- SQL agent/service with allowlist and safety constraints
- Spreadsheet ingestion adapter and question endpoint
- Image rule-check endpoint with structured pass/fail report

Acceptance Criteria:
- User can upload PDF and ask grounded questions with retrieved context
- User can ask NL DB questions and receive validated query results
- User can ask questions against Excel/GSheet data
- Rule-check endpoint returns deterministic structured output

### Phase D: Agents Track (LangChain Agents, MCP, n8n)
Scope:
- Build foundational LangChain agent patterns
- Implement Tic-Tac-Toe game-playing agent
- Add one MCP-backed agent example
- Add n8n-based agent workflow example

Deliverables:
- Agent base framework and tool registry
- Tic-Tac-Toe agent route/demo script
- MCP integration example with one practical tool
- n8n flow definition and integration notes

Acceptance Criteria:
- Each agent module has runnable demo path and expected-output sample
- MCP example shows end-to-end tool invocation from agent
- n8n flow runs and returns usable results to app/backend

## Cross-Phase Constraints
- Preserve existing auth, thread CRUD, and streaming chat behavior.
- Keep secrets only in env files and never in repository commits.
- Ship each phase behind stable API contracts to avoid frontend regressions.

## Recommended Next Action
- Start Phase A implementation first (LangChain-first chat orchestration + strict memory-of-5 policy), then run regression checks on login, thread CRUD, and streaming.
