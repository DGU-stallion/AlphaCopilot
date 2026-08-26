# Domain Docs

## Layout

Single-context repo.

- **Glossary**: `CONTEXT.md` at the repo root (create lazily when the first term is resolved)
- **ADRs**: `docs/adr/` at the repo root (create lazily when the first decision is recorded)

## Consumer rules

- Read `CONTEXT.md` before writing any code — use its vocabulary for domain terms, not your own synonyms.
- Before proposing an architectural change, check `docs/adr/` for ADRs that may already have settled the question.
- When a term is resolved during a session, update `CONTEXT.md` immediately — don't batch.
- Only propose a new ADR when the decision is hard to reverse, surprising without context, and the result of a real trade-off.
