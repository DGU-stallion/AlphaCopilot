# Implementation Plan: Architecture Deepening

## Overview

Eliminate five structural debt categories in AlphaCopilot's unified backend. Execution follows dependency order: start with the least-risky isolated change (AgentTuning dataclass), then split the research router, then establish proper packaging (pyproject.toml + import migration), then eliminate standalone entry points, and finally refactor the quant router to fail-fast.

## Tasks

- [x] 1. Extract AgentTuning dataclass from AgentLoop
  - [x] 1.1 Create `backend/quant/agent/tuning.py` with frozen AgentTuning dataclass
    - Define `@dataclass(frozen=True)` with fields: `token_threshold`, `heartbeat_interval_s`, `reasoning_delta_min_interval_s`, `stream_retry_delay_s`, `tool_timeout_seconds`, `goal_max_continuations`
    - Add `from_env_config()` classmethod that reads from `src.config.accessor.get_env_config()` (use current `from src.*` imports for now; will be migrated in task 3)
    - Verify: `cd backend/quant && python -c "from agent.tuning import AgentTuning; t = AgentTuning(token_threshold=100000, heartbeat_interval_s=3.0, reasoning_delta_min_interval_s=0.5, stream_retry_delay_s=2.0, tool_timeout_seconds=300.0, goal_max_continuations=5); print(t)"`
    - _Requirements: 5.1, 5.2_

  - [x] 1.2 Refactor `backend/quant/agent/loop.py` to accept and use AgentTuning
    - Add `tuning: AgentTuning` parameter to `AgentLoop.__init__`
    - Replace all calls to `_token_threshold()`, `_heartbeat_interval_s()`, `_reasoning_delta_min_interval_s()`, `_stream_retry_delay_s()`, `_tool_timeout_seconds()`, `_goal_max_continuations()` with `self._tuning.<field>`
    - Remove the `_override()` function and all six module-level accessor functions
    - Remove the second `from src.config.accessor import get_env_config` import at module top (keep only the one needed by `from_env_config`)
    - Verify: `cd backend/quant && python -c "from agent.loop import AgentLoop; print('OK — no _override or accessor functions')"`
    - _Requirements: 5.3, 5.4, 5.5, 5.6_

  - [x] 1.3 Update all AgentLoop instantiation sites to pass AgentTuning
    - Find all places that construct `AgentLoop(...)` (likely in session/run creation code) and add `tuning=AgentTuning.from_env_config()`
    - Verify: `cd backend/quant && python -m pytest tests/ -x -q --timeout=30 2>&1 | head -30` (existing tests still pass)
    - _Requirements: 5.3, 5.7_

  - [x] 1.4 Write property test for AgentTuning injection (Property 7)
    - **Property 7: AgentTuning injection respected by AgentLoop**
    - Create `backend/quant/tests/test_agent_tuning_prop.py`
    - Use Hypothesis to generate random valid tuning values, construct AgentLoop with those values, verify all values are used (not env config fallback)
    - Verify: `cd backend/quant && python -m pytest tests/test_agent_tuning_prop.py -v`
    - **Validates: Requirements 5.3, 5.4, 5.7**

- [x] 2. Checkpoint — AgentTuning extraction complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Split Research Router into sub-modules
  - [x] 3.1 Create `backend/research/caches.py` with ResearchCaches dataclass
    - Define `@dataclass` with fields: `pct_cache`, `ann_cache`, `fin_cache`, `dc_cache` (all `dict` with `field(default_factory=dict)`)
    - Move `_validate()` and `_cached()` helper functions here as module-level utilities
    - Verify: `cd backend/research && python -c "from caches import ResearchCaches; c = ResearchCaches(); print(c)"`
    - _Requirements: 3.5_

  - [x] 3.2 Create `backend/research/routes/__init__.py` and four route sub-modules
    - Create `backend/research/routes/__init__.py` (empty or re-exports)
    - Create `backend/research/routes/chat.py` — `register_chat_routes(router, *, caches)` with `/chat` endpoint
    - Create `backend/research/routes/portfolio.py` — `register_portfolio_routes(router, *, caches)` with `/portfolio`, `/portfolio/holding`, `/portfolio/close`, `/portfolio/refresh` endpoints
    - Create `backend/research/routes/market_data.py` — `register_market_data_routes(router, *, caches)` with all `/indices`, `/quote`, `/valuation/*`, `/kline`, `/finance`, `/info`, `/disclosure`, `/market/*`, `/global/*`, and signal endpoints (`/margin`, `/block-trade`, `/holders`, `/dividend`, `/fund-flow`, `/dragon-tiger`, `/lockup`, `/blocks`, `/hot-concepts`, `/investor-qa`, `/industry`)
    - Create `backend/research/routes/reports_news.py` — `register_reports_news_routes(router, *, caches)` with `/myreports`, `/myreports/file/{rid}`, `/myreports/{rid}`, `/radar`, `/radar/refresh`, `/news`, `/reports`, `/announcements`, `/financials`
    - Move Pydantic models (`ChatReq`, `HoldingIn`, `CloseIn`, `ReportIn`, `LLMConfig`) to a shared `backend/research/models.py` or keep in respective route files
    - Verify: `cd backend/research && python -c "from routes.chat import register_chat_routes; from routes.portfolio import register_portfolio_routes; from routes.market_data import register_market_data_routes; from routes.reports_news import register_reports_news_routes; print('All route modules import OK')"`
    - _Requirements: 3.1, 3.2_

  - [x] 3.3 Refactor `backend/research/router.py` to assemble from sub-modules
    - Replace inline route definitions with calls to `register_chat_routes`, `register_portfolio_routes`, `register_market_data_routes`, `register_reports_news_routes`
    - Accept optional `caches: ResearchCaches | None = None` parameter
    - Keep the `/health` endpoint inline in the assembler
    - Verify: `cd backend && python -c "from research.router import create_research_router; r = create_research_router(); routes = [(route.methods, route.path) for route in r.routes]; print(f'{len(routes)} routes registered'); assert len(routes) >= 30"`
    - _Requirements: 3.3, 3.4_

  - [x] 3.4 Write property test for route set preservation (Property 1)
    - **Property 1: Research route set preservation**
    - Create `backend/research/tests/test_route_preservation_prop.py`
    - Capture the baseline route set from the current monolithic router, compare against the split router
    - Verify: `cd backend/research && python -m pytest tests/test_route_preservation_prop.py -v`
    - **Validates: Requirements 3.4**

  - [x] 3.5 Write property test for cache isolation (Property 2)
    - **Property 2: Cache isolation via injection**
    - Create `backend/research/tests/test_cache_isolation_prop.py`
    - Use Hypothesis to generate random stock codes and cache entries, inject custom ResearchCaches, verify no global state mutation
    - Verify: `cd backend/research && python -m pytest tests/test_cache_isolation_prop.py -v`
    - **Validates: Requirements 3.5, 3.6**

- [x] 4. Checkpoint — Research router split complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Eliminate sys.path hacks — create pyproject.toml and migrate imports
  - [x] 5.1 Create `backend/pyproject.toml` declaring quant and research as packages
    - Add `[project]` with name `alphacopilot-backend`, version `0.2.0`, requires-python `>=3.11`
    - Add `[tool.setuptools.packages.find]` with `where = ["."]`, `include = ["quant*", "research*"]`
    - Add `[tool.setuptools.package-data]` for non-Python files
    - Verify: `cd backend && pip install -e . && python -c "import quant; import research; print('Package install OK')"`
    - _Requirements: 2.5_

  - [x] 5.2 Migrate all `from src.*` imports in quant module to `from quant.*`
    - Replace `from src.agent.*` → `from quant.agent.*`
    - Replace `from src.config.*` → `from quant.config.*`
    - Replace `from src.providers.*` → `from quant.providers.*`
    - Replace `from src.tools.*` → `from quant.tools.*`
    - Replace `from src.core.*` → `from quant.core.*`
    - Replace `from src.api.*` → `from quant.api.*` (Note: `src/api/` maps to files currently at `quant/` level or in a subdirectory — verify actual file locations)
    - Replace `from src.goal.*` → `from quant.goal.*` (or wherever goal module lives)
    - Replace `from src.ui_services` → `from quant.ui_services`
    - Replace `from src.preflight` → `from quant.preflight`
    - Also update `from quant/agent/tuning.py` (created in task 1) to use `from quant.config.accessor` instead of `from src.config.accessor`
    - Verify: `cd backend && python -c "from quant.agent.loop import AgentLoop; from quant.router import create_quant_router; print('Quant imports OK via package')"` 
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 5.3 Migrate `from backtest.*` imports to `from quant.backtest.*`
    - Find all `from backtest.` or `import backtest.` within quant code
    - Replace with `from quant.backtest.*` absolute imports
    - Verify: `cd backend && python -c "from quant.backtest.engines.base import BacktestEngine; print('Backtest import OK')"`
    - _Requirements: 2.4_

  - [x] 5.4 Remove all `sys.path.insert` / `sys.path.append` from production code
    - Remove from `backend/app.py` (the research dir and quant dir sys.path hacks)
    - Remove from `backend/quant/router.py` (the `_quant_dir` sys.path hack)
    - Remove from any other production files that have sys.path manipulation
    - Do NOT remove from test conftest.py yet (handled in next sub-task)
    - Verify: `cd backend && grep -r "sys.path.insert\|sys.path.append" --include="*.py" | grep -v ".venv" | grep -v __pycache__ | grep -v conftest | grep -v tests` (should return empty)
    - _Requirements: 2.1_

  - [x] 5.5 Update test conftest.py to rely on installed package
    - Remove any `sys.path.insert` calls from `conftest.py` files
    - Ensure tests run via `pip install -e .` package resolution
    - Verify: `cd backend && python -m pytest quant/tests/ -x -q --timeout=30 2>&1 | head -30`
    - _Requirements: 2.6, 2.7_

- [x] 6. Checkpoint — Import migration complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Eliminate standalone entry points
  - [x] 7.1 Convert `backend/research/app.py` to deprecation stub
    - Remove `FastAPI()` instantiation, middleware, and route registration
    - Replace with deprecation warning message pointing to `backend/app.py`
    - If run as `__main__`, print deprecation message and `raise SystemExit(1)`
    - Verify: `cd backend/research && python -c "import subprocess, sys; r = subprocess.run([sys.executable, 'app.py'], capture_output=True, text=True); assert r.returncode == 1; assert 'deprecated' in r.stderr.lower() or 'deprecated' in r.stdout.lower()"`
    - _Requirements: 1.2, 1.4_

  - [x] 7.2 Convert `backend/quant/api_server.py` to deprecation stub
    - Remove `FastAPI()` instantiation (`app = FastAPI(...)`) and middleware registration
    - Keep `serve_main()` function as a thin wrapper that delegates to the unified app (or prints deprecation warning)
    - Keep re-exports for test compatibility (add `# TODO: remove once tests migrated` comment)
    - If run as `__main__`, print deprecation message and `raise SystemExit(1)`
    - Verify: `cd backend/quant && python -c "import subprocess, sys; r = subprocess.run([sys.executable, 'api_server.py'], capture_output=True, text=True); assert r.returncode == 1; assert 'deprecated' in r.stderr.lower() or 'deprecated' in r.stdout.lower()"`
    - _Requirements: 1.3, 1.5_

  - [x] 7.3 Clean up `backend/app.py` — remove fallback router and sys.path hacks
    - Remove the `try/except` block around quant router that creates a fallback router
    - Import `create_quant_router` directly (fail-fast)
    - Remove `sys.path.insert` for research and quant directories (rely on installed package)
    - Ensure single CORS and single auth middleware
    - Verify: `cd backend && python -c "from app import create_app; a = create_app(); print(f'App created with {len(a.routes)} routes')"`
    - _Requirements: 1.1, 1.6, 1.7, 4.4_

  - [x] 7.4 Write unit test for entry point deprecation
    - Create `backend/tests/test_entry_point_deprecation.py`
    - Test that running `research/app.py` and `quant/api_server.py` as `__main__` produces `SystemExit(1)` and deprecation message
    - Verify: `cd backend && python -m pytest tests/test_entry_point_deprecation.py -v`
    - _Requirements: 1.4, 1.5_

- [x] 8. Checkpoint — Entry points consolidated
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Quant Router fail-fast refactoring
  - [x] 9.1 Refactor `backend/quant/router.py` — core deps fail-fast, optional deps feature-flagged
    - Remove all `try/except` wrappers around core route imports (sessions, runs)
    - Import core routes at top level: `from quant.api.sessions_routes import register_sessions_routes` etc.
    - Define `OPTIONAL_ROUTE_MODULES` dict mapping module names to feature flag env vars
    - For optional deps: check feature flag first, then try import with warning on failure
    - Remove the catch-all `/{path:path}` fallback route entirely
    - Remove the session guards fallback logic
    - Verify: `cd backend && python -c "from quant.router import create_quant_router; r = create_quant_router(); routes = [(m, route.path) for route in r.routes for m in (route.methods or set())]; print(f'{len(routes)} quant routes registered, no catch-all'); assert not any('{path:path}' in path for _, path in routes)"`
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [x] 9.2 Write property test for core dep fail-fast (Property 3)
    - **Property 3: Core dependency fail-fast**
    - Create `backend/quant/tests/test_quant_router_prop.py`
    - Mock core deps as unimportable, assert `create_quant_router()` raises ImportError
    - Verify: `cd backend && python -m pytest quant/tests/test_quant_router_prop.py::test_core_dep_fail_fast -v`
    - **Validates: Requirements 4.1**

  - [x] 9.3 Write property test for no catch-all route (Property 4)
    - **Property 4: No catch-all route regardless of optional dep availability**
    - In same test file `backend/quant/tests/test_quant_router_prop.py`
    - Use Hypothesis to generate random subsets of optional deps as unavailable, verify no `/{path:path}` route
    - Verify: `cd backend && python -m pytest quant/tests/test_quant_router_prop.py::test_no_catch_all -v`
    - **Validates: Requirements 4.2, 4.3**

  - [x] 9.4 Write property test for feature flag (Property 5)
    - **Property 5: Feature flag prevents import attempt**
    - In same test file
    - Mock imports and set flags to "0", verify import not attempted
    - Verify: `cd backend && python -m pytest quant/tests/test_quant_router_prop.py::test_feature_flag_prevents_import -v`
    - **Validates: Requirements 4.5**

  - [x] 9.5 Write property test for deterministic routes (Property 6)
    - **Property 6: Deterministic route set for a given configuration**
    - In same test file
    - Use Hypothesis to generate random dep/flag configs, call create_quant_router() twice, assert route sets equal
    - Verify: `cd backend && python -m pytest quant/tests/test_quant_router_prop.py::test_deterministic_routes -v`
    - **Validates: Requirements 4.6**

- [x] 10. Final checkpoint — All refactoring complete
  - Ensure all tests pass, ask the user if questions arise.
  - Run full test suite: `cd backend && python -m pytest -x -q --timeout=60`
  - Verify no `sys.path.insert` in production code: `grep -r "sys.path.insert" --include="*.py" | grep -v .venv | grep -v __pycache__ | grep -v tests`
  - Verify no `from src.*` imports: `grep -r "from src\." --include="*.py" backend/quant/ | grep -v .venv | grep -v __pycache__`
  - Verify app starts cleanly: `cd backend && python -c "from app import create_app; app = create_app(); print('✅ Unified app starts successfully')"`

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Execution order is dependency-driven: AgentTuning (isolated) → Research split (isolated) → pyproject.toml + imports (enables everything) → Entry point elimination (depends on package imports) → Quant router fail-fast (depends on both)
- The `from src.*` → `from quant.*` migration (task 5.2) is the largest change by file count — use automated find-and-replace

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1"] },
    { "id": 1, "tasks": ["1.2", "3.2"] },
    { "id": 2, "tasks": ["1.3", "3.3"] },
    { "id": 3, "tasks": ["1.4", "3.4", "3.5"] },
    { "id": 4, "tasks": ["5.1"] },
    { "id": 5, "tasks": ["5.2", "5.3"] },
    { "id": 6, "tasks": ["5.4"] },
    { "id": 7, "tasks": ["5.5"] },
    { "id": 8, "tasks": ["7.1", "7.2"] },
    { "id": 9, "tasks": ["7.3"] },
    { "id": 10, "tasks": ["7.4"] },
    { "id": 11, "tasks": ["9.1"] },
    { "id": 12, "tasks": ["9.2", "9.3", "9.4", "9.5"] }
  ]
}
```
