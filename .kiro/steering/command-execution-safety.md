# 命令执行防卡死规则

本项目的 Python 代码库较大（quant/ 下有 100+ 文件），执行 shell 命令时容易因输出量过大或依赖解析超时而导致 agent 卡住。以下规则强制执行。

## ⚠️ Kiro 已知 Bug：终端命令卡住

这是 Kiro IDE 的已知 bug（GitHub issues: #53, #1734, #4909, #6005, #2992, #4817 等），
目前没有官方修复。表现为：
- 命令实际已完成（终端已显示输出和 shell prompt）
- 但 Kiro 无法读取终端输出，一直显示 "Working..."
- 大量输出的命令特别容易触发

**用户 Workaround**：
1. 手动在终端按 Enter 或输入任意字符触发 Kiro 读取
2. 如果仍卡住，手动复制终端输出粘贴到 chat 中
3. 最后手段：重启 Kiro

**Agent 缓解策略**：
- 绝不运行可能产生大量输出的命令
- 验证代码正确性优先用 `ast.parse` 或 `get_diagnostics`，避免触发长 import 链
- 如果 execute_bash 超时但上下文表明命令应该很快完成，可以继续下一步（认为命令已完成）
- 子代理中避免依赖命令输出来决定下一步 — 用工具读取文件状态代替

## 1. 禁止大输出搜索命令

**绝对不要**在 `execute_bash` 中运行可能产生大量输出的搜索命令：

```bash
# ❌ 禁止 — 可能输出 200+ 行
grep -rn "from src\." --include="*.py" quant/
find . -name "*.py" -exec grep "pattern" {} \;
cd backend && grep -r "sys.path" --include="*.py"

# ✅ 替代方案 — 使用 grep_search 工具
# grep_search 工具有内置截断，不会卡死
```

**规则**：凡是搜索文件内容的需求，一律使用 `grep_search` 或 `read_file` 工具，不要用 bash grep/find。

## 2. 管道命令限制

管道链 (`|`) 本身不受支持（`&&`, `||`, `;` 等命令分隔符被禁止）。如果需要过滤输出：

```bash
# ❌ 禁止
grep -r "pattern" | grep -v ".venv" | tail -80

# ✅ 替代方案
# 1. 用 grep_search 工具的 excludePattern 参数
# 2. 或者用 execute_bash 加 timeout 参数（毫秒）
```

## 3. pip install 必须加超时

```bash
# ❌ 可能卡死
pip install -e .

# ✅ 加超时（60 秒）
pip install -e . --no-deps  # 如果只需验证包声明
# 或在 execute_bash 中设置 timeout: 60000
```

## 4. pytest 命令必须加约束

```bash
# ❌ 可能无限运行
python -m pytest tests/ -v

# ✅ 加超时和限制
python -m pytest tests/specific_test.py -x -q --timeout=30 --tb=short 2>&1 | head -30
# 或直接用 timeout 参数：execute_bash timeout=30000
```

## 5. 语法验证优先于 import 验证

当需要验证代码正确性时，优先用 `ast.parse`（纯语法检查，不触发 import）：

```bash
# ✅ 快速、无依赖
python -c "import ast; ast.parse(open('file.py').read()); print('Syntax OK')"

# ⚠️ 慎用 — 如果依赖链很长会卡住
python -c "from quant.agent.loop import AgentLoop"
```

## 6. 子代理提示中必须包含警告

派发 spec-task-execution 子代理时，prompt 中必须包含以下提醒：

> **IMPORTANT**: Do NOT run grep/find commands via bash that may produce large output. Use grep_search or read_file tools instead. Add timeout=30000 to any execute_bash calls that might hang.

## 7. 优先使用内置工具

| 需求 | ❌ 不要用 | ✅ 要用 |
|------|-----------|---------|
| 搜索代码内容 | `grep -r` | `grep_search` 工具 |
| 查看文件 | `cat file.py` | `read_file` 工具 |
| 列出文件 | `find . -name "*.py"` | `list_directory` 或 `file_search` 工具 |
| 检查语法 | 完整 import | `ast.parse` 或 `get_diagnostics` |
| 运行测试 | 不加超时的 pytest | `execute_bash` + timeout 参数 |
