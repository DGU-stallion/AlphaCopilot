# Implementation Plan: AlphaCopilot 前后端整合

## Overview

本计划将 AlphaCopilot 的前后端从骨架状态推进到可运行状态。按依赖顺序执行：先后端路由整合（Task 1-3），再前端类型和 API client（Task 4-8），最后 UI 功能组件和端到端验证（Task 9-14）。

## Tasks

- [x] 1. Refactor research module to expose APIRouter: Create `backend/research/router.py` with `create_research_router()` factory, extract routes from `research/app.py` removing `/api/` prefix, keep `app.py` as standalone fallback. Verify import and route count > 0. (Requirements: 1.1, 1.2)
- [x] 2. Create quant router adapter: Create `backend/quant/router.py` with `create_quant_router()`, fix sys.path for internal imports, register sessions/runs/swarm/alpha/settings/auth/correlation routes, exclude live-trading/channels, wrap in try/except for 503 fallback on missing deps. (Requirements: 3.1, 3.2, 3.3, 3.4, 1.6)
- [x] 3. Rewrite unified backend entry: Rewrite `backend/app.py` with `create_app()` factory, mount research at `/api/research`, quant at `/api/quant`, configure CORS allow-all, add VR_API_KEY auth middleware with loopback bypass, add `/api/health` endpoint, register quant lifecycle hooks. Verify health + research indices endpoints. (Requirements: 1.1, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4)
- [x] 4. Create frontend research types: Create `frontend/src/types/research.ts` with StockQuote, IndexQuote, MarketOverview, MarketEmotion, KlineBar, RadarData, ValuationData, Financials, PortfolioData, ChatMessage, LLMConfig interfaces. Ensure no conflicts with types/agent.ts. Verify tsc passes. (Requirements: 8.1, 8.2, 8.3)
- [x] 5. Create frontend research API client: Create `frontend/src/lib/apiResearch.ts` with typed functions for all research endpoints prefixed `/api/research`, reusing authHeaders from existing api.ts. Verify tsc passes. (Requirements: 4.1, 4.2, 4.4, 4.5)
- [x] 6. Update quant API client paths: Add QUANT_BASE constant to `frontend/src/lib/api.ts`, prefix all request paths and SSE URLs with `/api/quant`. Verify tsc passes and no bare `/sessions` paths remain. (Requirements: 4.1, 4.3, 4.5)
- [x] 7. Migrate research pages to new API client: Update DailyReview, Intel, StockData, Watchlist, Sectors, SectorDetail, Portfolio, MyReports, Notes, Settings pages to import from researchApi. Remove old broken imports. Verify tsc passes. (Requirements: 4.4, 4.5, 9.2)
- [x] 8. Fix remaining TypeScript compilation errors: Categorize and fix all remaining tsc errors (missing types, unused imports, missing packages for tests). Verify `npx tsc --noEmit` exits 0. (Requirements: 4.5, 8.2)
- [x] 9. Verify Vite proxy configuration: Confirm proxy rule works for both `/api/research/*` and `/api/quant/*`, verify quick error on backend down. (Requirements: 9.1, 9.2, 9.3)
- [x] 10. Implement ContextualAgentEntry component: Create `frontend/src/components/common/ContextualAgentEntry.tsx` with placeholder resolution and navigation to `/agent?prefill=...`. (Requirements: 7.1, 7.2, 7.4)
- [x] 11. Handle prefill parameter on Agent page: Read `prefill` searchParam on Agent.tsx mount, populate input without auto-sending, clear param from URL. (Requirements: 7.3)
- [x] 12. Add contextual agent entries to research pages: Add ContextualAgentEntry to StockData, DailyReview, and Intel pages with appropriate prompt templates. (Requirements: 7.1, 7.2)
- [x] 13. Implement session-level guards: Add 404 for non-existent session, 409 for concurrent attempt in quant session routes. (Requirements: 5.6, 5.7)
- [-] 14. End-to-end smoke test: Start backend + frontend, verify sidebar renders, research pages load data, Agent page loads, health endpoint accessible. Commit and push. (Requirements: 1.4, 9.1, 9.2)

## Task Dependency Graph

```json
{
  "waves": [
    {"tasks": [1, 2, 4]},
    {"tasks": [3, 5, 6]},
    {"tasks": [7, 10, 13]},
    {"tasks": [8, 11]},
    {"tasks": [9, 12]},
    {"tasks": [14]}
  ]
}
```

## Notes

- Tasks 1-3 are backend-only and can be verified without the frontend running.
- Tasks 4-8 are frontend-only and can be verified with `npx tsc --noEmit` without the backend.
- Tasks 10-12 depend on the Agent page already loading (Task 8 must pass first).
- Task 13 requires quant router to be working (Task 2) but is independent of frontend tasks.
- Task 14 integrates everything and should be the final step.
