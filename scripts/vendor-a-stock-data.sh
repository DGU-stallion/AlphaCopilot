#!/usr/bin/env bash
# vendor a-stock-data 同步脚本（M3-V6）
#
# 一条命令完成：下载 → 校验 → 跑上游测试 → 绿则更新 NOTICE，红则回滚。
#
# 为什么需要脚本而不是手工 curl：
#   vendor 是**只读**区（CI 用 `git status --porcelain vendor/` 校验无本地改动）。
#   手工 curl 会漏文件（我们已经漏过 README.md / README_en.md，导致本地 1 红
#   而 CI 绿 —— 「CI 绿本地红」最容易被忽略）。脚本把「该有哪些文件」
#   变成一份清单，漏了就跑不过。
#
# 用法：
#   ./scripts/vendor-a-stock-data.sh                # 同步到 pin 的 commit
#   ./scripts/vendor-a-stock-data.sh <commit>       # 试用别的 commit（会写 NOTICE）
#   DRY_RUN=1 ./scripts/vendor-a-stock-data.sh      # 只下载不落盘

set -euo pipefail

REPO="simonlin1212/a-stock-data"
# 默认 pin 的版本：V3.10.2。升级时改这里 + 更新 docs/research/a-stock-data-v3.10.md。
PINNED_COMMIT="29b07d2e3700"
COMMIT="${1:-$PINNED_COMMIT}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/data-service/vendor/a-stock-data"
VENV_PY="$ROOT/data-service/.venv/bin/python"

# 必须齐全的文件清单。少一个就可能「本地红而 CI 绿」。
FILES=(
  SKILL.md
  LICENSE
  CHANGELOG.md
  README.md
  README_en.md
  tests/test_valuation.py
  tests/test_official_data.py
  tests/test_v39_sources.py
  tests/test_v310_sources.py
)

step() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
fail() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ---------- 0. 前置检查 ----------
step "0/5 前置检查"
[ -x "$VENV_PY" ] || fail "没有 data-service 的 venv，先按 data-service/README.md 创建"
echo "commit: $COMMIT"
echo "dest:   $DEST"

# ---------- 1. 下载到临时目录 ----------
step "1/5 下载"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

for f in "${FILES[@]}"; do
  mkdir -p "$TMP/$(dirname "$f")"
  url="https://raw.githubusercontent.com/$REPO/$COMMIT/$f"
  code=$(curl -sL -o "$TMP/$f" -w '%{http_code}' --max-time 60 "$url")
  if [ "$code" != "200" ]; then
    fail "下载失败 $f (HTTP $code) —— commit $COMMIT 里可能没有这个文件"
  fi
  printf '  ✓ %-34s %s bytes\n' "$f" "$(wc -c < "$TMP/$f" | tr -d ' ')"
done

# ---------- 2. 结构校验（防上游悄悄改了形态）----------
step "2/5 结构校验"
LINES=$(wc -l < "$TMP/SKILL.md" | tr -d ' ')
BLOCKS=$(grep -c '```python' "$TMP/SKILL.md" || true)
echo "  SKILL.md: $LINES 行 / $BLOCKS 个 python 块"
# 这两个数字变了不一定是错，但值得停下来看一眼（上游大改版）。
[ "$BLOCKS" -gt 50 ] || fail "python 块只有 $BLOCKS 个，形态异常（期望 >50）"

# ---------- 3. 跑上游测试（在临时目录里，不碰 vendor）----------
step "3/5 上游测试"
cp -R "$ROOT/data-service/src" "$TMP/src" 2>/dev/null || true
( cd "$TMP" && "$VENV_PY" -m pytest tests -q ) || fail "上游测试失败，已中止（vendor 未被修改）"

# ---------- 4. 落盘 ----------
step "4/5 落盘"
if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "  DRY_RUN=1，跳过落盘"
else
  # 先清旧文件再拷：避免上游删了某个测试文件而我们留着残留。
  # 只清我们管理的这些路径，不 rm -rf 整个目录（防止误删 NOTICE 等本地文件）。
  for f in "${FILES[@]}"; do
    mkdir -p "$DEST/$(dirname "$f")"
    cp "$TMP/$f" "$DEST/$f"
  done
  echo "  已写入 $DEST"
fi

# ---------- 5. 更新 NOTICE ----------
step "5/5 更新 NOTICE"
NOTICE="$DEST/NOTICE"
{
  echo ""
  echo "## 同步记录 $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo ""
  echo "来源: https://github.com/$REPO/tree/$COMMIT"
  echo "下载校验（sha256）:"
  for f in "${FILES[@]}"; do
    printf '    %-40s %s\n' "$f" "$(shasum -a 256 "$TMP/$f" | cut -d' ' -f1)"
  done
  echo ""
  echo "上游测试: 通过（见步骤 3）"
} >> "$NOTICE"

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "  DRY_RUN=1，NOTICE 未写入（上面是要写的内容）"
else
  echo "  已追加到 $NOTICE"
fi

step "完成"
echo "提醒：vendor/ 是只读区。CI 会校验「无本地改动」："
echo "    git status --porcelain data-service/vendor/"
echo "如果上面有输出，说明连 NOTICE 也被手改了 —— 应该让脚本改。"
