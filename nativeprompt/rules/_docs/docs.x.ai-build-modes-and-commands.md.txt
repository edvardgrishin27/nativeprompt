# Modes and Commands

The TUI has pager-local slash commands, plus a smaller set provided by `xai-grok-shell`. User-invocable skills also appear as slash commands.

In the TUI, `Shift+Tab` cycles session modes. For the full key reference, see [Keyboard Shortcuts](/build/keyboard-shortcuts).

## Modes

### Plan

Plan mode is planning first: only the session plan file can be edited until you approve. That file-edit gate is independent of the permission mode (ask, auto, or always-approve). Enter with `/plan [description]` or `Shift+Tab`, and reopen a plan with `/view-plan`. See [Plan Mode](/build/features/plan-mode).

### Auto

Auto uses a classifier to auto-approve safe tools; dangerous ones may still prompt. Toggle with `/auto` or `Shift+Tab` when the feature is enabled. Full mode table: [Permissions](/build/features/permissions).

### Always-approve

Always-approve skips permission prompts for tool calls (`deny` rules and hooks still apply). Toggle with `/always-approve` or `Shift+Tab`, or start with `grok --always-approve`. Modes, allow/deny rules, and how they relate to the sandbox are under [Permissions](/build/features/permissions).

## Core TUI commands

The command palette groups session, context, model, and tool actions.

Use `/context` to check current context usage.

| Command | What it does |
| ------- | ------------ |
| `/quit` (alias `/exit`) | Quit the application |
| `/help` | Browse commands and keyboard shortcuts |
| `/home` | Return to the welcome screen |
| `/new` (alias `/clear`) | Start a new session |
| `/resume` | Resume a previous session |
| `/sessions` | Switch, rename, or close active sessions |
| `/fork` | Branch the current session into a peer agent |
| `/rename <title>` (alias `/title`) | Rename the current session |
| `/share` | Share the current session via URL |
| `/session-info` | Show session info |
| `/context` | View context usage |
| `/compact [context]` | Compact conversation history |
| `/rewind` | Rewind to a previous turn |
| `/export` | Export the conversation to a file or clipboard |
| `/copy [N]` | Copy the last (or Nth-latest) response to the clipboard |
| `/find` | Search the conversation scrollback |
| `/transcript` | View the full transcript in your pager (`$PAGER`) |
| `/model <name>` (alias `/m`) | Switch the active model |
| `/effort` | Set reasoning effort for the current model |
| `/always-approve` | Toggle always-approve mode |
| `/auto` | Toggle auto mode (classifier; when feature enabled) |
| `/plan [description]` | Enter plan mode |
| `/view-plan` | View the current plan |
| `/btw <question>` | Ask a side question without interrupting |
| `/loop [interval] <prompt>` | Run a prompt on a recurring interval — see [Background Tasks](/build/features/background-tasks) |
| `/imagine <prompt>` | Generate an image from a text description |
| `/imagine-video <prompt>` | Generate a video from a text description |
| `/tasks` | List background tasks, subagents, and scheduled tasks |
| `/create-workflow [description]` | Author and save a new workflow |
| `/workflow <name> [args]` | Launch a saved workflow, or `pause` / `resume` / `stop` / `save` a run |
| `/workflows` | Open the live workflow run dashboard (fullscreen) |
| `/deep-research <query>` | Run a background research workflow |
| `/queue` | List the prompts queued behind the running turn |
| `/dashboard` | Open the [Agent Dashboard](/build/features/dashboard) |
| `/settings` (alias `/config`) | Open the settings modal |
| `/theme [name]` (alias `/t`) | Switch the color theme |
| `/compact-mode` | Toggle denser UI layout |
| `/multiline` (alias `/ml`) | Toggle multiline input |
| `/vim-mode` | Toggle vim-style scrollback keybindings |
| `/timestamps` | Toggle message timestamps |
| `/terminal-setup` | Check terminal and clipboard setup |
| `/config-agents` (alias `/agents`) | Manage agent definitions |
| `/personas` | Manage personas |
| `/remember <note>` | Save a memory note |
| `/import-claude` | Open the Claude settings import modal |
| `/feedback [text]` | Send feedback about the current session |
| `/release-notes` (alias `/changelog`) | View release notes for the current version |
| `/usage` | View credit usage or manage billing |
| `/privacy` | Show or toggle privacy and data-retention status |
| `/login`, `/logout` | Sign in, or sign out of the current account |
| `/hooks` | Open the unified extensions modal at the Hooks tab |
| `/plugins` | Open the unified extensions modal at the Plugins tab |
| `/marketplace` | Open the unified extensions modal at the Marketplace tab |
| `/skills` | Open the unified extensions modal at the Skills tab |
| `/mcps` | Open the unified extensions modal at the MCP tab |

`/hooks`, `/plugins`, `/marketplace`, `/skills`, and `/mcps` all open the same extensions modal — they just pre-select a tab. A few commands appear only when their feature is available (for example `/imagine` and `/loop`).

## Shell-provided commands

| Command | What it does |
| ------- | ------------ |
| `/flush` | Flush conversation memory to disk now |
| `/memory` (alias `/mem`) | Browse, view, and manage your memories |
| `/dream` | Run memory consolidation |

These appear when cross-session memory is enabled.

## Skills as commands

Any user-invocable skill can also appear as a slash command, for example `/<skill-name>`.

If names collide, use the qualified form, such as `/local:commit`.

## Workflows

Workflows orchestrate a bounded set of [subagents](/build/features/subagents) in the background: fan out work, verify, then return a result. They are on by default.

Create one with `/create-workflow` and describe what it should do. Grok asks about fan-out, verification, and scope, then authors, smoke-checks, and saves the file as `.grok/workflows/<name>.rhai` in the project, or `~/.grok/workflows/<name>.rhai` for every project.

```text
/create-workflow Review the current branch for bugs, then verify each finding
```

Launch a saved workflow with `/workflow <name>` (optional JSON args) or `/<name>`. `/workflows` is the live run dashboard in the fullscreen TUI; it lists active and retained runs, not saved files.

```text
/workflow review-changes {"target":"origin/main...HEAD"}
/workflow pause review-changes
/workflow resume review-changes
/workflow stop review-changes-2
```

`/deep-research <query>` starts a built-in research workflow. Disable the feature with `[workflows] enabled = false` in `~/.grok/config.toml`, or `GROK_WORKFLOWS=0`.
