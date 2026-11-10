# Agent Guide

How coding agents should work in this repository.

## The conventions are mandatory

All code here follows the engineering conventions in `docs/conventions/`:

| Doc | Covers |
|---|---|
| `docs/conventions/architecture.md` | Layering (`Protocol → Service → UseCase → Provider / Repository`), dependency direction, error model, configuration and transaction ownership |
| `docs/conventions/testing.md` | Test ownership per layer, patch strategy, coverage that must not be duplicated |
| `docs/conventions/documentation.md` | Documentation language (English only) and structure |

Read the relevant doc before adding or changing code. These are constraints, not suggestions.

## New projects and scripts follow the same rules

This applies to *every* piece of code written for this project — not only code inside the existing package, and not only "real" features.

- **Where a script lives.** Ad-hoc scripts go in `scripts/` with a purpose-revealing name, or become a CLI subcommand under `src/protocols/cli/`. Never leave one-off scripts at the repository root, and never name them `test.py`, `tmp.py`, `new.py`.
- **Scripts use the same layering.** A script that calls an external API, touches a database, or reads configuration goes through `providers/` (third-party calls), `repositories/` (persistence), and `services/` (reusable logic) instead of inlining `httpx`/`requests` calls or SQL in the script body. If the logic is worth running more than once, it belongs in the package, not in the script.
- **Engines are not utilities and not UseCases.** A self-contained subsystem that could be published as a standalone SDK, carries no domain knowledge, and does not depend on the core domain models — an agent loop, a backtest engine — belongs in `src/engines/<name>/`. It exposes one facade, owns its clients and lifecycle, and takes its running mode (dry-run / sandbox / live) and any result-affecting randomness as explicit configuration. Never place such a component in `utils/`.
- **Even disposable scripts stay disciplined.** Deterministic behavior, configuration through the environment or config file (never hardcoded credentials or tokens), no stray state files written into the repository, and cleanup that does not delete user data.
- **No new structure without saying so.** A new top-level directory, a new dependency, or a new abstraction layer must be stated explicitly in the PR with the reason. Adding a layer "because the diagram shows it" is not a reason.
- **New code gets a test.** Follow the ownership rules in `docs/conventions/testing.md`: patch the concrete provider, use a real test database for repositories, and keep one behavior in one test location.

## How much architecture to add

Do not scaffold the full layering up front. Start at the lowest level the actual requirement justifies and add a layer only when a concrete trigger appears (a second external API, a second independent workflow, real persistence, a second implementation of the same capability). The reusable `layered-codebase` skill documents this ladder, including when to remove a layer again.

## Reusable skill

The language-agnostic version of these conventions lives in the `layered-codebase` skill:

- Source: `~/Project/skills/skills/layered-codebase`
- Mounted: `.claude/skills/layered-codebase`

It contains the full layering spec, the complexity ladder, the agent red lines, the review checklist, templates for `AGENTS.md` and directory layout, per-language tooling mappings, and a scaffolding script (`scripts/init_scaffold.py`).

Use it when starting a new project or module — **including projects outside this repository, and including projects that are only a single script**. It is the reference for "what is the minimum structure this needs?" and "what would make this reviewable later?".

## Definition of done

Before reporting work as finished:

- [ ] Layering and dependency direction respected; no reverse or cross-layer imports
- [ ] Every new error code has an owner and is mapped explicitly per layer
- [ ] New behavior has a test, with no duplicated coverage across layers
- [ ] `ruff check .`, `mypy src`, and `pytest` all pass — paste the commands and their output
- [ ] No new dependency, top-level directory, or public interface change without an explicit note in the PR
- [ ] Commit message follows Conventional Commits with the scope matching the module directory
