# Documentation conventions

## Language: English only

**All project documentation under `docs/` must be written in English.**

This includes tool references (`docs/tools/`), engineering conventions (`docs/conventions/`), research notes intended as shared project artifacts, and any other markdown under `docs/`.

| Do | Don't |
|----|--------|
| Write headings, body text, tables, and examples in English | Mix Chinese (or other languages) into `docs/**/*.md` as the primary prose |
| Keep code, CLI, YAML, JSON, symbol names, and API identifiers as-is | Translate identifiers (`binance_perp_tool`, `dry_run`, field names) |
| Prefer short, precise technical English | Duplicate the same doc in a second language under `docs/` |

Chat replies and local scratch notes outside `docs/` are unconstrained. If a contributor drafts in another language, translate into English before landing under `docs/`.

## Tool docs (`docs/tools/`)

Each non-trivial tool should have `docs/tools/<tool_name>.md` covering:

1. Purpose and dependencies (config, SDKs)
2. Inputs / actions / validation rules
3. Output shape (and artifacts, if any)
4. CLI examples
5. Optional pipeline YAML example
6. Operational caveats (dry-run, sandbox, symbol formats, etc.)

Keep README summaries short and link to the full tool doc for detail.

## Cross-links

- Index new convention docs in [`README.md`](./README.md).
- Point agents at `docs/conventions/` from `skills/core/AGENT_GUIDE.md` when norms change.
