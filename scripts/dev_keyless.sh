#!/usr/bin/env bash
# 一键起 keyless 验收环境（B 方案）：mock 模型 + 后端 + 前端。
# 用法： bash scripts/dev_keyless.sh
# 打开： http://127.0.0.1:5899
# 停止： Ctrl-C（会清理三个子进程）
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
MOCK_PORT=8999
SDK="/Users/a19150/Project/deepseek-harness/python/sdk/src:/Users/a19150/Project/deepseek-harness/python/sdk-runtime/src"

pids=()
cleanup() { echo; echo "[dev] 停止…"; for p in "${pids[@]:-}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM

echo "[dev] 1/3 起 mock 模型 (:$MOCK_PORT) …"
python3 "$REPO/scripts/dev_mock_model.py" "$MOCK_PORT" &
pids+=($!)
sleep 1

echo "[dev] 2/3 起后端 FastAPI (:8900) …"
(
  cd "$REPO/backend"
  export PYTHONPATH="$SDK:."
  export DSH_RUNTIME_MODE=node
  export DEEPSEEK_BASE_URL="http://127.0.0.1:$MOCK_PORT/v1"
  export DEEPSEEK_API_KEY="sk-keyless-mock"
  export ALPHACOPILOT_DB="$REPO/workspace/dev.db"
  python3 -m api.main
) &
pids+=($!)
sleep 2

echo "[dev] 3/3 起前端 Vite (:5899) …"
(
  cd "$REPO/frontend"
  pnpm dev
) &
pids+=($!)

echo
echo "======================================================"
echo "  keyless 验收就绪：打开  http://127.0.0.1:5899"
echo "  试试："
echo "    · 你好 / 你能做什么          → 纯文字逐字回复"
echo "    · 分析白酒板块相关性          → 相关性热力图"
echo "    · 用 20/60 金叉回测茅台       → 净值+回撤图+指标（job）"
echo "  （内容为脚本化 mock，非真实 LLM 推理）"
echo "  Ctrl-C 停止全部"
echo "======================================================"
wait
