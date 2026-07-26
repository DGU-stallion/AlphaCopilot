# Handoff: Architecture Deepening — Fix Runtime Blockers

## Next Session Focus

新会话需要解决阻止后端启动的两个 runtime 问题，使 `cd backend && python -m uvicorn app:app --port 8900` 能成功启动。

---

## Project Context

- **Repo**: `/Users/a19150/Project/AlphaCopilot`
- **Spec**: `.kiro/specs/architecture-deepening/` (requirements.md, design.md, tasks.md)
- **All 33 spec tasks are marked complete** in tasks.md — the structural refactoring is done at file level but has runtime integration issues.
- **Steering file**: `.kiro/steering/command-execution-safety.md` — rules to avoid Kiro's terminal-hang bug.

---

## Current State

### What's Done (spec tasks 1–10, all completed)

1. `AgentTuning` frozen dataclass extracted → `backend/quant/agent/tuning.py`
2. `AgentLoop` refactored to accept `tuning: AgentTuning` parameter
3. Research router split into 4 sub-modules under `backend/research/routes/`
4. `ResearchCaches` injectable dataclass at `backend/research/caches.py`
5. `pyproject.toml` at `backend/` declares `quant*` and `research*` packages
6. `from src.*` → `from quant.*` migration complete in quant module
7. `from backtest.*` → `from quant.backtest.*` migration complete
8. `sys.path.insert/append` removed from all production code
9. `research/app.py` and `quant/api_server.py` converted to deprecation stubs
10. `backend/app.py` cleaned — fail-fast quant router, no fallback
11. `quant/router.py` refactored — core deps fail-fast, optional deps feature-flagged
12. Property tests written and passing for Properties 1–7
13. Research internal bare imports fixed (`import astock` → `import research.astock as astock`)

### What's Broken (2 blockers for runtime)

#### Blocker 1: `quant/api/` package does NOT exist

`quant/router.py` imports:
```python
from quant.api.sessions_routes import register_sessions_routes
from quant.api.runs_routes import register_runs_routes
from quant.api.settings_routes import register_settings_routes
from quant.api.auth_routes import register_auth_routes
from quant.api.system_routes import register_system_routes
```

But `backend/quant/api/` directory was never created. The route registration functions were originally defined inline in `quant/api_server.py` (now a deprecation stub that only re-exports symbols).

**What needs to happen**:
- Create `backend/quant/api/__init__.py`
- Create individual route files (`sessions_routes.py`, `runs_routes.py`, `settings_routes.py`, `auth_routes.py`, `system_routes.py`, `swarm_routes.py`, `alpha_routes.py`, `scheduled_routes.py`, `channels_routes.py`, `live_routes.py`, `uploads_routes.py`, `qveris_routes.py`)
- Each file must define a `register_<name>_routes(router)` function that attaches the FastAPI endpoints
- Also need `quant/api/security.py`, `quant/api/models.py`, `quant/api/helpers.py`, `quant/api/state.py` (these are referenced in `api_server.py` re-exports)

**Investigation approach**: The original code (before this refactoring) had these routes defined somewhere. Check git history: `git log --oneline --all -- backend/quant/api_server.py` to find the pre-refactoring state. The deprecation stub's re-exports (`from quant.api.sessions_routes import ...`) tell you what each module must export. These `quant.api.*` paths were migrated from `from src.api.*` — meaning the original files lived at a path that resolved as `src.api.*` when `sys.path` pointed into `quant/`. This means there might be an `api/` subdirectory that was renamed or moved, OR the route code was embedded in `api_server.py` itself and needs extraction.

#### Blocker 2: Research module may have remaining bare imports

Fixed the main ones (`astock`, `gstock`, `market`, `chat`, `cli_runtime`, `portfolio`, `myreports`, `newsradar`), but there could be deeper transitive bare imports. Specifically:
- `research/chat.py` may call internal functions using bare module references
- `research/portfolio.py`, `research/market.py` may have `from X import Y` where X is research-internal

**Quick validation**: 
```bash
cd backend && .venv/bin/python -c "from research.router import create_research_router; r = create_research_router(); print(len(r.routes))"
```

---

## Key Files to Read

| File | Purpose |
|------|---------|
| `backend/quant/router.py` | Quant router — imports from `quant.api.*` |
| `backend/quant/api_server.py` | Deprecation stub with all re-exports — shows what `quant.api.*` modules must export |
| `backend/research/router.py` | Research assembler — imports sub-modules |
| `backend/research/routes/*.py` | Route sub-modules (already use `research.*` paths) |
| `backend/app.py` | Unified entry point |
| `.kiro/specs/architecture-deepening/design.md` | Architecture target state |
| `.kiro/steering/command-execution-safety.md` | Rules to avoid terminal-hang bug |

---

## Kiro Terminal Bug (Important)

Kiro has a known bug where `execute_bash` commands timeout even though they completed (GitHub issues #53, #1734, #4909, #6005 at https://github.com/kirodotdev/Kiro). Mitigations:
- Use `grep_search` / `read_file` tools instead of bash grep/find
- Use `ast.parse` for syntax validation instead of full import verification
- Add `timeout=30000` to execute_bash calls
- If command shows output + shell prompt in the "timed out" response, treat it as successful

---

## Suggested Skills

- **`implement`** — The primary skill for this session. The work is implementation: creating the `quant/api/` package with route files, and fixing remaining research imports.
- **`diagnosing-bugs`** — If the research module still has import failures after the obvious fixes, use this to trace the import chain.
- **`codebase-design`** — If decisions are needed about how to structure `quant/api/` (what goes in each file, what the register functions look like).

---

## Acceptance Criteria for Next Session

1. `cd backend && .venv/bin/python -c "from app import create_app; app = create_app(); print(len(app.routes))"` succeeds
2. `cd backend && .venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8900` starts without error
3. `GET /api/health` returns `{"ok": true}`
4. `GET /api/research/health` returns `{"ok": true}`
5. Research and quant property tests still pass

---

## Git State

Changes are uncommitted. Consider committing the completed spec work before starting the `quant/api/` package creation.
