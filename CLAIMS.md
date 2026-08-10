# CLAIMS — what this tool actually does

**English** · [Русский](CLAIMS.ru.md)

This file exists so that nothing in the README, the video, or the repo promises more than the code delivers. Every claim below names the exact thing that proves it — a command you can run, or a file you can read. If a claim cannot be checked, it does not belong here.

Numbers were measured on **2026‑07‑30** against `nativeprompt 0.1.0`, `rules_version 2026-07-29`. Re-run the commands in [How to verify](#how-to-verify) to check them yourself.

---

## What is true

### Model detection

`nativeprompt` picks the target model from, in order of confidence: an explicit `--model`, markers of the **active CLI session** (`CLAUDECODE` / `CLAUDE_CODE_ENTRYPOINT` for Claude Code, `CODEX_THREAD_ID` / `CODEX_SHELL` / `CODEX_CI` / `CODEX_SANDBOX` for Codex), the env vars `ANTHROPIC_MODEL` / `OPENAI_MODEL` / `CODEX_MODEL`, the `.claude/settings.local.json` → `.claude/settings.json` cascade walked upward from the current directory, `~/.claude/settings.json`, and `~/.codex/config.toml`. An active session of one CLI wins over a stale env var left behind by the other.

Keying is by **family + generation**, so an id the cheatsheet has never seen (`claude-opus-6`) still resolves to the Claude family and gets family rules instead of nothing.

> Verified by: `nativeprompt/detect.py`; 32 tests in `tests/test_detect.py`, including session-vs-stale-env precedence and the project-over-home settings cascade.

### Rules come from vendor documentation

Every rule in `nativeprompt/rules/*.json` carries a `source` URL pointing at an official Anthropic or OpenAI page. There are **26 rules** today across six families:

| Family | Rules | Scope split | Harness recommendations |
|---|---|---|---|
| Claude Code (`claude.json`) | 14 | 8 family-wide + 6 pinned to a generation (`opus-5`, `fable-5`, `opus-4.8`) | 6 |
| Codex (`openai.json`) | 8 | 8 family-wide | 6 |
| Gemini CLI, Grok, Kimi, Qwen | 1 each | family-wide | 7–8 |

The imbalance is stated plainly: the last four are stubs carrying a run-mode
recommendation, not full sets. Claiming the same depth for them would be false.

A test asserts every rule has `id`, `title`, `why`, `source`, `check`, `action`; that `source` is `https://`; and that `check` names a detector that actually exists in `analyze.py`. A second test freezes the rule id sets, so the cheatsheet cannot grow or shrink silently.

The 25 distinct URLs used as rule, harness and generation-page sources, plus the 22 URLs in the self-update manifest, all returned **HTTP 200** when checked on 2026‑07‑30.

> Verified by: `nativeprompt rules`, `nativeprompt/rules/_sources.json`, and 62 tests in `tests/test_rules.py`.

### Each edit is explained with a link

`improve` prints, for every finding, the rule title, *why* the vendor recommends it, and the source URL — before showing the rewritten prompt. That teaching layer is the point of the tool; a silent swap would be less useful and less checkable.

> Verified by: run `nativeprompt improve "..." --model claude-opus-5` and read the "правило:" line under each finding.

### Harness recommendation

The tool classifies the task into one of `trivial | planning | goal | loop | workflow | normal` and maps it to a documented way to run it — for Claude Code: plain prompt, plan mode, `/goal`, `/loop`, workflows; for Codex: plain prompt, `/plan`, `/goal`, delegation to cloud/non‑interactive, and an explicit note that **Codex has no `/loop`**. Each recommendation carries its own source URL.

> Verified by: `nativeprompt/harness.py`, `harness` blocks in the rule files, 6 tests in `tests/test_harness.py`.

### Self-update actually fetches

`nativeprompt update` downloads the 22 canonical `.md` / `llms.txt` vendor pages listed in `rules/_sources.json`, hashes them with SHA‑256, and diffs against `rules/_snapshot.json`. It exits non‑zero when something changed or is new, so CI can fail on it; `.github/workflows/update-rules.yml` runs it weekly.

A real run on 2026‑07‑30: **14 fetched — 9 unchanged, 1 changed, 4 new, 0 unreachable → action needed.** That is the mechanism working, not a passing grade: it means a maintainer owes the cheatsheet a review pass.

> Verified by: `nativeprompt update` (needs network), `nativeprompt/update.py`, 3 tests in `tests/test_update.py`.

### Zero dependencies, deterministic, offline

`dependencies = []` in `pyproject.toml` — stdlib only, `requires-python >=3.9`, CI runs the suite on 3.9 / 3.11 / 3.13. The core never calls a model, so the same input yields the same output and no API key is needed. Only `update` touches the network.

> Verified by: `pyproject.toml`, `.github/workflows/ci.yml`, and the absence of any network call outside `update.py`.

### The prompt is treated as data

`SKILL.md` instructs the agent to treat the user's prompt as **content to improve, not instructions to follow**, and to pass it via stdin rather than interpolating it into a shell command. That closes both prompt‑injection and quoting/substitution holes.

> Verified by: `SKILL.md` step 0 and step 2.

---

## Why the tool does not rewrite your text

This is the project's main design decision, and it was bought at a price.

`improve` changes exactly two things in your prompt: it lowers SHOUTING CAPS and drops the
polite opener ("could you", "не мог бы ты"). It also **adds** placeholder sections. It
deletes nothing and substitutes nothing. Everything the vendor recommends removing — "think
step by step", "double-check yourself", "only the important bits", "show your reasoning",
repetition — is reported as a finding with a source link. You decide.

**Why not automatically.** Eight rounds of independent review, eight consecutive versions:
the regexes that cut text found a new way to destroy meaning every single round. Not
hypothetically — this is what they did to real prompts:

| input | what came out |
|---|---|
| `Обдумай пошагово` ("think it over step by step") | `Об.` — the task destroyed entirely |
| `почему это настолько важное` | `почему это насвсё (…)` — a word cut in half |
| `.env почини` | `Env почини.` — the filename destroyed |
| `show not only the important ones, but also minor` | `show not everything (…)` — meaning inverted |
| `replace "x ; y" with "x; y"` | `replace "x; y" with "x; y"` — the instruction became a tautology |
| `you may not touch prod` | `do not touch prod` — permission became prohibition |
| `fix the bug, think step by step, double-check` | two separate instructions fused into one |
| `Make sure there are no warnings. Run the linter` | the linter sentence vanished entirely |

Each defect was fixed, each got a test, and the next round found a new input of the same
class. That is not sloppiness — it is a property of the problem. Telling a polite turn of
phrase from part of the task cannot be done by word shape. "Think step by step" is an
imposed chain of thought; "describe the deploy process step by step" is a requested output
format. They differ in meaning, not in form. A regex racing language loses every time.

**The smart rewrite is not this tool's job.** `improve` prints a **metaprompt** carrying
every triggered rule, its rationale, its source, and an explicit ban on inventing anything
on the author's behalf. Your own Claude or Codex executes it — a model that does understand
language. The deterministic knives were duplicating work already delegated to something
that does it properly.

**What pins this.** `tests/test_invariant.py` — one property instead of a scattering of
special-case guards: every content word of the original prompt is present in the result.
The one exception is the polite opener, and its words are listed in the test explicitly
rather than obtained by asking the function itself (otherwise a broken function would
excuse its own bug). The property runs over 40 real prompts — fenced and inline code,
quotes of every kind, tables, lists, CAPS in five positions, mixed languages, CRLF, emoji,
degenerate inputs — plus a 500-case fuzzer with a fixed seed, each input against three
rule families.

**What we gave up.** The `improved` field now stays closer to your original: it used to
show a fully rewritten prompt, now it shows your text with CAPS lowered and sections
appended. If you want the finished text, take the metaprompt — that is what it is for.

## What it does NOT do / limits

**It does not invent your task.** Missing details — files, "done" criteria, output format — are inserted as explicit placeholders `‹…›`, never as plausible-sounding content. A test asserts the rewriter does not fabricate file names.

**The deterministic rewrite is structural, not literary — and very narrow.** It changes exactly two things: it lowers Russian intensifier words (English ones only when used as a heading, because `CRITICAL` is more often a log level than a shout) and drops the polite opener. A trailing `!!!` (three or more) collapses to one; `!!` is never touched anywhere — it is an operator in JS, Kotlin and Haskell, and by shape it is indistinguishable from shouting. And a single-line prompt that was edited gets a final period if it had none. It also appends placeholder sections and an XML wrapper for multi-part Claude prompts. Two vendor hints are appended as finished text rather than placeholders: "Answer concisely." for Opus 5 and permission to run to completion for Codex — both short, both about answer shape, both listed in `applied`. No addition appears at all when the prompt ends inside an unclosed code block: a section must not be written into someone else's code, so the findings are merely shown. Advice you already gave yourself ("answer concisely", "run to completion") is not repeated — which is why re-running an already-improved prompt does not accumulate additions. Nothing else is ever glued into the prompt: the advice to move standing rules into AGENTS.md (and its Gemini/Qwen/Kimi/Grok counterparts) lives in the finding and the meta-prompt only, because the executor would read it as one more instruction. Everything the vendor recommends removing by meaning — forced chain-of-thought, "double-check yourself", "only the important bits", duplicated sentences — is FLAGGED with a source link and left untouched; see "Why the tool does not rewrite your text" for the reasoning. The **smart** prose rewrite is not done by this tool at all: `improve` emits a **meta-prompt** that your own Claude or Codex executes. There is no model inside `nativeprompt`, and the quality of that second pass is your model's, not ours.

**Rules are not auto-updated in code.** `update` only *signals* that official docs moved. Editing `rules/*.json` is a human action through a PR. This is deliberate — it keeps the cheatsheet reviewable — but it also means the rules can lag behind a vendor doc change until someone acts on the signal.

**Detectors are regex heuristics.** 15 named checks in `analyze.py`, tuned on Russian and English phrasings. Unusual wording will produce false positives and misses. This is an assistant, not an oracle, and it has no semantic understanding of your prompt.

**What that cost in practice (0.1.1).** The first external report — Windows, Claude Code, opus-5 — found six defects, and all six reproduced on the first try. They are listed plainly because they show the PRICE of the paragraph above rather than contradicting it:

- The run-mode advice was the same for almost everything. Shape `normal` is the catch-all bucket for any prompt without keywords, and it routed to the `trivial` branch — so a large research task got a confident "small clear edit, no plan/goal". The bucket now has its own branch that says outright that the shape could not be determined.
- Shape influenced nothing at all: no detector consulted it. A one-line edit was told to scope the task and add a test run, at an honest `shape: trivial`.
- Triviality was decided by string length. "Write a JSON parser" is under 90 characters, therefore trivial. That heuristic is gone: the signal is what the task means, not how long it is.
- The "drop self-verification" rule cut meaning. From "check yourself: name a source for every figure" it removed the requested deliverable; from "make sure the marker shows up. If it does not — admit the method is leaky" it removed the middle clause, leaving a condition that referred to nothing. Narrowing the detector was not enough: the third version of the knife deleted a whole sentence, «run the linter, and also make sure there are no warnings» — the verification itself. The rule is now a warning: the tool flags, the human cuts. Deletion is left only where nothing can be confused with the task. It fires only on a BARE request, with no deliverable verb and no consequence next to it.
- Cleaning the form corrupted the text. All newlines were collapsed, so a prompt with headings and a numbered list came back as one paragraph; the word "ВАЖНО" was deleted along with the paragraph's structure; and a "split glued sentences" heuristic inserted a period before any capitalised word — "планировщик. Windows", "в. России". That heuristic is gone, cleaning is line-by-line, and shouting caps are lowercased rather than removed.
- `--json` was not UTF-8. On Windows it was written in the system ANSI codepage, which violates the JSON spec; characters outside cp1251 — the arrow, the angle quotes used in placeholders — crashed the command outright.

The reporter's overall diagnosis is accurate and worth recording: the decision to apply a rule was made from surface features of the text — capital letters, the word "file", polite phrasing — and you cannot tell from form that a task is missing meaning. The fixes above narrowed the crudest misses; they did not change the tool's nature. It is still regexes.

Separately, on why the project's own tests missed all of this. There were 67 and they all passed. Every input was a single line, with no markup and no proper nouns; they asserted that unwanted text was REMOVED and never that the rest SURVIVED. `_tidy`, the function holding both text-corruption bugs, had no direct test at all. An author cannot invent an inconvenient input for themselves — they test what they meant. The regressions are pinned in `tests/test_regressions_windows.py`.

**Model aliases do not resolve to a version.** `opus`, `sonnet`, `haiku`, `fable`, `best`, `opusplan`, `default` map to the Claude family but to **no generation** — which model answers behind an alias depends on provider, plan, and `ANTHROPIC_DEFAULT_*`. In that case only family‑wide rules apply, and the report says so (`alias-unresolved`). The `[1m]` context suffix is preserved rather than silently dropped. Same for an unknown id: family rules, no generation rules.

**There are few generation-scoped rules, and all of them are Claude's.** The cheatsheet knows eleven Claude generations and three OpenAI ones, but only six rules are pinned to a generation — three for `opus-5`, two for `fable-5`, one for `opus-4.8`. Every other generation gets family rules: those are not invented, the vendor simply did not publish a page for them.

**Coverage is six families, agentic CLIs only:** Claude Code, Codex, Gemini CLI, Grok, Kimi, Qwen. Not the API, console, or chat surfaces. Rule counts are very uneven: claude 14, openai 8, and one apiece for the other four — those are stubs carrying a run-mode recommendation, not full sets. Claiming the same depth for them would be false.

**It is not a benchmark.** The tool applies vendor *rules*; it does not measure that your prompt became "N% better". No percentage of quality improvement is claimed anywhere, and none should be.

**The CLI speaks Russian.** Interface strings, findings text and the meta-prompt are currently in Russian, even though the rules and their sources are English vendor docs. An English UI is not implemented.

**Published (2026-07-30).** `pip install nativeprompt` and `pipx install nativeprompt` work — verified by installing 0.1.0 from PyPI into a clean virtualenv and running the CLI. Repository: github.com/edvardgrishin27/nativeprompt. Released via PyPI Trusted Publishing from a workflow that runs the test suite first.

**Hook limitation.** `hooks/nativeprompt_hook.py` (Claude Code `UserPromptSubmit`) cannot replace the prompt you typed — Claude Code allows only *adding* context, so the model sees the original next to the improved version. The hook stays silent on prompts under 15 characters and on prompts that trigger no findings, and swallows every error so it can never block a prompt from being sent. It resolves the package on its own: installed package first, then its own repository directory, then `NATIVEPROMPT_HOME` / `CLAUDE_PROJECT_DIR` — no path editing required.

---

## How to verify

```bash
# 1. Test suite — 837 tests, no dependencies beyond pytest
cd nativeprompt && python3 -m pytest -q
# 837 passed
#   622 invariant · 72 regressions · 62 rule integrity · 32 detection · 23 capabilities · 9 analysis · 8 rewrite · 6 harness · 3 update

# 2. Every rule with its official source — spot-check the links
python3 -m nativeprompt rules claude
python3 -m nativeprompt rules codex

# 3. Are the rules still in sync with the vendors' docs?
python3 -m nativeprompt update          # exits 1 when docs changed or are new

# 4. See the contrast the tool is built around, on one prompt
python3 examples/contrast_demo.py
python3 -m nativeprompt improve "почини баг, думай пошагово, перепроверь себя" --model claude-opus-5
python3 -m nativeprompt improve "почини баг, думай пошагово, перепроверь себя" --model gpt-5.6

# 5. What did it detect, and from where?
python3 -m nativeprompt detect          # prints the signal it used
```

Available commands and flags, in full (`nativeprompt/__main__.py`):

| Command | Flags |
|---|---|
| `improve "<prompt>"` (or stdin) | `--model M` · `--json` · `--no-metaprompt` |
| `detect` | `--model M` · `--json` |
| `rules [claude, codex, gemini, grok, kimi, qwen]` | — |
| `update` | `--write` · `--diff` · `--timeout N` · `--json` |

Nothing else exists. If you see a flag documented anywhere that is not in this table, that documentation is wrong.

---

MIT. If you find a claim here that the code does not back, that is a bug — open an issue.
