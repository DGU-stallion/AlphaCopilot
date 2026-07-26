# Requirements Document

## Introduction

AlphaCopilot 将 Vibe-Research（投研看板）与 Vibe-Trading（量化 agent 框架）整合到统一前后端架构下。本需求文档从技术设计推导，覆盖五个核心关注点：统一后端入口、Quant 路由适配、前端统一 API Client、上下文 Agent 快捷入口、以及 Agent 对话端到端流程。

## Glossary

- **Backend_Entry**: 统一后端 FastAPI 应用实例（`backend/app.py`），负责挂载所有模块路由并管理全局中间件
- **Research_Router**: 处理投研数据请求的路由模块，挂载于 `/api/research/*` 路径前缀
- **Quant_Router**: 处理量化 agent 功能请求的路由模块，挂载于 `/api/quant/*` 路径前缀
- **API_Client**: 前端统一的 HTTP/SSE 请求层，包含 `api.ts`（量化接口）和 `apiResearch.ts`（投研接口）
- **Contextual_Agent_Entry**: 投研页面内嵌的快捷按钮组件，预填上下文后跳转 Agent 对话页面
- **Session_Service**: 管理 Agent 对话会话的后端服务，负责消息持久化和 attempt 调度
- **Agent_Loop**: 量化 Agent 的核心执行循环，处理工具调用和响应生成
- **SSE_Channel**: Server-Sent Events 通道，用于实时推送 Agent 执行过程事件到前端
- **Auth_Middleware**: 统一认证中间件，基于 `VR_API_KEY` 环境变量或 loopback 免认证策略

## Requirements

### Requirement 1: 统一后端路由入口

**User Story:** As a developer, I want a single FastAPI application that mounts both research and quant modules, so that the system runs as one process with clear route isolation.

#### Acceptance Criteria

1. THE Backend_Entry SHALL mount Research_Router at the `/api/research` path prefix and Quant_Router at the `/api/quant` path prefix
2. WHEN a request path starts with `/api/research/`, THE Backend_Entry SHALL route it exclusively to Research_Router without invoking Quant_Router handlers
3. WHEN a request path starts with `/api/quant/`, THE Backend_Entry SHALL route it exclusively to Quant_Router without invoking Research_Router handlers
4. THE Backend_Entry SHALL expose a health endpoint at `/api/health` that returns `{"ok": true, "service": "alphacopilot"}`
5. WHEN the Backend_Entry starts, THE Backend_Entry SHALL execute Quant_Router startup lifecycle hooks and on shutdown SHALL execute shutdown hooks
6. IF a Quant_Router startup hook fails, THEN THE Backend_Entry SHALL log the error, keep Research_Router operational, and register fallback routes on `/api/quant/*` that return HTTP 503 with the failure reason

### Requirement 2: 统一 CORS 与认证

**User Story:** As a developer, I want both modules to share the same CORS and authentication policy, so that frontend requests are handled consistently regardless of which module serves them.

#### Acceptance Criteria

1. THE Backend_Entry SHALL configure CORS to allow all origins for local development
2. WHEN the `VR_API_KEY` environment variable is set, THE Auth_Middleware SHALL require a valid API key on all `/api/research/*` and `/api/quant/*` routes
3. WHEN the `VR_API_KEY` environment variable is not set and the request originates from loopback address (127.0.0.1), THE Auth_Middleware SHALL allow the request without authentication
4. WHEN an unauthenticated request is received and authentication is required, THE Auth_Middleware SHALL return HTTP 401 with a descriptive error message

### Requirement 3: Quant 路由适配层

**User Story:** As a developer, I want Vibe-Trading's scattered route registrations refactored into a single APIRouter factory, so that the quant module integrates cleanly into the unified backend.

#### Acceptance Criteria

1. WHEN `create_quant_router()` is called, THE Quant_Router SHALL return an APIRouter containing session, run, swarm, alpha-zoo, settings, and auth endpoint groups
2. THE Quant_Router SHALL exclude live-trading and channels routes from the returned APIRouter
3. WHEN quant module dependencies are unavailable, THE Quant_Router SHALL register fallback routes that return HTTP 503 with a message indicating which dependencies are missing
4. THE Quant_Router SHALL not configure its own CORS or authentication middleware, deferring to Backend_Entry for those concerns

### Requirement 4: 前端统一 API Client

**User Story:** As a frontend developer, I want a unified API client layer that provides typed access to both research and quant endpoints, so that all pages can call backend APIs through a consistent interface.

#### Acceptance Criteria

1. THE API_Client SHALL prefix all quant API calls with `/api/quant` and all research API calls with `/api/research`
2. THE API_Client SHALL share authentication logic (`authHeaders` and `withAuthTicket`) across both research and quant request functions
3. WHEN an SSE connection is established for a quant session, THE API_Client SHALL use the `withAuthTicket` mechanism to authenticate the EventSource connection
4. THE API_Client SHALL export typed request functions for market overview, stock quotes, kline data, financials, valuation, radar, portfolio, and reports under the research namespace
5. WHEN TypeScript compilation is run, THE API_Client SHALL produce zero type errors across all research and quant interface definitions

### Requirement 5: Agent 对话核心流程

**User Story:** As a user, I want to send natural language messages and receive streaming agent responses with visible multi-agent collaboration, so that I can conduct quantitative research through conversation.

#### Acceptance Criteria

1. WHEN a user sends a message to a session, THE Session_Service SHALL persist the message, create an attempt, and return the message_id and attempt_id synchronously
2. WHEN an attempt is created, THE Agent_Loop SHALL execute asynchronously, emitting SSE events for text deltas, tool calls, and tool results through the SSE_Channel
3. WHEN the Agent_Loop completes execution, THE Session_Service SHALL persist the assistant response and emit an `attempt.completed` event through the SSE_Channel
4. IF the Agent_Loop encounters an unrecoverable error, THEN THE Session_Service SHALL emit an `attempt.failed` event with error details through the SSE_Channel
5. WHEN a user sends an empty message, THE Session_Service SHALL reject the request with an HTTP 400 response
6. IF a message is sent to a non-existent session_id, THEN THE Session_Service SHALL return HTTP 404 with a descriptive error
7. IF a message is sent while an active attempt is still executing for the same session, THEN THE Session_Service SHALL reject the request with HTTP 409 Conflict

### Requirement 6: SSE 事件流与重连

**User Story:** As a user, I want real-time streaming of agent execution events with automatic reconnection, so that I never miss intermediate steps even if my network briefly drops.

#### Acceptance Criteria

1. WHEN the frontend connects to SSE with `replay=active`, THE SSE_Channel SHALL replay all events from the currently active attempt for that session
2. THE SSE_Channel SHALL deliver events only for the session specified in the connection URL, never mixing events from other sessions
3. WHEN the SSE connection is interrupted, THE API_Client SHALL automatically reconnect with exponential backoff and display a reconnecting indicator in the UI
4. WHEN SSE reconnection succeeds, THE API_Client SHALL request replay of active events to restore the complete event sequence

### Requirement 7: 上下文 Agent 快捷入口

**User Story:** As a user browsing research pages, I want a contextual shortcut to start an agent conversation pre-filled with the current page context, so that I can seamlessly transition from research to AI-assisted analysis.

#### Acceptance Criteria

1. WHEN the Contextual_Agent_Entry is rendered with a prompt template and context variables, THE Contextual_Agent_Entry SHALL resolve all `{key}` placeholders in the prompt using corresponding values from the context object
2. WHEN a user clicks the Contextual_Agent_Entry button, THE Contextual_Agent_Entry SHALL navigate to the Agent page with the resolved prompt passed as a `prefill` URL search parameter
3. WHEN the Agent page loads with a `prefill` search parameter, THE Agent page SHALL populate the input field with the prefilled prompt without automatically sending it
4. IF a placeholder `{key}` in the prompt has no matching key in the context object, THEN THE Contextual_Agent_Entry SHALL remove the unmatched placeholder from the resolved prompt

### Requirement 8: TypeScript 类型隔离

**User Story:** As a frontend developer, I want research and quant type definitions in separate files without naming conflicts, so that the codebase compiles cleanly and each domain's types are self-contained.

#### Acceptance Criteria

1. THE API_Client SHALL define research data types in `types/research.ts` and quant/agent types in `types/agent.ts` as separate modules
2. WHEN both type modules are imported into the same file, THE TypeScript compiler SHALL produce zero naming conflicts or ambiguity errors
3. WHEN a type name exists in both domains, THE API_Client SHALL use a module-scoped or prefixed naming strategy to prevent collisions

### Requirement 9: Vite 开发代理配置

**User Story:** As a developer, I want the Vite dev server to proxy all `/api` requests to the backend, so that frontend development works seamlessly without CORS issues or manual URL switching.

#### Acceptance Criteria

1. THE Vite dev server SHALL proxy all requests matching `/api` to `http://127.0.0.1:8900`
2. WHEN the frontend makes a request to `/api/research/*` or `/api/quant/*` in development mode, THE Vite proxy SHALL forward the request to the backend preserving the full path
3. WHEN the backend is unreachable, THE Vite proxy SHALL return an appropriate error response to the frontend rather than hanging indefinitely
