#### Features

# AGENTS.md

Project rules are Markdown files that Grok loads into context for every session in a directory tree. Put coding conventions, build and test commands, and architecture notes in an `AGENTS.md` at your repo root, and Grok follows them without being told each session.

## Discovery

Grok loads rules in this order, with deeper files taking precedence on conflicts:

1. Global rules in `~/.grok/`
2. Every directory from the repo root down to the working directory (or only the working directory outside a git repo)

Within each directory, Grok reads any of `AGENTS.md`, `Agents.md`, `AGENT.md`, `CLAUDE.md`, `Claude.md`, and `CLAUDE.local.md`, plus every `*.md` file in a `.grok/rules/` directory (`.claude/rules/` and `.cursor/rules/` are read for compatibility). Files ignored by `.gitignore` are skipped, which keeps personal overrides like `CLAUDE.local.md` out of shared context.

A nested `AGENTS.md` scopes to its subtree, so a monorepo can carry different conventions per package:

```text
my-monorepo/
  AGENTS.md                # repo-wide rules
  packages/
    frontend/AGENTS.md     # "Use React. Prefer CSS modules."
    backend/AGENTS.md      # "Use Express. Follow REST conventions."
```

Files are loaded in full, with no size cap; short, specific instructions are followed more reliably than long ones.

## Session rules

To add rules for a single run without editing files, pass `--rules` (Grok appends the text to the system prompt), or `--system-prompt-override` to replace the system prompt entirely:

```bash customLanguage="bash"
grok --rules "Always use TypeScript. Prefer functional components."
```

## Verification

```bash customLanguage="bash"
grok inspect
```

This lists each rules file Grok found, with its path and approximate token count.
