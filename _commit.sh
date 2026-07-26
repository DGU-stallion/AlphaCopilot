#!/usr/bin/env bash
# 分批提交积压的改动，然后推送
# 用法：cd /Users/a19150/Project/AlphaCopilot && bash _commit.sh

set -e
cd "$(dirname "$0")"

echo "=== Commit 1: 路由拆分（生产代码）==="
git add \
  backend/quant/api/__init__.py \
  backend/quant/api/_compat.py \
  backend/quant/api/alpha_routes.py \
  backend/quant/api/auth_routes.py \
  backend/quant/api/channels_routes.py \
  backend/quant/api/helpers.py \
  backend/quant/api/live_routes.py \
  backend/quant/api/models.py \
  backend/quant/api/qveris_routes.py \
  backend/quant/api/runs_routes.py \
  backend/quant/api/scheduled_routes.py \
  backend/quant/api/security.py \
  backend/quant/api/sessions_routes.py \
  backend/quant/api/settings_routes.py \
  backend/quant/api/state.py \
  backend/quant/api/swarm_routes.py \
  backend/quant/api/system_routes.py \
  backend/quant/api/uploads_routes.py \
  backend/research/routes/__init__.py \
  backend/research/routes/chat.py \
  backend/research/routes/market_data.py \
  backend/research/routes/portfolio.py \
  backend/research/routes/reports_news.py \
  backend/research/caches.py \
  backend/research/models.py \
  backend/quant/agent/tuning.py \
  backend/pyproject.toml \
  backend/app.py

git commit -m "feat: split monolithic entry into per-domain route modules

quant/api/ replaces api_server.py; research/routes/ extracted from
research/app.py; shared caches.py and models.py extracted."

echo ""
echo "=== Commit 2: 测试文件 ==="
git add \
  backend/tests/test_route_isolation.py \
  backend/tests/test_entry_point_deprecation.py \
  backend/tests/test_api.py \
  backend/tests/test_fixes.py \
  backend/tests/test_reports_and_security.py \
  backend/quant/tests/test_agent_tuning_prop.py \
  backend/quant/tests/test_quant_router_prop.py \
  backend/research/tests/__init__.py \
  backend/research/tests/test_cache_isolation_prop.py \
  backend/research/tests/test_route_preservation_prop.py

git commit -m "test: add correctness property tests for route isolation and auth"

echo ""
echo "=== Commit 3: 前端测试基础设施 ==="
git add \
  frontend/vitest.config.ts \
  frontend/src/lib/resolvePrompt.test.ts \
  frontend/package.json \
  frontend/package-lock.json

git commit -m "test(frontend): add vitest setup and resolvePrompt/API prefix tests

Removes unused @testing-library deps from package.json."

echo ""
echo "=== Commit 4: 项目清理 ==="
git add .gitignore

git commit -m "chore: add .pytest_cache and .hypothesis to .gitignore"

echo ""
echo "=== 推送到 origin/main ==="
git push -u origin main

echo ""
echo "✅ 全部完成！"

# 清理临时脚本自身
rm -- "$0"
rm -f _stage.sh
