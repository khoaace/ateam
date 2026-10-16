"""Prompt gửi cho trưởng nhóm và các thành viên, cùng các hàm tách kết quả."""

from __future__ import annotations

import json
import re

from .config import Config


def roster(cfg: Config, with_effort: bool = False) -> str:
    lines = []
    for n, a in cfg.active_agents().items():
        line = f'- "{n}": {a.role or "general"}'
        if with_effort and a.efforts:
            line += f"  [effort levels: {', '.join(a.efforts)}]"
        lines.append(line)
    return "\n".join(lines)


TASK_SCHEMA = (
    '[{"id": 1, "agent": "<member name>", "title": "<short title>", '
    '"prompt": "<detailed, self-contained instructions>", "depends_on": [<ids>]}]'
)


def effort_hint(cfg: Config) -> str:
    if not cfg.lead_sets_effort:
        return ""
    return ('\nOptionally add "effort" to a task (one of that member\'s effort levels) when it clearly '
            'needs more or less reasoning than usual; omit it otherwise.')


def plan_prompt(cfg: Config, goal: str, cwd: str, notes: str) -> str:
    return f"""You are the TEAM LEAD of a team of AI coding agents working in: {cwd}

Team members (name: strengths):
{roster(cfg, cfg.lead_sets_effort)}

GOAL from the user:
{goal}

{('Shared team notes:' + chr(10) + notes) if notes else ''}

Break the goal into a SMALL number (1-8) of concrete tasks and assign each to the best member
(you may assign tasks to yourself, "{cfg.lead}"). Each prompt must be self-contained: the member
only sees its own task, the goal and results of tasks it depends on. Use "depends_on" when a task
needs another task's output; otherwise tasks run in parallel, so parallel tasks must not edit the
same files. Write titles and prompts in the same language as the goal.
You may inspect the project to plan, but DO NOT modify any files now.{effort_hint(cfg)}

Reply with ONLY a JSON array, no other text:
{TASK_SCHEMA}"""


def followup_plan_prompt(cfg: Config, goal: str, history: str, prev_summary: str, followup: str,
                         cwd: str, notes: str, earlier: list[str] | None = None) -> str:
    """Kế hoạch cho yêu cầu "tiếp tục" một mục tiêu đã làm xong."""
    prior = "".join(f"\nEarlier follow-up {i}: {f}" for i, f in enumerate(earlier or [], 1))
    return f"""You are the TEAM LEAD of a team of AI coding agents working in: {cwd}

Team members (name: strengths):
{roster(cfg, cfg.lead_sets_effort)}

The team ALREADY WORKED on this goal earlier:
ORIGINAL GOAL:
{goal}{prior}

WORK DONE SO FAR (task results):
{history or '(no task results kept)'}
{('Your previous assessment: ' + prev_summary + chr(10)) if prev_summary else ''}
{('Shared team notes:' + chr(10) + notes + chr(10)) if notes else ''}
NEW FOLLOW-UP REQUEST from the user:
{followup}

Plan ONLY what this new request needs, building on the work already done (do not redo finished
work). Break it into a SMALL number (1-8) of concrete tasks and assign each to the best member
(you may assign tasks to yourself, "{cfg.lead}"). Each prompt must be self-contained: the member
only sees its own task, the goal and results of tasks it depends on, so include the relevant
context from the work done so far. Use "depends_on" when a task needs another task's output;
parallel tasks must not edit the same files. Write titles and prompts in the same language as
the follow-up request.
You may inspect the project to plan, but DO NOT modify any files now.{effort_hint(cfg)}

Reply with ONLY a JSON array, no other text:
{TASK_SCHEMA}"""


def thread_prompt(turns: list[tuple[str, str]], new: str) -> str:
    """Hỏi tiếp trong thread /task: các lượt trước (yêu cầu, kết quả) + yêu cầu mới, không bọc vai trò."""
    if not turns:
        return new
    parts = ["We are continuing an earlier conversation in this project. Previous turns:"]
    for i, (req, res) in enumerate(turns, 1):
        parts.append(f"\n[{i}] Request:\n{req}\n[{i}] Your result:\n{(res or '(no result)')[:2500]}")
    parts.append(f"\nNEW REQUEST:\n{new}")
    return "\n".join(parts)


def task_prompt(cfg: Config, *, agent: str, task_id: int, title: str, prompt: str,
                goal: str | None, deps: list[tuple[int, str, str, str]], notes: str,
                cwd: str, can_delegate: bool) -> str:
    others = [n for n in cfg.active_agents() if n != agent]
    parts = [
        f'You are "{agent}", a member of an AI agent team (team lead: "{cfg.lead}").',
        f"Working directory: {cwd}",
    ]
    if goal:
        parts.append(f"\nOVERALL TEAM GOAL:\n{goal}")
    parts.append(f"\nYOUR TASK (#{task_id}): {title}\n{prompt}")
    if deps:
        parts.append("\nRESULTS OF TASKS YOU DEPEND ON:")
        for did, dagent, dtitle, dres in deps:
            parts.append(f"--- #{did} by {dagent}: {dtitle} ---\n{dres or '(no summary)'}")
    if notes:
        parts.append(f"\nSHARED TEAM NOTES:\n{notes}")
    rules = [
        "\nRULES:",
        "- Do your task yourself and stay within its scope.",
    ]
    if can_delegate and others:
        rules += [
            f"- If part of the work is clearly better done by another member ({', '.join(others)}),"
            " delegate it by printing this block (it will run after you finish):",
            '<<<DELEGATE to="MEMBER_NAME" title="short title">>>',
            "full self-contained instructions",
            "<<<END>>>",
        ]
    rules += [
        "- To leave information for the whole team, print: <<<NOTE>>>your note<<<END>>>",
        "- End your answer with a line starting with 'SUMMARY:' followed by a concise summary:"
        " what you did, files changed, and anything teammates need to know.",
    ]
    parts.extend(rules)
    return "\n".join(parts)


def review_prompt(cfg: Config, goal: str, round_no: int, results: str, cwd: str) -> str:
    return f"""You are the TEAM LEAD of a team of AI coding agents working in: {cwd}

Team members:
{roster(cfg, cfg.lead_sets_effort)}

GOAL:
{goal}

Review round {round_no} of {cfg.max_rounds}. Results of the tasks so far:
{results}

You may inspect the project files to verify the work, but DO NOT modify any files.
Decide whether the goal is fully achieved. If not, create follow-up tasks (fix problems, missing
parts). Write in the same language as the goal.{effort_hint(cfg)}

Reply with ONLY a JSON object, no other text:
{{"done": true|false, "summary": "<short assessment for the user>", "new_tasks": {TASK_SCHEMA}}}"""


def compact_prompt(*, notes: str, goals: str, log: str, focus: str, cwd: str) -> str:
    return f"""You are the TEAM LEAD of a team of AI coding agents working in: {cwd}

The team's shared context has grown long. COMPACT it: write a short summary that will REPLACE the
notes below and be sent with every future prompt to the team.

SHARED TEAM NOTES:
{notes or '(none)'}

RECENT GOALS (id, status, text, lead's assessment):
{goals or '(none)'}

SYSTEM LOG (last lines):
{log or '(empty)'}
{(chr(10) + 'Focus of the summary, from the user: ' + focus + chr(10)) if focus else ''}
Keep only what future tasks need: decisions, conventions, facts about the project (commands, ports,
paths), what is done and what is still open or failing. Drop chatter, timings and repeated lines.
At most ~25 short bullet points. Write in the same language as the notes and goals.
Do NOT modify any files.

End your answer with a line 'SUMMARY:' followed by the bullet points (nothing after them)."""


def commit_message_prompt(*, diff: str, recent: str, cwd: str) -> str:
    return f"""You are writing a git COMMIT MESSAGE for the changes below, in the repository at: {cwd}

RECENT COMMIT MESSAGES of this repository (match their language, tone and format — e.g. Conventional
Commits prefixes if they use them):
{recent or '(no commits yet — write in English)'}

CHANGES TO COMMIT (git diff --stat, then the diff; may be truncated):
{diff}

Write one commit message: a subject line of at most ~72 characters in the imperative mood, then
(only if the change is not trivial) a blank line and a short body (2-5 lines) explaining WHAT changed
and WHY. No code blocks, no quotes, no trailers.
Do NOT modify any files and do NOT run git yourself.

End your answer with a line 'SUMMARY:' followed by the commit message only (nothing after it)."""


def extract_commit_message(text: str) -> str:
    """Commit message sau dòng SUMMARY: cuối cùng (bỏ rào ``` và ngoặc kép bao ngoài)."""
    if "SUMMARY:" not in text:
        return ""
    msg = text[text.rfind("SUMMARY:") + len("SUMMARY:"):].strip()
    lines = [ln for ln in msg.splitlines() if not ln.strip().startswith("```")]
    msg = "\n".join(lines).strip()
    if len(msg) >= 2 and msg[0] == msg[-1] and msg[0] in "\"'`":
        msg = msg[1:-1].strip()
    return msg


# ---------------- tách kết quả ----------------

def extract_json(text: str, kind: type):
    """Tìm giá trị JSON đầu tiên có kiểu `kind` (list hoặc dict) trong văn bản."""
    candidates: list[str] = []
    for m in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.S):
        candidates.append(m.group(1))
    candidates.append(text)
    opener = "[" if kind is list else "{"
    dec = json.JSONDecoder()
    for cand in candidates:
        for i, ch in enumerate(cand):
            if ch != opener:
                continue
            try:
                val, _ = dec.raw_decode(cand[i:])
            except json.JSONDecodeError:
                continue
            if isinstance(val, kind):
                if kind is list and val and not all(isinstance(x, dict) for x in val):
                    continue
                return val
    return None


DELEGATE_RE = re.compile(
    r'<<<DELEGATE\s+to="([^"]+)"(?:\s+title="([^"]*)")?\s*>>>\s*(.*?)\s*<<<END>>>', re.S)
NOTE_RE = re.compile(r"<<<NOTE>>>\s*(.*?)\s*<<<END>>>", re.S)


def parse_delegations(text: str) -> list[tuple[str, str, str]]:
    return [(m.group(1).strip(), (m.group(2) or "").strip(), m.group(3).strip())
            for m in DELEGATE_RE.finditer(text)]


def parse_notes(text: str) -> list[str]:
    return [m.group(1).strip() for m in NOTE_RE.finditer(text) if m.group(1).strip()]


def extract_summary(text: str, limit: int = 2500) -> str:
    idx = text.rfind("SUMMARY:")
    if idx >= 0:
        s = text[idx + len("SUMMARY:"):].strip()
    else:
        s = text.strip()
        s = s[-limit:]
    s = DELEGATE_RE.sub("", NOTE_RE.sub("", s)).strip()
    return s[:limit]


def fix_prompt(*, agent: str, task_id: int, title: str, prompt: str, command: str, rc: int,
               output: str, attempt: int, max_attempts: int, cwd: str,
               original_agent: str) -> str:
    who = "you" if agent == original_agent else f'"{original_agent}"'
    return f"""You are "{agent}", a member of an AI agent team. Working directory: {cwd}

Task #{task_id} ("{title}") was just implemented by {who}, but the project's verification command
fails. Fix attempt {attempt} of {max_attempts}.

ORIGINAL TASK:
{prompt}

VERIFICATION COMMAND: {command}
EXIT CODE: {rc}
OUTPUT (last lines):
{output}

Fix the code so the verification command passes. Do not delete or weaken tests to make them pass,
unless a test is clearly wrong — then say why. Run the command yourself if you can.
End your answer with a line starting with 'SUMMARY:' describing what you fixed."""
