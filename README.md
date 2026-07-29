# nativeprompt

**Rewrite your prompt into the *native dialect* of the model you're actually using — by each vendor's OFFICIAL rules — and learn why.**

Every model has its own prompting grammar. Claude Code likes explicit structure, roles, and (as a fallback) chain-of-thought. Codex / GPT‑5 reasoning models want the *opposite*: minimal scaffolding, **no forced "think step by step"**, and are actively hurt by contradictions and repetition. The same prompt is better on one and worse on the other.

`nativeprompt` detects which model/CLI you're on, rewrites your prompt to that vendor's **official** best‑practices, and tells you **which rule drove each change** (with a link). It also recommends **how to run** the task (`/goal`, `/loop`, plan mode, dynamic workflow for Claude Code; `/plan`, `/goal`, delegation for Codex).

Scope: the **agentic CLIs** — **Claude Code** and **Codex** — not the API/console/chat.

## Why it's different

Anthropic and OpenAI each ship a prompt improver — but only for their own model, closed, and static. Multi‑vendor tools make *you* pick the target and their rules go stale. `nativeprompt` is the only one that combines all four:

1. **Auto‑detects the current model** (family + generation) and applies *its* rules.
2. **Official vendor rules only** — every suggestion links to the source doc, no folk hacks.
3. **Explains why** — a teaching layer, not a silent swap.
4. **Self‑updating cheatsheet** — a `update` command + CI diff of the vendors' `.md`/`llms.txt` docs keeps the rules current as models change.

Zero runtime dependencies (stdlib only). Deterministic core — no API key needed to run it.

## Install

```bash
pipx install nativeprompt          # or: pip install nativeprompt
# or from source:
git clone https://github.com/edvardgrishin27/nativeprompt && cd nativeprompt && pip install -e .
```

## Use

```bash
# auto-detect the model from your session/env, rewrite + explain
nativeprompt improve "почини баг в логине, думай пошагово, перепроверь себя"

# target a specific model
nativeprompt improve "..." --model claude-opus-5
nativeprompt improve "..." --model gpt-5.6          # or: codex

# which model did it detect?
nativeprompt detect

# show the rules + their sources
nativeprompt rules claude
nativeprompt rules codex

# self-update: check whether the vendors' official docs changed
nativeprompt update
```

`improve` prints: what to fix (each with the vendor rule + link), the rewritten prompt, a **how‑to‑run** recommendation, and a **meta‑prompt** you can hand to your own model for a smarter rewrite (the "разбор + мета‑промт" engine).

See the contrast in one shot:

```bash
python3 examples/contrast_demo.py
```

## How the two layers work

- **Deterministic pass** (`improve` → *улучшенный промпт*): removes what hurts (forced CoT for Codex, "double‑check" for Opus 5, pushy CAPS, repetition), restructures (XML for Claude, explicit action), and adds missing sections **as placeholders `‹…›`** — it never invents your task.
- **Meta‑prompt** (the smart path): a model‑specific instruction assembled from the applicable rules that your own Claude/Codex runs to fully rewrite the prose.

## Self‑update

`rules/*.json` is a human‑curated, versioned cheatsheet keyed by **model family + generation** (so a future `claude-opus-6` still gets Claude‑family rules). `nativeprompt update` fetches the canonical `.md`/`llms.txt` vendor docs (manifest in `rules/_sources.json`), diffs them against a snapshot, and flags when the official guidance changed — so a maintainer reviews and updates the rules via PR. The rules never change silently.

## Boundaries

It improves the *wording and structure* of your prompt for the target model. It does **not** guess the task for you — missing details become explicit `‹placeholders›`.

## License

MIT. Built for the "Внутри FuturaAI" channel by Edvard Grishin.
