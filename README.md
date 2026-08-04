# nativeprompt

**Rewrite your prompt into the native dialect of the model you're actually running — using that vendor's official rules — and show you which rule drove each edit.**

![MIT](https://img.shields.io/badge/license-MIT-black)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![zero deps](https://img.shields.io/badge/dependencies-0-brightgreen)
![67 tests](https://img.shields.io/badge/tests-63%20passing-brightgreen)
![offline](https://img.shields.io/badge/core-deterministic%20%C2%B7%20offline-lightgrey)

**English** | [Русский](README.ru.md)

Scope: the **agentic CLIs** — Claude Code, Codex, Gemini CLI, Grok Build, Qwen Code and Kimi CLI. Not the API, not the web chat.

Coverage differs by vendor, and the tool says so out loud. Anthropic and OpenAI publish
model-specific prompting rules, so for Claude Code and Codex you get both halves: what to
change in the prompt *and* which command to launch with. Google, xAI, Alibaba and Moonshot publish no
such rules — for Gemini CLI, Grok Build, Qwen Code and Kimi CLI you get the harness half only. Inventing rules and
attributing them to a vendor would defeat the point: every finding here cites a source.

---

## Why

The two vendors do not agree on what a good prompt looks like. Their own docs say so.

| Same phrase in your prompt | Claude Code | Codex / GPT‑5.x |
|---|---|---|
| "think step by step" | acceptable scaffolding | **remove it** — reasoning models plan internally, and prescribed intermediate steps get in the way ([reasoning guide](https://developers.openai.com/api/docs/guides/reasoning)) |
| "double-check yourself" | **remove it on Opus 5** — the model already verifies, so the reminder buys over-verification, tokens and latency ([Opus 5 prompting](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)) | harmless, but usually redundant |
| "only report the important stuff" | **rephrase** — Opus 5 follows constraints literally and will genuinely hide the rest; ask for everything, filter in a second pass ([Opus 5 prompting](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5)) | same direction, weaker effect |
| repeated instructions, extra examples | tolerated | **cut them** — lean prompts win on GPT‑5.x ([prompt guidance](https://developers.openai.com/api/docs/guides/prompt-guidance)) |
| mixed instructions + data + examples | **wrap in XML tags** so the model doesn't blend them ([XML tags](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/use-xml-tags)) | not a documented Codex practice |
| "CRITICAL: you MUST…" in caps | **drop the caps** — aggressive scaffolding causes over-triggering on new models | **drop it** — GPT‑4.1-era scaffolding, no longer helps ([GPT‑5 prompting guide](https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_prompting_guide)) |

So a prompt tuned on one CLI is measurably *mis*-tuned on the other. `nativeprompt` detects which one you're on and applies that vendor's published rules — plus it recommends **how to run** the task (`/goal`, `/loop`, plan mode, dynamic workflow on Claude Code; `/plan`, `/goal`, delegation on Codex).

## What makes it different

Both vendors ship a prompt improver, but only for their own model, closed, and frozen at release time. Generic multi-vendor rewriters make *you* pick the target and their rule sets drift out of date. Four properties together are the point:

| | Anthropic prompt improver | OpenAI prompt optimizer | Generic multi-vendor rewriters (Rosetta et al.) | **nativeprompt** |
|---|---|---|---|---|
| **Auto-detects the model you're on** | n/a — Anthropic only | n/a — OpenAI only | you pick the target manually | yes — family + generation, from the live session, env, or settings files |
| **Rules sourced from vendor docs** | implicit, not shown | implicit, not shown | usually hand-written folklore | every rule carries a `source` URL you can open |
| **Explains each edit** | no — silent rewrite | no — silent rewrite | rarely | yes — rule title, rationale, and link per finding |
| **Stays current** | ships when the vendor ships | ships when the vendor ships | goes stale | `update --diff` shows the exact changed lines in the vendor's doc; weekly CI opens a PR with that diff |

Plus: **zero runtime dependencies** (stdlib only), deterministic, works offline, no API key. The only command that touches the network is `update`.

> **Note on language.** The CLI's explanations are currently written in Russian (the author's audience); rule titles link to the vendors' English documentation. The code, the API and this README are English. English CLI output is on the roadmap — see [Contributing](#contributing).

## Install

```bash
pipx install nativeprompt   # or: pip install nativeprompt
```
Published on PyPI. Zero runtime dependencies — stdlib only, works offline, no API key.

Until then, install from a clone:

```bash
git clone https://github.com/edvardgrishin27/nativeprompt
cd nativeprompt
pip install -e .            # gives you the `nativeprompt` command
```

Or run it with no install at all — it is stdlib-only:

```bash
python3 -m nativeprompt improve "your prompt" --model claude-opus-5
```

Requires Python ≥ 3.9. Nothing else.

## Quick start

```bash
# 1. Which model does it think you're on?
nativeprompt detect
```

```
Модель: claude-opus-5[1m] · opus-5
Семейство/CLI: claude (Claude Code)
Определено: ~/.claude/settings.json (сессия Claude Code · VS Code)
```

```bash
# 2. Rewrite + explain. Always pass the prompt over stdin —
#    quotes and $substitutions inside a user prompt will otherwise break the command.
printf '%s' 'Could you please FIX the login bug, think step by step and double-check yourself. Only report the most important things.' \
  | nativeprompt improve --model gpt-5.6
```

Real output (trimmed to the findings and the harness advice):

```
МОДЕЛЬ: Codex (gpt-5.6) · gpt-5.6
определено: явно (--model)

ЧТО УЛУЧШИТЬ (3):
1. [-] Убрать «думай пошагово» / не прописывать промежуточные шаги
   правило: https://developers.openai.com/api/docs/guides/reasoning
2. [+] Outcome-first: цель + формат результата + критерий «готово»
   правило: https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_prompting_guide
3. [~] Просить действие прямо
   правило: https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_prompting_guide
[+] Для большой задачи разрешить идти до конца — https://learn.chatgpt.com/docs/prompting

КАК ЗАПУСКАТЬ (Codex) — форма задачи: normal
  → просто напиши задачу
```

The exact same prompt against Claude Opus 5 produces a *different* set: `think step by step` survives, `double-check yourself` is removed, and scope / verification / output-format placeholders are added. Markers: `[+]` add, `[-]` remove, `[~]` restructure, `[!]` warning.

See both side by side in one command:

```bash
python3 examples/contrast_demo.py
```

More raw prompts to try are in [`examples/prompts.md`](examples/prompts.md).

### Commands

| Command | Flags | What it does |
|---|---|---|
| `improve "<prompt>"` | `--model M`, `--json`, `--no-metaprompt` | detect → analyze → rewrite → harness advice → explain. Reads the prompt from stdin when the argument is omitted. |
| `detect` | `--model M`, `--json` | shows the resolved model, family/CLI, and **which signal** it came from. Exit 1 if nothing resolved. |
| `rules [claude\|codex]` | — | prints every rule with its source URL, plus the harness table. No argument = all families. |
| `update` | `--diff`, `--write`, `--timeout N`, `--json` | fetches the vendors' canonical docs and compares them with stored text snapshots. `--diff` prints the exact before/after lines. Non-zero exit when action is needed (CI signal). `--write` records the new snapshots after you've reviewed the rules. A weekly CI job opens a PR containing the diff — **rules themselves are always edited by a human** (see below). |

`nativeprompt --version` prints the version.

`improve` output has four blocks: **what to fix** (each with the vendor rule + link), the **rewritten prompt**, a **how-to-run** recommendation, and a **meta-prompt** you can hand to your own model for a full prose rewrite (suppress it with `--no-metaprompt`).

## Using it in VS Code

Both CLIs have a VS Code extension, and both have quirks that change how `nativeprompt` sees your setup. Everything in this section comes from the vendors' docs.

### Claude Code extension

**The extension does not put `claude` on your PATH.** It bundles a private copy of the CLI for its chat panel; a standalone CLI install is a separate thing ([vs-code](https://code.claude.com/docs/en/vs-code)). Practical consequence: run `nativeprompt` in VS Code's **integrated terminal** (`` Cmd+` ``), and use the hook (below) if you want it inside the chat panel.

**Where the model actually comes from.** Claude Code's documented precedence is: in-session `/model` → `claude --model` at startup → `ANTHROPIC_MODEL` → the `model` field in your settings file ([model-config](https://code.claude.com/docs/en/model-config)). `nativeprompt detect` follows the same order (env before settings) and tells you which signal it used.

**Three ways to confirm the model, in increasing order of reliability:**

1. `/status` in the chat panel — shows the active model and account ([model-config](https://code.claude.com/docs/en/model-config)).
2. `nativeprompt detect` in the integrated terminal — also names the source file or variable.
3. A `statusLine` script — it receives `model.id` and `model.display_name` on stdin, along with `effort.level` and `context_window.context_window_size`, so it's the only way to confirm that a 1M context is *actually* active ([statusline](https://code.claude.com/docs/en/statusline)).

**If `detect` shows the wrong model,** it is almost always one of these:

- You pressed **`s`** in the `/model` picker ("this session only"). Since v2.1.153 only `Enter` writes the `model` field to your **user** settings; `s` writes nothing, so any settings-based detection sees the old value ([model-config](https://code.claude.com/docs/en/model-config)).
- **VS Code was launched from Finder/Dock and never inherited your shell environment**, so `ANTHROPIC_MODEL` from `.zshrc` is invisible to it. The documented fixes: launch with `code .` from a terminal, set the extension's `claudeCode.environmentVariables` setting, or put the variable in the `env` block of `~/.claude/settings.json` — which is shared between the extension and the CLI ([vs-code](https://code.claude.com/docs/en/vs-code)).
- **Project or managed settings override yours.** The cascade is managed → CLI args → `.claude/settings.local.json` → `.claude/settings.json` → `~/.claude/settings.json` ([settings](https://code.claude.com/docs/en/settings)). When the startup model comes from project or managed settings, the startup header names the file.
- **You're on an alias, not a version.** `opus` / `sonnet` / `haiku` / `best` resolve to different concrete models depending on your provider (Anthropic API vs Bedrock vs Foundry vs Google Cloud), and `ANTHROPIC_DEFAULT_OPUS_MODEL` and friends can redirect them ([model-config](https://code.claude.com/docs/en/model-config)). `nativeprompt` says so explicitly and falls back to family-level rules. Pass `--model claude-opus-5` to get generation-specific rules. The `[1m]` suffix (1M context) is preserved and reported — it works on aliases and on full model names alike, including `opusplan[1m]`.

**Hooks work identically in the panel.** `~/.claude/settings.json` is *"shared between the extension and CLI"* — the same `hooks` block applies to both ([vs-code](https://code.claude.com/docs/en/vs-code)). You can also reach it from the panel: type `/` → **Customize** → hooks. Adding `"$schema": "https://json.schemastore.org/claude-code-settings.json"` to the file gives you completion and validation right in the editor.

### Codex extension

- The IDE extension and the CLI **share the same configuration layers**; open it from the gear icon → **Codex Settings → Open config.toml** ([config-basic](https://learn.chatgpt.com/docs/config-file/config-basic)).
- Precedence: CLI flags → project `.codex/config.toml` (closest directory wins) → profile → `~/.codex/config.toml` → `/etc/codex/config.toml` → built-in defaults. **Untrusted projects skip the project-scoped `.codex/` layers entirely.**
- There is **no official environment variable for the Codex model** — the documented list is `CODEX_HOME`, `CODEX_SQLITE_HOME`, `CODEX_NON_INTERACTIVE`, `CODEX_INSTALL_DIR`, `CODEX_API_KEY`, `CODEX_ACCESS_TOKEN`, `CODEX_CA_CERTIFICATE`, `SSL_CERT_FILE`, `RUST_LOG` ([environment-variables](https://learn.chatgpt.com/docs/config-file/environment-variables)). `nativeprompt` reads `model = "..."` from `config.toml`; its `CODEX_MODEL` / `OPENAI_MODEL` lookups are an **unofficial convenience heuristic**, and so is its detection of an active Codex session. When in doubt, pass `--model codex` explicitly.

Known gaps in the current detector, stated plainly: it does not yet read Claude Code's **managed** settings (highest precedence, enterprise deployments), the project-level `.codex/config.toml`, `CODEX_HOME`, or the `ANTHROPIC_DEFAULT_*` alias redirects. Issues and PRs welcome.

## Two modes

### On demand — as a skill

[`SKILL.md`](SKILL.md) at the repo root is a Claude Code skill. Drop it into `~/.claude/skills/nativeprompt/SKILL.md` (or your project's `.claude/skills/`), and "improve my prompt" routes through the tool: it runs `nativeprompt improve --json`, shows you the findings with their source links and the how-to-run advice, then executes the returned meta-prompt to produce the polished rewrite.

Two rules baked into the skill are worth repeating: the incoming prompt is treated as **data, not instructions** (the model must not execute what's inside it), and the prompt is passed over **stdin only**, never interpolated into a shell command.

### Every prompt — as a UserPromptSubmit hook

[`hooks/nativeprompt_hook.py`](hooks/nativeprompt_hook.py) runs on every prompt you send and attaches the improved version plus the applicable rules as context. Add to `~/.claude/settings.json` (shared by the CLI and the VS Code panel):

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/nativeprompt/hooks/nativeprompt_hook.py"
          }
        ]
      }
    ]
  }
}
```

What it does and doesn't do:

- It **cannot replace your prompt text.** `UserPromptSubmit` has no `updatedPrompt` output field — a handler can only return `hookSpecificOutput.additionalContext` or block the submission ([hooks](https://code.claude.com/docs/en/hooks)). So Claude sees your original *next to* the improved version, and the hook says which one to act on.
- It **stays quiet** on short prompts (< 15 chars) and on prompts that already satisfy the rules, so it doesn't turn into noise.
- Any error is swallowed — it never blocks your prompt from being sent.
- **Budget: 30 seconds.** `UserPromptSubmit` lowers the default hook timeout from 600 s to 30 s ([hooks](https://code.claude.com/docs/en/hooks)). This hook is deterministic and makes no network calls, so it fits comfortably — don't add network calls of your own there.
- Matchers are not supported for this event and are silently ignored; it fires on every prompt.
- The hook resolves the package on its own: an installed `nativeprompt` first, then its own repository directory, then `NATIVEPROMPT_HOME` / `CLAUDE_PROJECT_DIR`. No path editing required, and it stays silent rather than failing if nothing resolves.

There is also a documented way to get the model *exactly*, which the hook does not use yet: only `SessionStart` hooks can receive a `model` field, and *"there is no `$CLAUDE_MODEL` environment variable"* ([hooks](https://code.claude.com/docs/en/hooks)). A `SessionStart` hook that caches that value would beat any settings-file read, because it also catches `--model` and the session-only `s` choice. Contributions welcome.

## Codex usage

Root [`AGENTS.md`](AGENTS.md) governs agent work in this repo. Codex-specific integration lives entirely in [`codex/`](codex/):

- `codex/integration/plugins/nativeprompt/skills/nativeprompt/` — a standalone Codex skill.
- `codex/integration/plugins/nativeprompt/skills/nativeprompt/scripts/improve_prompt.py` — a safe wrapper: stdin only, no shell, validates the JSON contract.
- `codex/integration/AGENTS.md.snippet` — an optional block for your own project's `AGENTS.md` so Codex calls the tool when you ask it to improve a prompt.
- `codex/REVIEW.md` — review notes. By convention, proposed core changes are staged as unified diffs in `codex/patches/` rather than applied to `nativeprompt/` directly.

Local install for Codex:

```bash
python3 -m pip install -e .
mkdir -p ~/.agents/skills
ln -s "$PWD/codex/integration/plugins/nativeprompt/skills/nativeprompt" ~/.agents/skills/nativeprompt
```

Then, in a new Codex session: `$nativeprompt improve this prompt for Codex: ‹prompt›`.

Note that Codex reads persistent project rules from `AGENTS.md` automatically, merged from `~/.codex` down through directories from the repo root to the current one, with deeper files overriding ([agents-md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)). Reasoning depth and answer length belong in `~/.codex/config.toml` (`model_reasoning_effort`, `model_verbosity`), not in prose inside your prompt ([config-reference](https://learn.chatgpt.com/docs/config-file/config-reference)) — `nativeprompt` will tell you so instead of rewriting the prompt around it.

## How it works

```
detect  →  analyze  →  rewrite  →  harness  →  explain          (+ update, out of band)
```

1. **detect** (`detect.py`) — resolves model → **family + generation**. Keying on family means an unreleased id like `claude-opus-6` still gets Claude-family rules instead of nothing. Signals, in order: `--model`, active CLI session markers, `ANTHROPIC_MODEL` / `OPENAI_MODEL` / `CODEX_MODEL`, the `~/.claude/settings.json` cascade, `~/.codex/config.toml`. The `[1m]` suffix is split off and reported separately.
2. **analyze** (`analyze.py`) — regex detectors for prompt smells (`forced_cot`, `verification_demand`, `pushy_caps`, `repetition`, `contradiction_hint`, `missing_verification`, `missing_output_contract`, `vague_ask`, …) plus a **task shape** classifier: `trivial | normal | planning | goal | loop | workflow`.
3. **rewrite** (`rewrite.py`) — the deterministic pass. It removes what the vendor says hurts, restructures what the vendor says to restructure, and adds missing sections **as `‹placeholders›`**. It never invents your task.
4. **harness** (`harness.py`) — maps the task shape to a run mode from the `harness` block of the rules file: plan mode / `/goal` / `/loop` / dynamic workflow on Claude Code, `/plan` / `/goal` / delegation on Codex — each with its own source link.
5. **explain** (`explain.py`) — assembles the report and the **meta-prompt**: a model-specific instruction, built from exactly the rules that fired, which your own Claude or Codex executes to do the full prose rewrite. That split is deliberate — the tool itself contains no model.

## Self-update

`nativeprompt/rules/*.json` is a human-curated, versioned cheat sheet, keyed by **model family + generation**, where every rule carries a `source` URL.

`nativeprompt update` fetches the vendors' canonical `.md` / `llms.txt` pages (manifest: `nativeprompt/rules/_sources.json`), hashes them, and diffs against the stored snapshot:

```
[изменилось]       claude  https://code.claude.com/docs/en/goal.md
[новое]            openai  https://learn.chatgpt.com/docs/prompting.md
[без изменений]    claude  https://code.claude.com/docs/en/best-practices.md
...
Итог: изменилось 1, новых 4, без изменений 9, недоступно 0 (из 14).
```

A weekly GitHub Actions job (`.github/workflows/update-rules.yml`) runs exactly that and fails when the official guidance moved. **The rules are never rewritten automatically** — a maintainer reads the changed doc, updates the JSON, and lands it in a PR, then records the new snapshot with `nativeprompt update --write`. That is a deliberate design choice: a cheat sheet you can audit is worth more than one that mutates silently.

## Boundaries

Deliberately narrow, so the tool stays trustworthy:

- **It does not invent your task.** Missing details — file paths, done criteria, output format — become explicit `‹placeholders›`, never fabricated content.
- **The deterministic rewrite is structural, not literary.** It strips what hurts, restructures, and inserts placeholder sections. The full prose rewrite is the **meta-prompt**, run by your own model. There is no LLM inside this tool.
- **Detectors are regex heuristics.** Unusual phrasings will produce false positives and misses. It is an assistant, not an oracle.
- **An alias is not a version.** `opus`, `sonnet`, `best` resolve differently per provider and plan, so generation-specific rules are withheld and family rules applied — and the CLI says so.
- **No benchmark claims.** The tool applies the vendors' published rules; it does not measure that your prompt got "N% better", and it will never print such a number.
- **v1 covers Claude Code and Codex.** The family architecture is ready for more vendors; nothing else is implemented.

Honest limits are tracked in [`CLAIMS.md`](CLAIMS.md).

## Contributing

Verify first:

```bash
python3 -m pytest -q          # 67 tests: detection, detectors, rewrite, harness, rules integrity, frozen snapshot
```

**Adding or changing a rule.** Rules live in `nativeprompt/rules/<family>.json`. A rule is only accepted with a **link to the vendor's own documentation** — no folklore, no blog posts, no "it worked for me". Shape:

```json
{
  "id": "opus5-remove-verification",
  "scope": "opus-5",                 // "family" or a generation key
  "check": "verification_demand",    // a detector in analyze.py
  "action": "remove",                // add | remove | restructure | warn
  "title": "short imperative",
  "why": "one or two sentences, concrete",
  "source": "https://…"              // official vendor doc, must return 200
}
```

If your rule needs a new `check`, add the detector to `analyze.py` with a test. If the source page isn't in `rules/_sources.json`, add it there too so `update` starts watching it. There's a frozen-snapshot test over the rule set: rule changes are visible in the diff by design.

**Adding a vendor.** Drop a new `nativeprompt/rules/<family>.json` with `detect` (id prefixes + aliases), `generations`, `rules`, and a `harness` block describing that CLI's run modes; register its docs in `_sources.json`. `catalog.py` discovers families from the directory — no code change needed for a well-formed file.

Other useful contributions, in rough priority order: English CLI output, managed-settings and `CODEX_HOME` support in `detect.py`, a `SessionStart` hook for exact model resolution, and detector precision on non-Russian, non-English prompts.

## Why rules are not auto-merged

The robot detects the change, fetches it, shows the exact diff and opens the PR.
The last step — deciding whether a *rule* changes — stays human, on purpose:

1. **A doc change is not a rule change.** Most edits are typos, rewordings, new examples.
   Auto-applying would churn the rules for nothing.
2. **A rule is a translation, not a copy.** The doc says, in prose, "Opus 5 verifies its own
   work — remove explicit verification instructions". The rule is a detector plus a decision
   about scope (whole family, or just this generation). That is judgement.
3. **A wrong auto-update is worse than a stale rule.** It would hand you bad advice *carrying an
   official source link* — that is, with maximum credibility. This package is installed by other
   people; model-written changes should not merge themselves into it.

## License

MIT — see [LICENSE](LICENSE). Built by Edvard Grishin (Futura AI studio).
