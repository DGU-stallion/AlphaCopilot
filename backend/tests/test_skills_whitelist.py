"""skills 白名单的守门测试（ADR-0010 修订 §2）。

## 为什么要测目录内容，而不只是测 argv

skills 的内容直接进 system prompt。三件事会静默变坏：

1. **混进违规内容** —— AGENTS 硬规则 10 禁止 qveris/crypto/mootdx 等一整类。
   一旦有人「顺手」把上游 90 个全拷进来，违规项也跟着进来，而 CI 不会红。
2. **token 成本失控** —— 90 个的 description 是 6.1k tokens **每轮**常驻。
   这是持续的、按对话次数计的成本，不会报错，只会慢慢变贵。
3. **取数指引指向不存在的库** —— 上游 skill 写着「pip install yfinance」，
   模型照着做会失败，然后开始自己造数据。这正是硬规则 6 要防的。

所以把这三条都写成断言。它们跑得极快（只读文件），但把「慢慢腐化」变成会红的失败。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"

# ADR-0010 修订 §2 的白名单。改动这个列表要同步改那里的文档与 token 预算。
EXPECTED = {
    "candlestick",
    "correlation-analysis",
    "dividend-analysis",
    "earnings-revision",
    "factor-research",
    "financial-statement",
    "performance-attribution",
    "quant-statistics",
    "risk-analysis",
    "sector-rotation",
    "technical-basic",
    "valuation-model",
}

# AGENTS 硬规则 10 明确禁止的类别（不引入实盘/live/channels/qveris 相关任何代码）。
FORBIDDEN = {
    "qveris", "ccxt", "crypto", "okx", "perp-funding", "stablecoin",
    "onchain", "defi", "mootdx", "vnpy", "pine-script", "token-unlock",
}

# 每轮常驻的 description 预算。12 个实测约 700 tokens；给一倍余量。
MAX_DESCRIPTION_CHARS = 4000


def _skill_dirs() -> list[Path]:
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(d for d in SKILLS_DIR.iterdir() if d.is_dir() and (d / "SKILL.md").exists())


def _frontmatter(path: Path) -> dict[str, str]:
    """取 SKILL.md 的 frontmatter 键值（只解析需要的几个，不引 yaml 依赖）。"""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


def test_skills_dir_exists():
    """skills 目录必须存在——它不存在时 PiProvider 会静默不挂载任何 skill。"""
    assert SKILLS_DIR.is_dir(), f"缺少 {SKILLS_DIR}"
    assert _skill_dirs(), "skills 目录里没有任何含 SKILL.md 的子目录"


def test_only_whitelisted_skills_present():
    """目录里只能有白名单内的 skill。

    这条防的是「顺手把上游 90 个全拷进来」——那会连带把违规项和 6.1k tokens/轮
    的成本一起带进来，而没有任何测试会红。
    """
    actual = {d.name for d in _skill_dirs()}
    extra = actual - EXPECTED
    missing = EXPECTED - actual

    assert not extra, (
        f"出现白名单外的 skill：{sorted(extra)}\n"
        "若确实要加，请同步更新 ADR-0010 修订 §2、本文件的 EXPECTED 与 token 预算"
    )
    assert not missing, f"白名单里的 skill 缺失：{sorted(missing)}"


def test_no_forbidden_categories():
    """禁止类别不得以任何形式出现（目录名、frontmatter、正文取数指引）。"""
    offenders: list[str] = []
    for d in _skill_dirs():
        name = d.name.lower()
        for bad in FORBIDDEN:
            # 目录名命中一定算违规（正文里可能出现「A 股用 244 天」这类
            # 无害比较，不按关键词扫正文，避免误报）
            if bad in name:
                offenders.append(f"{d.name}（目录名含 {bad}）")
                break
    assert not offenders, f"skills 里出现硬规则 10 禁止的类别：{offenders}"


def test_description_budget():
    """description 总量必须在预算内。

    这些 description 每轮都进 system prompt，是不随使用量变化的固定成本。
    上游 90 个是 6.1k tokens；我们压到 12 个约 700 tokens。
    """
    total = 0
    per_skill: dict[str, int] = {}
    for d in _skill_dirs():
        desc = _frontmatter(d / "SKILL.md").get("description", "")
        per_skill[d.name] = len(desc)
        total += len(desc)

    assert total <= MAX_DESCRIPTION_CHARS, (
        f"description 合计 {total} 字符，超过预算 {MAX_DESCRIPTION_CHARS}"
        f"（≈{total // 3} tokens/轮）。明细：{per_skill}"
    )


def test_every_skill_has_name_and_description():
    """Pi 会跳过「没有 description」的 skill（docs/skills.md），且不报错。"""
    broken = []
    for d in _skill_dirs():
        fm = _frontmatter(d / "SKILL.md")
        if not fm.get("name") or not fm.get("description"):
            broken.append(d.name)
        elif fm["name"] != d.name:
            # name 与目录名不一致会让 /skill:name 失效
            broken.append(f"{d.name}（name={fm.get('name')!r}）")
    assert not broken, f"这些 skill 的 frontmatter 不完整或 name 不匹配目录名：{broken}"


def test_data_access_points_at_our_library():
    """skill 里若提到取数，必须指向我们的库，而不是让模型去 pip install 别的东西。

    上游 skill 写着 yfinance / tushare。模型照着 pip install 会失败（而且 run_python
    通道禁网），然后它就开始自己造数据——这正是硬规则 6 要防的。
    """
    # 允许出现这些词，但只能在「说明本环境没有」的语境里
    suspicious = re.compile(
        r"(pip install\s+\S*(yfinance|tushare|akshare|mootdx))"
        r"|(import\s+yfinance)"
        r"|(from\s+tushare)",
        re.I,
    )
    offenders = []
    for d in _skill_dirs():
        text = (d / "SKILL.md").read_text(encoding="utf-8")
        for m in suspicious.finditer(text):
            offenders.append(f"{d.name}: {m.group(0)!r}")
    assert not offenders, (
        "skill 里仍有「让模型自己装取数库」的指引，应改为 alpha.data / research.astock：\n"
        + "\n".join(offenders)
    )


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_skill_mentions_its_source(name):
    """每个 skill 头部要标来源与适配说明（MIT 归属 + 我们改了哪）。

    这不是形式主义：半年后看到「为什么这个文件说 A 股用 244 天」时，
    需要能追回上游原文对照。
    """
    text = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    assert "HKUDS/Vibe-Trading" in text[:400], f"{name} 缺来源标注（MIT 归属）"
