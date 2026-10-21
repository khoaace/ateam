"""Prompt gửi cho trưởng nhóm và các thành viên, cùng các hàm tách kết quả."""

from __future__ import annotations

import json
import re

from .config import Config


def roster(cfg: Config, with_effort: bool = False) -> str:
    lines = []
    for n, a in cfg.active_agents().items():
        line = f'- "{n}": {a.role or "general"}'
        if with_effort and a.efforts_for():
            line += f"  [effort levels: {', '.join(a.efforts_for())}]"
        lines.append(line)
    return "\n".join(lines)


TASK_SCHEMA = (
    '[{"id": 1, "type": "code", "agent": "<member name>", "title": "<short title>", '
    '"prompt": "<concise, self-contained instructions: what to change, where (files/areas), done when>", '
    '"depends_on": [<ids>]}]'
)

SUMMARY_RULE = ("End your answer with a line starting with 'SUMMARY:' followed by at most ~5 short lines: what you"
                " changed (files), the result, and anything teammates need to know.")


def _plan_rules(cfg: Config, language_of: str, has_overview: bool = False) -> str:
    """Luật chia việc chung cho lập kế hoạch và kế hoạch tiếp: ít task, prompt ngắn, khám phá vừa đủ."""
    explore = ("""Rely on the PROJECT OVERVIEW above instead of re-exploring the project; open files only to confirm
the specific places you name — members read the code themselves. Members also receive the PROJECT OVERVIEW,
so do not repeat it in task prompts.""" if has_overview else
               """Explore the project only as much as you need to split the work and name the right files — members
read the code themselves, so do not read the whole codebase.""")
    return f"""{explore}
Use as FEW tasks as possible (usually 1-3, at most 6) and assign each to the best member (you may assign
tasks to yourself, "{cfg.lead}"). If one member can do it, make ONE task. Split only when parts can run in
parallel on different files or need different strengths.
{checks_rules(cfg)}
Each prompt must be self-contained (the member only sees its own task, the goal and results of tasks it
depends on) but SHORT — under ~150 words: what to change, where (files/areas), constraints, and when it is
done. Do not paste code; choose sensible defaults for minor details. Use "depends_on" when a task needs
another task's output; otherwise tasks run in parallel, so parallel tasks must not edit the same files.
Write titles and prompts in the same language as the {language_of}.
DO NOT modify any files now.{effort_hint(cfg)}"""


def checks_rules(cfg: Config) -> str:
    """Trưởng nhóm quyết viết test / review code theo preset chất lượng của dự án (cfg.quality). Kiểm tra cuối thì
    ateam tự thêm theo luật (Orchestrator._apply_checks) — chỉ dặn đừng tạo task chạy test."""
    if cfg.quality == "fast":
        tests, review = "Tests: only for risky logic, inside the task that makes the change.", ""
    elif cfg.quality == "strict":
        tests = ("Tests: REQUIRED — every task that changes behaviour must add or update tests for it (in the same "
                 "task, or in a separate task for another member that depends on it).")
        review = ('Code review: REQUIRED — add one task with "type": "review" for a member other than the authors '
                  "(prefer one whose strength is review), depending on the tasks to review.")
    else:
        tests = ("Tests: when a task changes behaviour and the project has tests, ask for tests in that task's "
                 "prompt; only for large or risky logic, add a separate task for another member to write them "
                 "(depending on it). No tests for docs, config, styling or trivial edits.")
        review = ("Code review: only for risky changes (security, data loss, money, concurrency, public APIs, "
                  'migrations) or large ones, add one task with "type": "review" for a member other than the '
                  "authors (prefer one whose strength is review), depending on the tasks to review — it reviews "
                  "their diff and fixes small issues. Skip it for small, low-risk changes.")
    check = ("Never create tasks just to run tests or checks: "
             + (f"ateam runs `{cfg.verify.command}` after each task, and once more on the combined result when tasks"
                " run in parallel." if cfg.verify.command else "each member runs the tests related to its change."))
    return "\n".join(x for x in (tests, review, check) if x)


def effort_hint(cfg: Config) -> str:
    if not cfg.lead_sets_effort:
        return ""
    return ('\nOptionally add "effort" to a task (one of that member\'s effort levels) when it clearly '
            'needs more or less reasoning than usual; omit it otherwise.')


QUESTION_SCHEMA = ('{"question": "...", "why": "why this matters, one line", "options": ["...", "..."], '
                   '"recommended": "..."}')


def plan_prompt(cfg: Config, goal: str, cwd: str, notes: str, can_ask: bool = False, overview: str = "") -> str:
    """can_ask: được hỏi lại người dùng (một câu, như /grill) thay vì lập kế hoạch khi có điểm quan trọng chưa rõ;
    overview: khối PROJECT OVERVIEW của /init (overview.block)."""
    ask = f"""

If — and only if — something ESSENTIAL is unclear (it changes what to build or how, exploring the codebase
cannot answer it, and guessing would risk building the wrong thing), do not plan yet: ask the user ONE
question first. For minor details, choose a sensible default and state it in the task prompt instead.
Give 2-4 short concrete options and your recommended answer, in the same language as the goal.
To ask the user first, reply with ONLY this JSON object instead of the array:
{QUESTION_SCHEMA}""" if can_ask else ""
    return f"""You are the TEAM LEAD of a team of AI coding agents working in: {cwd}

Team members (name: strengths):
{roster(cfg, cfg.lead_sets_effort)}

GOAL from the user:
{goal}

{(overview + chr(10) + chr(10)) if overview else ''}{('Shared team notes:' + chr(10) + notes) if notes else ''}

Break the goal into concrete tasks.
{_plan_rules(cfg, "goal", bool(overview))}

Reply with ONLY a JSON array, no other text:
{TASK_SCHEMA}{ask}"""


def followup_plan_prompt(cfg: Config, goal: str, history: str, prev_summary: str, followup: str,
                         cwd: str, notes: str, earlier: list[str] | None = None, overview: str = "") -> str:
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
{(overview + chr(10) + chr(10)) if overview else ''}{('Shared team notes:' + chr(10) + notes + chr(10)) if notes else ''}
NEW FOLLOW-UP REQUEST from the user:
{followup}

Plan ONLY what this new request needs, building on the work already done (do not redo finished
work); include in each prompt the context it needs from the work done so far.
{_plan_rules(cfg, "follow-up request", bool(overview))}

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
                cwd: str, can_delegate: bool, qa: list[dict] | None = None,
                can_ask: bool = True, siblings: list[tuple[int, str, str]] | None = None,
                verify_cmd: str = "", overview: str = "", kind: str = "code", diff: str = "",
                handoff: bool = False) -> str:
    """siblings: các task khác cùng mục tiêu (id, agent, tiêu đề) — để không làm chồng việc của nhau;
    verify_cmd: lệnh kiểm tra ateam tự chạy sau task — agent chỉ cần chạy test liên quan;
    kind "review": review_rules, diff = cách xem thay đổi của các task phụ thuộc;
    handoff: có task khác phụ thuộc task này — task phân tích/thiết kế/review bàn giao bằng SUMMARY dài hơn."""
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
    if siblings:
        parts.append("\nOTHER TASKS IN THIS GOAL (teammates handle these — do not do them):")
        parts += [f"- #{sid} {sagent}: {stitle}" for sid, sagent, stitle in siblings]
    if overview:
        parts.append("\n" + overview)
    if notes:
        parts.append(f"\nSHARED TEAM NOTES:\n{notes}")
    if qa:
        parts.append(qa_text(qa))
    rules = ["\nRULES:"] + (review_rules(diff, bool(deps)) if kind == "review" else []) + [
        "- Do your task yourself and stay within its scope. Make the smallest change that completes it: do not"
        " refactor, reformat or rename unrelated code, and do not add features, dependencies or docs nobody"
        " asked for.",
        ("- Use the PROJECT OVERVIEW to find the right files; read only the files you need for this task and do"
         " not explore the whole repository." if overview else
         "- Read only the files you need for this task; do not explore the whole repository."),
        (f"- After you finish, ateam automatically runs `{verify_cmd}` and sends you any failure — run only the"
         " tests related to your change, do not run the full suite repeatedly." if verify_cmd else
         "- Check your change (e.g. run the relevant tests) before finishing."),
        "- Keep your answer short: no long explanations, do not paste file contents or long logs.",
    ]
    if can_delegate and others:
        rules += [
            f"- Only if a clearly separate part needs another member's strength ({', '.join(others)}),"
            " delegate it by printing this block (it will run after you finish) — never delegate testing or"
            " reviewing:",
            '<<<DELEGATE to="MEMBER_NAME" title="short title">>>',
            "full self-contained instructions",
            "<<<END>>>",
        ]
    rules += ASK_RULES if can_ask else [ASK_DONE_RULE]
    rules += [
        "- To leave a short fact for the whole team (one line, e.g. a command or a port), print:"
        " <<<NOTE>>>your note<<<END>>>",
        "- " + SUMMARY_RULE,
    ]
    if handoff:
        rules.append("- Other tasks depend on yours. If your task is analysis, design or review (no code changes), the"
                     " SUMMARY is the hand-off they receive: include everything they need, up to ~40 lines.")
    parts.extend(rules)
    return "\n".join(parts)


def review_rules(diff: str, has_deps: bool) -> list[str]:
    """Task "review": agent khác tác giả xem diff, tự sửa lỗi nhỏ, giao lỗi lớn cho tác giả, liệt kê vấn đề còn mở."""
    first = (f"- You REVIEW the work of the tasks you depend on; do not redo it. Read their diff first ({diff}),"
             " then only the code around it." if has_deps else
             "- You REVIEW the code described in your task; read only the files it concerns.")
    return [first,
            "- Check correctness against the goal, edge cases, error handling and security. Do not comment on style or"
            " rewrite working code you would have written differently.",
            "- Fix clear, small bugs yourself with minimal edits. Delegate a larger fix to the task's author with a"
            " DELEGATE block (file:line, what is wrong, what to change) when delegation is available; otherwise"
            " report it.",
            "- In your SUMMARY list what you fixed and every problem still open (file:line — problem), or write"
            ' "no issues found".']


def qa_text(qa: list[dict] | None) -> str:
    """Các câu agent đã hỏi người dùng (<<<ASK>>>) và câu trả lời — gửi kèm khi không tiếp tục được phiên."""
    if not qa:
        return ""
    lines = [f"Q: {x.get('q', '')}\nA: {x.get('a') or '(no answer)'}" for x in qa]
    return "\n\nYOU ASKED THE USER EARLIER (continue the task with these answers):\n" + "\n".join(lines)


ASK_RULES = [
    "- If a requirement is genuinely ambiguous and guessing wrong would change the result (not for"
    " details you can reasonably decide yourself), ask the user ONE question and stop your turn by printing:",
    '<<<ASK>>>{"question": "...", "why": "why it matters", "options": ["...", "..."], "recommended": "..."}<<<END>>>',
    "  You will be resumed with the answer. Write the question in the language of the task.",
]
ASK_DONE_RULE = ("- Do not ask the user more questions: decide yourself and state your assumptions in the"
                 " SUMMARY.")


def retry_prompt(reason: str, reset: bool) -> str:
    """Chạy lại task trong cùng phiên (/retry): agent đã nhớ đề bài, chỉ cần biết lần trước ra sao."""
    where = ("The working tree was reset to the base commit, so your previous changes are gone — redo"
             " the work." if reset else "Your previous changes are still in the working tree.")
    return (f"The user asked you to run this same task again. Previous attempt ended with: "
            f"{reason or '(no error recorded)'}\n{where}\nFinish the task, keeping the change minimal. "
            + SUMMARY_RULE)


def feedback_prompt(feedback: str, reset: bool) -> str:
    """Bị từ chối khi duyệt diff, làm lại kèm góp ý — trong cùng phiên."""
    where = ("The working tree was reset to the base commit (your rejected changes are gone)." if reset
             else "Your previous changes are still in the working tree.")
    return (f"REVIEWER FEEDBACK — your previous attempt was rejected, address this:\n{feedback}\n{where}\n"
            "Change only what the feedback asks for. " + SUMMARY_RULE)


def answer_prompt(question: str, answer: str, can_ask: bool) -> str:
    """Tiếp tục phiên sau khi người dùng trả lời câu hỏi <<<ASK>>>."""
    more = "" if can_ask else " Do not ask further questions; decide yourself and state assumptions."
    return (f"The user answered your question.\nQ: {question}\nA: {answer}\nContinue the task.{more} "
            + SUMMARY_RULE)


SKIP_ANSWER = "(The user did not decide — choose the option you think is best and state your assumption.)"


def skip_answer(rec: str = "") -> str:
    """Người dùng bấm "để trưởng nhóm/agent tự quyết": theo khuyến nghị nếu có (tiếng Anh vì gửi agent)."""
    return f"(The user did not decide — go with your recommendation: {rec})" if rec else SKIP_ANSWER


def question_from(d: dict) -> dict | None:
    """JSON câu hỏi (question/why/options/recommended — /grill, hỏi lại khi lập kế hoạch, <<<ASK>>>) -> mục
    {"q", "why", "options", "rec"} hiển thị cho người dùng; None nếu không có câu hỏi."""
    question = str(d.get("question") or "").strip() if isinstance(d, dict) else ""
    if not re.search(r"\w", question):  # rỗng hoặc "..." của JSON ví dụ trong prompt (CLI in lại prompt)
        return None
    return {"q": question, "why": str(d.get("why") or "").strip(),
            "options": [str(x).strip() for x in d.get("options") or [] if str(x).strip()][:6],
            "rec": str(d.get("recommended") or "").strip()}


# ateam tự chạy lại lệnh kiểm tra sau mỗi lượt sửa: agent chạy cả bộ test nữa là chạy hai lần
FIX_CHECK_RULE = ("To check your fix, re-run only the failing tests — ateam runs the verification command again after "
                  "you finish.")


def fix_resume_prompt(*, command: str, rc: int, output: str, attempt: int, max_attempts: int) -> str:
    """Vòng sửa verify trong cùng phiên: agent nhớ task, chỉ gửi lỗi."""
    return f"""The project's verification command fails after your change. Fix attempt {attempt} of {max_attempts}.

VERIFICATION COMMAND: {command}
EXIT CODE: {rc}
OUTPUT (last lines):
{output}

Fix the code so the verification command passes. Do not delete or weaken tests to make them pass,
unless a test is clearly wrong — then say why. Keep the fix minimal: change only what the failure needs.
{FIX_CHECK_RULE}
End your answer with a line starting with 'SUMMARY:' describing what you fixed (at most ~3 lines)."""


def review_prompt(cfg: Config, goal: str, round_no: int, results: str, cwd: str, final: bool = False,
                  overview: str = "") -> str:
    """final: vòng cuối (max_rounds) — task mới không chạy nữa nên không cần viết; overview: khối PROJECT OVERVIEW
    khi không tiếp phiên lập kế hoạch nào (mục tiêu chạy theo workflow)."""
    more = ("This is the LAST round: new tasks will not run, so set \"new_tasks\" to [] and say in the summary "
            "what is still missing, if anything." if final else
            "If not, create follow-up tasks ONLY for concrete bugs or missing requirements (at most 3, same short "
            "format as a plan) — never for polish, nice-to-haves or new ideas.")
    return f"""You are the TEAM LEAD of a team of AI coding agents working in: {cwd}

Team members:
{roster(cfg, cfg.lead_sets_effort)}

GOAL:
{goal}

Review round {round_no} of {cfg.max_rounds}. Results of the tasks so far:
{results}
{(overview + chr(10)) if overview else ''}
Judge from the task results and verification status above; review tasks list the problems they fixed and any
still open. Open files (prefer `git diff`) only to check a specific doubt; do not re-explore the project or
re-run the whole test suite. DO NOT modify any files.
Decide whether the goal is achieved: set "done" to true when its requirements are met, even if you would
have written the code differently. {more}
Write in the same language as the goal.{effort_hint(cfg) if not final else ''}

Reply with ONLY a JSON object, no other text:
{{"done": true|false, "summary": "<1-3 sentence assessment for the user>", "new_tasks": {TASK_SCHEMA}}}"""


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


def init_prompt(*, cwd: str, current: str = "", changes: str = "", focus: str = "",
                native: list[str] | None = None) -> str:
    """/init: trưởng nhóm tìm hiểu dự án một lần và viết bản tổng quan (overview.py) — hoặc cập nhật bản cũ theo các
    thay đổi kể từ lần trước. Viết tiếng Anh: chỉ agent đọc, ít token hơn. native: file hướng dẫn có sẵn trong repo
    (rules.native_files) — AGENTS.md thì mọi CLI có sẵn tự nạp, chép lại là gửi hai lần."""
    known = ("""
AGENTS.md is loaded automatically by every member's CLI: do NOT repeat what it already says — cover only what
it lacks (if it covers everything, keep the overview very short). Other instruction files (CLAUDE.md,
GEMINI.md…) are read by only some members, so do include their essentials.""" if "AGENTS.md" in (native or []) else "")
    if current:
        task = f"""UPDATE the CURRENT OVERVIEW below. Re-check only the areas touched by the changes listed after it;
keep the parts that are still correct (and anything the user edited by hand), fix or drop what is stale, add
what is new.

CURRENT OVERVIEW:
{current}

CHANGES SINCE IT WAS WRITTEN:
{changes or '(unknown — check the parts most likely to change: layout, commands)'}"""
    else:
        task = """Explore the project: start from README / AGENTS.md / CLAUDE.md / package manifests and the directory
tree, then open only the main entry points. Summarize — do not copy those files verbatim."""
    return f"""You are the TEAM LEAD of a team of AI coding agents working in: {cwd}

WRITE THE PROJECT OVERVIEW: a dense reference that ateam sends with every future planning and task prompt,
so that you and the team members do not have to re-explore the codebase each time.
{task}{known}
{(chr(10) + 'Focus from the user (cover this well): ' + focus + chr(10)) if focus else ''}
Cover, as short bullet points with paths in backticks:
- Purpose: what the project is, in 1-2 lines.
- Stack: languages, frameworks, key libraries.
- Commands: exact commands to install, run, test (one test file / the whole suite), lint, build.
- Layout: directory / module -> responsibility, and the key files (entry points, where X is implemented).
- Architecture: the main data flow and how the parts talk to each other.
- Conventions: code style, naming, error handling, tests, i18n, anything a contributor must follow.
- Gotchas: constraints, generated or vendored files not to edit, slow or flaky things.
Skip what changes often (dependency versions, TODO lists) and anything a member can guess. As short as
possible — at most ~800 words. Read files only: do not install dependencies, build or run tests.
Write in English. DO NOT modify any files.

Reply with the overview in Markdown between these markers (nothing after them):
<<<OVERVIEW>>>
...
<<<END>>>"""


def grill_prompt(cfg: Config, goal: str, qa: list[dict], cwd: str, notes: str, *, finish: bool,
                 max_questions: int, essential_only: bool = False, overview: str = "") -> str:
    """/grill: trưởng nhóm phỏng vấn người dùng từng câu một trước khi lập kế hoạch.
    essential_only: câu hỏi bắt nguồn từ lúc lập kế hoạch (người dùng không gọi /grill) — chỉ hỏi tiếp điểm
    thiết yếu, không phỏng vấn cả cây thiết kế."""
    lines = []
    for i, x in enumerate(qa, 1):
        lines.append(f"Q{i}: {x.get('q', '')}")
        lines.append(f"A{i}: {x.get('a', '')}")
    history = "\n".join(lines) or "(no questions asked yet)"
    if finish:
        task = ("The user wants to STOP the interview now. Do not ask anything else: write the spec from "
                "what you know, and mark open points as your best assumptions.")
    elif essential_only:
        task = (f"The user did not ask for an interview: you asked because something essential was unclear. "
                f"Ask another question ONLY if something ESSENTIAL is still unclear (it changes what to build, "
                f"the codebase cannot answer it, guessing risks building the wrong thing); otherwise finish now. "
                f"You have asked {len(qa)} of at most {max_questions} questions.")
    else:
        task = (f"Ask the NEXT single most important question, or finish if you already have enough to "
                f"plan well. You have asked {len(qa)} of at most {max_questions} questions.")
    scope = ("Keep it short: only resolve what is essential to plan correctly." if essential_only else
             "Walk down each branch of the design tree (scope, user flows, data, edge cases, UX, constraints,\n"
             "acceptance criteria), resolving dependencies between decisions one at a time.")
    return f"""You are the TEAM LEAD of a team of AI coding agents working in: {cwd}

Before planning this GOAL, you INTERVIEW the user to reach a shared understanding of what to build.
{scope} Ask ONE question per
turn. If a question can be answered by exploring the codebase, explore it instead of asking — briefly,
only what that question needs. Never
ask something already answered below. Give 2-4 short concrete options and your recommended answer.
Write questions, options and the spec in the same language as the goal.
You may inspect the project, but DO NOT modify any files.

GOAL from the user:
{goal}

INTERVIEW SO FAR:
{history}
{(overview + chr(10)) if overview else ''}{('Shared team notes:' + chr(10) + notes + chr(10)) if notes else ''}
{task}

Reply with ONLY a JSON object, no other text. Either the next question:
{QUESTION_SCHEMA}
or, when you have enough information (or the user stopped):
{{"done": true, "spec": "concise requirements: scope, decisions agreed with the user, out of scope, acceptance criteria"}}"""


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


def code_edit_prompt(*, path: str, language: str, before: str, selection: str, after: str, instruction: str,
                     cwd: str) -> str:
    """⌘I ở tab Code (web): agent viết lại đoạn đang chọn — trả đoạn thay thế giữa <<<CODE>>> và <<<END>>>,
    không tự sửa file (người dùng xem diff rồi chấp nhận / bỏ)."""
    return f"""INLINE CODE EDIT in the repository at: {cwd}
File: {path} ({language})

Rewrite ONLY the SELECTED CODE according to the instruction. The code before and after it is context: do not repeat it.

INSTRUCTION:
{instruction}

CODE BEFORE THE SELECTION (context, may be truncated):
<<<BEFORE>>>
{before}
<<<END>>>

SELECTED CODE (to replace):
<<<SELECTION>>>
{selection}
<<<END>>>

CODE AFTER THE SELECTION (context, may be truncated):
<<<AFTER>>>
{after}
<<<END>>>

Rules:
- Do NOT modify any files and do NOT run commands — only answer.
- The replacement goes exactly where the selection was: keep the file's indentation and style, and the same
  first-line indentation as the selection.
- Write new comments in the same language as the existing comments of the file.
- Put the replacement code (nothing else, no ``` fences) between these two marker lines:
<<<CODE>>>
(the replacement code)
<<<END>>>"""


def code_explain_prompt(*, path: str, language: str, before: str, selection: str, after: str, question: str,
                        cwd: str, lang: str) -> str:
    """Giải thích đoạn code đang chọn (tab Code web): câu trả lời Markdown sau SUMMARY:."""
    ask = question or "Explain what this code does, how it works, and anything surprising or risky in it."
    reply_lang = ("the same language as the question" if question else
                  {"vi": "Vietnamese", "en": "English"}.get(lang, "the user's language"))
    return f"""EXPLAIN CODE in the repository at: {cwd}
File: {path} ({language})

QUESTION: {ask}

CODE BEFORE (context, may be truncated):
<<<BEFORE>>>
{before}
<<<END>>>

THE CODE TO EXPLAIN:
<<<SELECTION>>>
{selection}
<<<END>>>

CODE AFTER (context, may be truncated):
<<<AFTER>>>
{after}
<<<END>>>

Do NOT modify any files. Answer concisely in {reply_lang}, using Markdown (short paragraphs, bullet lists,
`code`). End with a line 'SUMMARY:' followed by your whole answer (it is shown to the user as is)."""


def conflict_prompt(*, files: list[str], state: str, cwd: str) -> str:
    """Nhờ agent giải quyết xung đột git (tab Git): sửa file, không stage/commit — người dùng xem lại rồi đánh dấu xong."""
    side = ("During a rebase, the <<<<<<< side is the branch being rebased onto and the >>>>>>> side is the commit "
            "being replayed." if state == "rebase" else
            "The <<<<<<< side is the current branch (HEAD) and the >>>>>>> side is the incoming change.")
    return f"""Resolve the git {state or 'merge'} conflicts in the repository at: {cwd}

CONFLICTED FILES:
{chr(10).join('- ' + f for f in files)}

{side}
For each conflict block, look at both sides (and the surrounding code / git log if needed) and write the
correct combined result: keep the intent of BOTH changes unless one clearly replaces the other. Remove every
conflict marker (<<<<<<<, |||||||, =======, >>>>>>>). Change only the conflicted regions; do not refactor or
touch other files. Make sure the result still compiles / parses.
Do NOT run git add, git commit, git merge/rebase --continue or --abort — the user reviews your result first.

End your answer with a line starting with 'SUMMARY:' followed by one short line per file: how you resolved it,
and anything the user should double-check."""


def workflow_suggest_prompt(cfg: Config, description: str, cwd: str) -> str:
    return f"""You are designing a reusable ateam WORKFLOW (a fixed chain of steps the team runs for a goal)
for the repository at: {cwd}

TEAM MEMBERS (name: role){' and their effort levels' if any(a.efforts_for() for a in cfg.active_agents().values()) else ''}:
{roster(cfg, with_effort=True)}
Use "lead" as the agent of a step that the team lead ("{cfg.lead}") should do (design, review, planning).

WHAT THE USER WANTS THE WORKFLOW TO DO:
{description}

Design 2-6 steps. Each step is one task for one member. In titles and prompts write {{goal}} where the
user's goal text should go (the workflow is reused for many goals). Prompts must be self-contained
instructions. "after" lists the step numbers (1-based) this step waits for; omit it to wait for the
previous step, use [] to start immediately (parallel steps). "effort" is optional (one of that member's
effort levels). "type" is "code" (default), "review" (another member reviews the diff of the steps it waits
for and fixes small issues) or "verify" (ateam runs the project's check command once on the combined result
of the steps it waits for and its agent fixes failures — useful after parallel steps). "review": true if the
lead should review the result at the end.
Write name as a short kebab-case slug; write description, titles and prompts in the language of the
user's request above. Do NOT modify any files.

Reply with ONLY a JSON object, no other text:
{{"name": "...", "description": "...", "review": true, "steps": [{{"agent": "<member or lead>", "type": "code", "title": "...", "prompt": "...", "after": [1], "effort": ""}}]}}"""


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

def extract_code_block(text: str) -> str | None:
    """Đoạn code thay thế của ⌘I: giữa <<<CODE>>> cuối cùng và <<<END>>> sau nó (bỏ dòng trống sát hai đầu và
    rào ``` nếu agent vẫn bọc). None nếu không có khối."""
    i = text.rfind("<<<CODE>>>")
    if i < 0:
        return None
    body = text[i + len("<<<CODE>>>"):]
    j = body.find("<<<END>>>")
    if j < 0:
        return None
    lines = body[:j].split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) >= 2 and lines[0].strip().startswith("```") and lines[-1].strip() == "```":
        lines = lines[1:-1]
    return "\n".join(lines)


def extract_overview(text: str) -> str | None:
    """Bản tổng quan của /init: giữa <<<OVERVIEW>>> cuối cùng và <<<END>>> sau nó. None nếu không có / chỉ là mẫu."""
    i = text.rfind("<<<OVERVIEW>>>")
    if i < 0:
        return None
    body = text[i + len("<<<OVERVIEW>>>"):]
    j = body.find("<<<END>>>")
    body = body[:j].strip() if j >= 0 else ""
    lines = body.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":  # agent bọc cả bản trong rào markdown
        first = lines[0].strip()
        inner = any(ln.strip().startswith("```") for ln in lines[1:-1])
        if first in ("```markdown", "```md") or (first == "```" and not inner):
            body = "\n".join(lines[1:-1]).strip()
    return body if body and body != "..." else None


def extract_answer(text: str) -> str:
    """Câu trả lời sau dòng SUMMARY: cuối cùng; không có thì cả output."""
    if "SUMMARY:" in text:
        text = text[text.rfind("SUMMARY:") + len("SUMMARY:"):]
    return text.strip()


def strip_echo(output: str, *prompts: str) -> str:
    """Bỏ phần CLI in lại prompt trước câu trả lời (`codex exec` in "user\\n<prompt>"), để không bóc nhầm JSON
    mẫu, khối DELEGATE/SUMMARY ví dụ trong prompt. Prompt thật đã kèm rule và đổi @file nên không so nguyên văn:
    cắt tới hết vài dòng cuối của prompt (thường là JSON mẫu / luật SUMMARY) ở lần xuất hiện liên tiếp đầu tiên.
    Nhiều prompt: lượt tiếp tục phiên có thể chạy lại bằng prompt đầy đủ khi CLI mất phiên."""
    lines = output.splitlines()
    filled = [(i, ln.strip()) for i, ln in enumerate(lines) if ln.strip()]
    for prompt in prompts:
        tail = [ln.strip() for ln in (prompt or "").splitlines() if ln.strip()][-3:]
        if len("".join(tail)) < 20:  # quá ngắn/chung chung: dễ trùng câu trả lời thật
            continue
        for j in range(len(filled) - len(tail) + 1):
            if all(filled[j + k][1] == tail[k] for k in range(len(tail))):
                return "\n".join(lines[filled[j + len(tail) - 1][0] + 1:])
    return output


def _close_truncated(s: str) -> str | None:
    """JSON thiếu dấu đóng ở cuối (model quên `]` cuối mảng): thêm đủ `}`/`]` còn mở; None nếu không vá được."""
    stack: list[str] = []
    in_str = esc = False
    for ch in s:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "[{":
            stack.append("]" if ch == "[" else "}")
        elif ch in "]}":
            if not stack or stack.pop() != ch:
                return None
    if in_str or not stack:
        return None
    return s.rstrip().rstrip(",") + "".join(reversed(stack))


def extract_json(text: str, kind: type, keys: tuple[str, ...] = ()):
    """Tìm giá trị JSON đầu tiên có kiểu `kind` (list hoặc dict) trong văn bản. Bỏ giá trị rỗng;
    `keys`: object (hoặc mọi phần tử của mảng) phải có ít nhất một khoá trong đó — tránh lấy nhầm
    `[]`/`{...}` agent in ra trước kết quả thật (vd `files: []`, nội dung package.json)."""
    candidates: list[str] = []
    for m in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.S):
        candidates.append(m.group(1))
    candidates.append(text)
    opener = "[" if kind is list else "{"
    dec = json.JSONDecoder()

    def fits(d) -> bool:
        return isinstance(d, dict) and (not keys or any(k in d for k in keys))

    for cand in candidates:
        i = cand.find(opener)
        while i >= 0:
            try:
                val, end = dec.raw_decode(cand, i)
            except json.JSONDecodeError as e:
                # hỏng đúng ở đầu một dòng mới hoặc hết văn bản (JSON hết dòng mà chưa đóng): vá dấu đóng còn thiếu
                head = cand[i:e.pos]
                at_eol = "\n" in head[len(head.rstrip()):] or not cand[e.pos:].strip()
                fixed = _close_truncated(head) if at_eol else None
                try:
                    val = json.loads(fixed) if fixed else None
                except ValueError:
                    val = None
                if isinstance(val, kind) and val and (all(fits(x) for x in val) if kind is list else fits(val)):
                    return val
                i = cand.find(opener, i + 1)
                continue
            if isinstance(val, kind) and val:
                if kind is list and all(fits(x) for x in val):
                    return val
                if kind is dict and fits(val):
                    return val
            # bỏ qua cả giá trị vừa đọc (mảng/object lồng bên trong không phải kết quả)
            i = cand.find(opener, end if isinstance(val, (list, dict)) else i + 1)
    return None


DELEGATE_RE = re.compile(
    r'<<<DELEGATE\s+to="([^"]+)"(?:\s+title="([^"]*)")?\s*>>>\s*(.*?)\s*<<<END>>>', re.S)
NOTE_RE = re.compile(r"<<<NOTE>>>\s*(.*?)\s*<<<END>>>", re.S)
ASK_RE = re.compile(r"<<<ASK>>>\s*(.*?)\s*<<<END>>>", re.S)


def parse_ask(text: str) -> dict | None:
    """Câu hỏi agent gửi người dùng (khối <<<ASK>>> cuối cùng): {"q","why","options","rec"} hoặc None.
    Nội dung không phải JSON → cả khối là câu hỏi."""
    found = [b for b in ASK_RE.findall(text or "") if '"question": "..."' not in b]  # bỏ ví dụ trong prompt
    if not found:
        return None
    body = found[-1].strip()
    d = extract_json(body, dict) if body.startswith("{") or "```" in body else None
    q = question_from(d) if isinstance(d, dict) else None
    if not q:
        return {"q": body, "why": "", "options": [], "rec": ""} if body else None
    return q


def parse_delegations(text: str) -> list[tuple[str, str, str]]:
    # bỏ khối ví dụ trong prompt (codex in lại prompt; output đọc lại từ file log khi merge)
    return [(m.group(1).strip(), (m.group(2) or "").strip(), m.group(3).strip())
            for m in DELEGATE_RE.finditer(text) if m.group(1).strip() != "MEMBER_NAME"]


def parse_notes(text: str) -> list[str]:
    # bỏ câu ví dụ trong prompt (CLI có thể in lại prompt)
    return [m.group(1).strip() for m in NOTE_RE.finditer(text) if m.group(1).strip() not in ("", "your note")]


def extract_summary(text: str, limit: int = 2500) -> str:
    idx = text.rfind("SUMMARY:")
    if idx >= 0:  # "**SUMMARY:**" (agy viết markdown): bỏ dấu ** còn sót
        s = re.sub(r"^\*+", "", text[idx + len("SUMMARY:"):]).strip()
    else:
        s = text.strip()
        s = s[-limit:]
    s = ASK_RE.sub("", DELEGATE_RE.sub("", NOTE_RE.sub("", s))).strip()
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
unless a test is clearly wrong — then say why. Keep the fix minimal: change only what the failure needs.
{FIX_CHECK_RULE}
End your answer with a line starting with 'SUMMARY:' describing what you fixed (at most ~3 lines)."""


def check_fix_prompt(*, agent: str, task_id: int, goal: str | None, note: str, tasks: list[tuple[int, str, str]],
                     command: str, rc: int, output: str, attempt: int, max_attempts: int, cwd: str) -> str:
    """Kiểm tra cuối (task "verify") fail trên kết quả gộp của các task: agent tìm thay đổi gây lỗi rồi sửa."""
    done = "\n".join(f"- #{i} by {a}: {title}" for i, a, title in tasks) or "- (none)"
    return f"""You are "{agent}", a member of an AI agent team. Working directory: {cwd}

The team finished the tasks below, then ateam ran the project's verification command once on their COMBINED
result (final check #{task_id}) and it fails. Fix attempt {attempt} of {max_attempts}.
{('GOAL:' + chr(10) + goal + chr(10)) if goal else ''}
TASKS CHECKED:
{done}
{('NOTE: ' + note + chr(10)) if note else ''}
VERIFICATION COMMAND: {command}
EXIT CODE: {rc}
OUTPUT (last lines):
{output}

Find the change that breaks it (`git status`, `git diff`, `git log`) and fix the code so the verification
command passes. Do not delete or weaken tests to make them pass, unless a test is clearly wrong — then say why.
Keep the fix minimal: change only what the failure needs.
{FIX_CHECK_RULE}
End your answer with a line starting with 'SUMMARY:' describing what you fixed (at most ~3 lines)."""
