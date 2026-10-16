# ateam — an AI coding team in your terminal

[Tiếng Việt](README.md) · Docs: https://ateam.khoaace.workers.dev

ateam is a terminal app (Python + Textual) that runs several AI coding CLIs — Claude Code, Codex, Antigravity
(`agy`), Grok Build (`grok`), OpenCode, or any CLI with a headless mode — as one team on your repo:

- a **lead** (default `claude`) turns your goal into a task plan, reviews results and assigns follow-ups;
  `/grill <goal>` lets the lead interview you one question at a time before planning;
- a SQLite **task board** (`.ateam/team.db`) shared by the TUI, the CLI and the agents;
- a **scheduler** that runs tasks by dependency with a parallel limit; agents delegate to each other;
- verify commands after each task, optional git worktrees with diff review before merge, rate-limit detection
  with fallback agents;
- a 🌿 **Git tab**: stage, commit (the lead can write the message), branches, pull/push, stash, history.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/khoaace/ateam/main/scripts/get.sh | bash
ateam            # open the TUI in the current directory
```

## Code tab (vim keys)

`/code @src/app.py:42` (or `/edit @file`, or key `e` in the Git tab / diff screen) opens the file in the 📝 Code
tab: syntax highlighting, line numbers, several open files, and core vim keys (`i a o`, `Esc`, `hjkl w b e gg G`,
counts, `dd yy p cw u Ctrl+R`, `v V`, `/ n N`, `:w :q :wq :q! :e!`). `/vim off` switches to normal editing
(Ctrl+S saves). Files an agent changes while open are reloaded (or you are warned if you have edits).

## Language and theme

- `/lang en` or `/lang vi` in the app (it restarts itself); `ateam lang en` to save it from the shell;
  `ateam --lang en <command>` or `ATEAM_LANG=en` for a single run. First run follows your `LANG`.
- `/theme` opens the theme picker: 21 built-in Textual themes (dark and light) plus an optional accent color
  (blue, purple, green, orange, pink, yellow, cyan, red), with live preview. Shortcut: `/theme nord purple`.

Both choices are stored in `~/.config/ateam/state.json` and shared across projects.

## Basics

Type a goal in the input box and press Enter: the lead plans, you approve with F2, the team works. `/help`
(F1) lists every command and shortcut; Ctrl+T switches tabs (Board, Team, Terminal, Git).

See [README.md](README.md) (Vietnamese) for the full guide.
