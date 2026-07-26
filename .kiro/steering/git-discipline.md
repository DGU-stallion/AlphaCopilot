# Git 提交纪律规则

本文档约束开发过程中 git 的使用方式，防止出现"一次性 300 个文件待提交"的局面。

## 核心原则

**每次提交只做一件事，每件事完成后立即提交。**

提交不是备份，是变更历史的最小可理解单元。

---

## 1. 提交粒度

| 场景 | 正确做法 |
|------|----------|
| 新增一个模块或功能 | 完成后立即提交，不等其他模块 |
| 修 bug | 一个 bug 一个提交，附 test |
| 重构 | 重构和功能变更分开提交 |
| 添加测试 | 可以和被测代码放一个提交，或单独提交 |
| 依赖变更 | 单独提交，commit message 说明原因 |
| 配置/文档 | 与代码分开提交 |

**反模式（禁止）**：
- 开发几天再一次性 `git add .` → 产生几百文件的大提交
- 一个提交混入不相关的文件（"顺手改了"）
- 用提交当草稿箱，message 写 "wip" 或 "temp"

---

## 2. 哪些文件提交，哪些不提交

### ✅ 提交
- 生产代码（`backend/`、`frontend/src/`）
- 测试文件
- 构建配置（`pyproject.toml`、`package.json`、`package-lock.json`）
- 项目级 `.gitignore`
- `README.md`、`CONTEXT.md`、`AGENTS.md`（面向其他用户的文档）

### ❌ 不提交
- `.kiro/` — IDE 会话状态、spec 草稿、steering 个人设置、临时文件
- `docs/` 下的个人开发笔记、handoff 文档、架构探索草稿
- `.env`、`.env.local` — 密钥和本地配置
- `__pycache__/`、`*.egg-info/`、`.venv/` — 构建产物（已在 .gitignore）
- `.DS_Store` — macOS 元数据（已在 .gitignore）
- `.pytest_cache/`、`.hypothesis/` — 测试产物（已在 .gitignore）

### 判断标准
> 问自己：「另一个克隆了这个仓库的开发者，需要这个文件才能运行或理解项目吗？」
> 不需要 → 不提交。

---

## 3. Staging 纪律

永远精确 stage，不要 `git add .`：

```bash
# ❌ 禁止 — 会把所有未追踪的垃圾一起带进去
git add .
git add -A

# ✅ 精确 stage
git add backend/quant/api/sessions_routes.py
git add backend/tests/test_route_isolation.py

# ✅ 按目录 stage（仅当该目录下全部文件都该提交时）
git add backend/quant/api/
git add frontend/src/lib/
```

**每次 commit 前先 `git diff --cached` 看一眼将要提交的内容**，确认没有夹带。

---

## 4. Commit Message 格式

遵循 Conventional Commits：

```
<type>(<scope>): <subject>

[可选 body，解释 why，不是 what]
```

**Type**：
- `feat` — 新功能
- `fix` — bug 修复
- `test` — 添加或修改测试
- `refactor` — 不改行为的重构
- `chore` — 构建、依赖、配置
- `docs` — 文档

**示例**：
```
feat(quant/api): split api_server.py into per-domain route modules
fix(tests): tighten Property 6 assertions, remove 503 escape hatch
chore(frontend): remove unused @testing-library deps
test(research): add cache isolation and route preservation property tests
```

---

## 5. 功能开发节奏（防止积压）

```
开始新功能
    ↓
写代码 → 完成一个自然单元（一个模块、一个接口、一组相关文件）
    ↓
git add <精确文件>
    ↓
git commit -m "feat(...): ..."
    ↓
继续下一个单元
```

**"自然单元"的判断**：如果你能用一句话描述这批改动做了什么，它就是一个提交。
如果需要用"以及"连接，就拆成两个提交。

---

## 6. 当积压已经发生时（补救流程）

如果已经有大量未提交的改动，按以下步骤拆分：

```bash
# 1. 看现状（只看文件名，不看 diff）
git status --short

# 2. 按逻辑分组，分批 stage + commit
#    先提交核心生产代码
git add backend/quant/api/
git commit -m "feat(quant/api): extract route modules from api_server.py"

#    再提交测试
git add backend/tests/test_route_isolation.py
git commit -m "test: add route isolation and auth consistency tests"

#    最后提交配置/清理
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): remove unused testing-library deps"

# 3. 确认没有遗漏
git status

# 4. 推送
git push -u origin main
```

---

## 7. Agent 执行规则

当 agent（Kiro）协助开发时：

- **写完一个模块后立即提醒提交**，不要等到"全部完成"
- 生成 staging 命令时**精确列出文件**，不用 `git add .`
- 如果 `git status` 或 `git diff` 因文件太多而卡死，改用逐文件操作
- `git` 命令全部加 `timeout=12000`，卡死时认为命令已完成并继续
