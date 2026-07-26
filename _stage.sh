#!/usr/bin/env bash
# Stage only the files that should be committed for this release.
# Run from repo root: bash _stage.sh

set -e
cd "$(dirname "$0")"

git add \
  .gitignore \
  backend/pyproject.toml \
  backend/app.py \
  backend/quant/agent/tuning.py \
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
  backend/quant/tests/test_agent_tuning_prop.py \
  backend/quant/tests/test_quant_router_prop.py \
  backend/research/caches.py \
  backend/research/models.py \
  backend/research/routes/__init__.py \
  backend/research/routes/chat.py \
  backend/research/routes/market_data.py \
  backend/research/routes/portfolio.py \
  backend/research/routes/reports_news.py \
  backend/research/tests/__init__.py \
  backend/research/tests/test_cache_isolation_prop.py \
  backend/research/tests/test_route_preservation_prop.py \
  backend/tests/test_api.py \
  backend/tests/test_fixes.py \
  backend/tests/test_reports_and_security.py \
  backend/tests/test_route_isolation.py \
  backend/tests/test_entry_point_deprecation.py \
  frontend/package.json \
  frontend/package-lock.json \
  frontend/vitest.config.ts \
  frontend/src/lib/resolvePrompt.test.ts

echo "Staged. Now run: git status && git commit -m '...'"
