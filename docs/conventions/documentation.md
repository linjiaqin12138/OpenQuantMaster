# Documentation conventions

## Language: English only

**All project documentation under `docs/` must be written in English.**

This includes service references (`docs/services/`), engineering conventions (`docs/conventions/`), research notes intended as shared project artifacts, and any other markdown under `docs/`.

| Do | Don't |
|----|--------|
| Write headings, body text, tables, and examples in English | Mix Chinese (or other languages) into `docs/**/*.md` as the primary prose |
| Keep code, CLI, YAML, JSON, symbol names, and API identifiers as-is | Translate identifiers (`BinancePerp`, `dry_run`, field names) |
| Prefer short, precise technical English | Duplicate the same doc in a second language under `docs/` |

Chat replies and local scratch notes outside `docs/` are unconstrained. If a contributor drafts in another language, translate into English before landing under `docs/`.

## Service docs (`docs/services/`)

Each non-trivial service should have `docs/services/<service>.md` covering:

1. Purpose and constructor / config dependencies
2. Inputs / actions / validation rules
3. Output shape (`ServiceResult.data`)
4. Code call examples
5. Operational caveats (dry-run, sandbox, symbol formats, etc.)

Service docs describe only the service contract: parameters, outputs, code call examples, and operational caveats. Do not include CLI commands or CLI usage sections; CLI usage belongs in the CLI command's own `--help` text.

Keep README summaries short and link to the full service doc for detail. Index services in [`docs/services/README.md`](../services/README.md).

## Cross-links

- Index new convention docs in [`README.md`](./README.md).
