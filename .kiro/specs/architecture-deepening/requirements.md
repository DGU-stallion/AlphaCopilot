# Requirements Document

## Introduction

Architecture deepening refactoring for AlphaCopilot's unified backend. This feature eliminates structural debt across five axes: triple entry points, ghost import prefixes, router monoliths, silent degradation, and config coupling. The goal is a cleaner module boundary graph that IDE tools, tests, and AI assistants can reason about without runtime tricks.

## Glossary

- **Unified_App**: The single `backend/app.py` FastAPI application that mounts all module routers and owns all middleware/lifecycle logic.
- **Research_Router**: The APIRouter exposed by the research module via `create_research_router()`.
- **Quant_Router**: The APIRouter exposed by the quant module via `create_quant_router()`.
- **Standalone_Entry**: A secondary `FastAPI()` instance (`research/app.py` or `quant/api_server.py`) that duplicates middleware and can be run independently.
- **Ghost_Prefix**: The `src.` import prefix used throughout the quant module that maps to no physical `src/` directory, resolved only via `sys.path` manipulation.
- **Route_Group**: A cohesive set of HTTP endpoints (e.g., chat routes, portfolio routes) that can be registered independently onto an APIRouter.
- **Preflight_Check**: A startup-time validation that asserts required dependencies are importable before the application begins serving requests.
- **Feature_Flag**: An environment variable that explicitly enables or disables an optional route group.
- **AgentTuning**: A frozen dataclass holding all tunable agent loop parameters (token threshold, heartbeat interval, retry delay, tool timeout, goal max continuations).
- **AgentLoop**: The ReAct core loop in `backend/quant/agent/loop.py` that drives multi-step agent reasoning.

## Requirements

### Requirement 1: Eliminate Standalone Entry Points

**User Story:** As a developer, I want a single authoritative FastAPI entry point, so that middleware, auth, and CORS configuration exist in exactly one place and cannot drift between copies.

#### Acceptance Criteria

1. THE Unified_App SHALL be the only file that instantiates a `FastAPI()` application with middleware and auth logic.
2. WHEN `backend/research/app.py` exists, THE Research_Module SHALL expose only a `create_research_router() -> APIRouter` function and SHALL NOT instantiate its own `FastAPI()` application with middleware.
3. WHEN `backend/quant/api_server.py` exists, THE Quant_Module SHALL expose only route-registration functions and SHALL NOT instantiate its own `FastAPI()` application with middleware.
4. IF a developer runs `python backend/research/app.py` directly, THEN THE Research_Module SHALL either fail with a clear deprecation message or delegate to the Unified_App.
5. IF a developer runs `python backend/quant/api_server.py` directly, THEN THE Quant_Module SHALL either fail with a clear deprecation message or delegate to the Unified_App.
6. THE Unified_App SHALL centralize all CORS configuration in a single `CORSMiddleware` registration.
7. THE Unified_App SHALL centralize all auth middleware in a single middleware function.

### Requirement 2: Eliminate sys.path Hacks and Ghost Import Prefix

**User Story:** As a developer, I want all Python imports to resolve through standard package mechanisms, so that IDE navigation, type checking, and AI code tools work without runtime path manipulation.

#### Acceptance Criteria

1. THE Quant_Module SHALL NOT contain any `sys.path.insert()` or `sys.path.append()` calls in production code.
2. THE Quant_Module SHALL NOT use `from src.*` import paths in any production module.
3. WHEN a quant internal module is imported, THE Quant_Module SHALL resolve the import using either `from quant.<subpackage>` absolute imports or relative imports.
4. WHEN a backtest module is imported from within quant code, THE Quant_Module SHALL use `from quant.backtest.<module>` rather than `from backtest.<module>`.
5. THE Quant_Module SHALL declare its package structure in a `pyproject.toml` (or equivalent) so that `pip install -e .` makes all internal imports resolvable.
6. THE test configuration (`conftest.py`) SHALL NOT contain `sys.path.insert()` calls; instead it SHALL rely on the installed package for import resolution.
7. WHEN all ghost prefix imports are replaced, THE Quant_Module SHALL pass its existing test suite without import errors.

### Requirement 3: Split Research Router into Internal Seams

**User Story:** As a developer, I want the research router split into focused sub-modules, so that each route group can be understood, tested, and modified independently.

#### Acceptance Criteria

1. THE Research_Module SHALL organize routes into at least four internal sub-modules: chat, portfolio, market_data, and reports_news.
2. WHEN routes are split, each sub-module SHALL expose a `register_<name>_routes(router: APIRouter)` function that attaches its endpoints to the provided router.
3. THE `create_research_router()` function SHALL remain the single public entry point and its return type SHALL remain `APIRouter`.
4. WHEN the split is complete, THE Research_Router SHALL serve the same set of HTTP endpoints at the same paths as before the refactoring.
5. THE module-level cache dictionaries (`_PCT_CACHE`, `_ANN_CACHE`, `_FIN_CACHE`, `_DC_CACHE`) SHALL be injectable (passable as parameters) rather than hardcoded module globals.
6. WHEN a sub-module is tested in isolation, THE test SHALL be able to provide its own cache instance without monkeypatching module-level state.

### Requirement 4: Quant Router Fail-Fast Instead of Silent Degradation

**User Story:** As a developer, I want the quant router to fail loudly at startup when core dependencies are missing, so that I get immediate feedback rather than discovering broken routes at request time.

#### Acceptance Criteria

1. WHEN the Unified_App starts and a core quant dependency (sessions, runs) fails to import, THEN THE Quant_Router SHALL raise an exception that prevents application startup.
2. WHEN the Unified_App starts and an optional quant dependency (alpha zoo, swarm) fails to import, THEN THE Quant_Router SHALL log a warning and omit that route group without registering a catch-all fallback.
3. THE Quant_Router SHALL NOT register a catch-all `/{path:path}` fallback route that returns 503 for any unmatched path.
4. THE Unified_App SHALL NOT wrap the quant router inclusion in a try/except that registers its own fallback router.
5. WHERE an optional route group is controlled by a Feature_Flag environment variable, THE Quant_Router SHALL check the flag before attempting to import and register that group.
6. WHEN the application starts successfully, THE Quant_Router SHALL have a deterministic set of registered routes that tests can assert against.

### Requirement 5: Extract AgentTuning Dataclass from AgentLoop

**User Story:** As a developer, I want agent configuration captured in a single immutable dataclass, so that tests can inject configuration without monkeypatching module-level functions and the runtime reads config exactly once.

#### Acceptance Criteria

1. THE Quant_Module SHALL define a frozen `AgentTuning` dataclass containing fields: `token_threshold`, `heartbeat_interval_s`, `reasoning_delta_min_interval_s`, `stream_retry_delay_s`, `tool_timeout_seconds`, `goal_max_continuations`.
2. THE AgentTuning dataclass SHALL provide a `from_env_config()` class method (or factory function) that constructs an instance from the current environment configuration.
3. THE AgentLoop SHALL accept an `AgentTuning` instance as a constructor parameter.
4. WHEN the AgentLoop needs a tuning value, THE AgentLoop SHALL read it from its `AgentTuning` instance rather than calling a module-level accessor function.
5. THE Quant_Module SHALL NOT contain module-level `_token_threshold()`, `_heartbeat_interval_s()`, `_reasoning_delta_min_interval_s()`, `_stream_retry_delay_s()`, `_tool_timeout_seconds()`, or `_goal_max_continuations()` wrapper functions after refactoring.
6. THE Quant_Module SHALL NOT use the `_override()` mechanism that inspects `sys.modules[__name__].__dict__` for monkeypatched values.
7. WHEN a test needs to override tuning parameters, THE test SHALL construct an `AgentTuning` instance with custom values and pass it to the AgentLoop constructor.
