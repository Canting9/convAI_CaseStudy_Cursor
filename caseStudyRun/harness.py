"""Run the Fair A task through Cursor's CLI agent, log everything, then have another model grade it.

Usage (from the caseStudyRun folder):
    python harness.py models                       # list model ids your account can use
    python harness.py run --models MODEL_A MODEL_B MODEL_C composer-2 [--self-report]
    python harness.py grade --grader MODEL_X       # blind-grades every run with a different model

Outputs go to runs/: one anonymous folder per run (run1, run2, ...), each with the repo copy,
events.ndjson (raw agent stream), transcript.md, and results.json. harness_log.csv collects one row per run (runs_log.csv is left for manual runs).
Tokens and cost are not in the CLI output: copy them from your Cursor usage dashboard into harness_log.csv.
"""
import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = HERE / "cursor-task"
HIDDEN = HERE / "cursor-eval" / "test_hidden.py"
RUNS = HERE / "runs"
LOG = HERE / "harness_log.csv"

PROMPT = (
    "In this repo, add late fees to the library. A loan is late for each day after its due date until it is "
    "returned (or until `today` if it's still out). Charge 25 cents per late day, capped at $10.00 per loan. "
    "Premium members get their first 3 late days free on each loan. Add `Library.fees_owed(member_id, today)` "
    "returning the total in cents as an int, and add fees to each line of the `report` CLI output in the form "
    "`, fees $X.YZ`. Keep existing behavior working and make the tests pass."
)

SELF_REPORT_PROMPT = (
    "The task is finished; do not change any files. Reply with ONLY a JSON object, no other text: "
    '{"estimated_wall_time_s": <number>, "estimated_total_tokens": <number>, "estimated_tool_calls": <number>, '
    '"confidence_all_requirements_met": <0-1>, "requirements_you_are_unsure_about": "<text>", '
    '"what_you_would_do_differently": "<text>"}'
)

GRADER_PROMPT = """You are grading another agent's change to this repo. Do not modify any files.

The task it was given:
<<TASK>>

Held-out test results (tests the agent never saw):
<<HIDDEN>>

The agent's diff against the starting code:
<<DIFF>>

Read the code as needed, then reply with ONLY a JSON object, no other text:
{"spec_correctness": <0-5>, "code_quality": <0-5>, "scope_discipline": <0-5>, "would_merge_as_is": "Y" or "N",
 "bugs_or_spec_misses": "<text>", "one_line_verdict": "<text>"}
"""

FIELDS = [
    "run", "model", "wall_time_s", "agent_duration_s", "tool_calls", "tool_breakdown",
    "visible_passed", "visible_total", "hidden_passed_of_9", "lines_added", "lines_removed", "files_changed",
    "input_tokens", "output_tokens", "cost_usd",
    "self_est_wall_time_s", "self_est_tokens", "self_est_tool_calls", "self_confidence",
    "grader_model", "spec_correctness", "code_quality", "scope_discipline", "would_merge_as_is", "grader_verdict",
]


def agent_bin(override):
    if override:
        return override
    for name in ("agent", "cursor-agent"):
        found = shutil.which(name)
        if found:
            return found
    sys.exit("Couldn't find the Cursor CLI ('agent' or 'cursor-agent'). Install it, or pass --agent-bin PATH.")


def sh(cmd, cwd=None, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")


def read_log():
    if not LOG.exists():
        return {}
    with open(LOG, newline="", encoding="utf-8") as f:
        return {row["run"]: row for row in csv.DictReader(f) if row.get("run") and row.get("model")}


def write_log(rows):
    with open(LOG, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for key in sorted(rows, key=lambda k: int(re.sub(r"\D", "", k) or 0)):
            w.writerow(rows[key])


def extract_json(text):
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def fresh_repo(dest):
    """Copy the task at its FIRST commit (the untouched base), never the current working tree."""
    if (TASK / ".git").exists():
        roots = sh(["git", "rev-list", "--max-parents=0", "HEAD"], cwd=TASK).stdout.split()
        if not roots:
            sys.exit("cursor-task has a .git folder but no commits; commit the base first.")
        archive = dest.parent / "base.zip"
        out = sh(["git", "archive", "--format=zip", "-o", str(archive), roots[-1]], cwd=TASK)
        if out.returncode != 0:
            sys.exit("git archive failed: " + out.stderr)
        import zipfile
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
        archive.unlink()
    else:
        shutil.copytree(TASK, dest, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "transcripts"))
    sh(["git", "init", "-q"], cwd=dest)
    sh(["git", "add", "-A"], cwd=dest)
    sh(["git", "-c", "user.name=harness", "-c", "user.email=harness@local", "commit", "-qm", "base"], cwd=dest)


def pytest_counts(target, repo):
    env = dict(os.environ, PYTHONPATH=str(repo))
    out = sh([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(target)], cwd=repo, env=env)
    text = out.stdout + out.stderr
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", text)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", text)) else 0
    errors = int(m.group(1)) if (m := re.search(r"(\d+) error", text)) else 0
    return passed, passed + failed + errors, text


def tool_name(tc):
    if not isinstance(tc, dict) or not tc:
        return "unknown", {}
    if "function" in tc:
        fn = tc["function"] or {}
        return fn.get("name", "function"), fn.get("arguments", {})
    key = next(iter(tc))
    val = tc[key] if isinstance(tc[key], dict) else {}
    return key.replace("ToolCall", ""), val.get("args", val)


def summarize(args, limit=140):
    text = json.dumps(args, ensure_ascii=False) if not isinstance(args, str) else args
    return text if len(text) <= limit else text[: limit - 3] + "..."


def parse_events(lines):
    events, transcript, tools, result, session = [], [], [], {}, None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(ev)
        session = ev.get("session_id", session)
        kind = ev.get("type")
        if kind == "assistant":
            for part in (ev.get("message") or {}).get("content") or []:
                if isinstance(part, dict) and part.get("type") == "text" and part.get("text", "").strip():
                    transcript.append(f"**Agent:** {part['text'].strip()}")
        elif kind == "tool_call" and ev.get("subtype") == "started":
            name, args = tool_name(ev.get("tool_call"))
            tools.append(name)
            transcript.append(f"`TOOL {len(tools)}: {name}` {summarize(args)}")
        elif kind == "result":
            result = ev
    return events, transcript, tools, result, session


def cmd_models(a):
    out = sh([agent_bin(a.agent_bin), "models"])
    print(out.stdout or out.stderr)


def cmd_run(a):
    if not TASK.exists() or not HIDDEN.exists():
        sys.exit("Run this from the caseStudyRun folder (cursor-task/ and cursor-eval/ must sit beside it).")
    binary = agent_bin(a.agent_bin)
    RUNS.mkdir(exist_ok=True)
    rows = read_log()
    manifest_path = RUNS / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for model in a.models:
        run_id = f"run{len(manifest) + 1}"
        folder = RUNS / run_id
        repo = folder / "repo"
        folder.mkdir()
        fresh_repo(repo)
        print(f"[{run_id}] {model}: running...", flush=True)
        cmd = [binary, "-p", "--output-format", "stream-json", "--model", model, "--force", "--trust",
               "--workspace", str(repo), PROMPT]
        start = time.perf_counter()
        proc = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=a.timeout)
        wall = time.perf_counter() - start
        (folder / "events.ndjson").write_text(proc.stdout, encoding="utf-8")
        if proc.stderr.strip():
            (folder / "stderr.txt").write_text(proc.stderr, encoding="utf-8")
        _, transcript, tools, result, session = parse_events(proc.stdout.splitlines())

        sh(["git", "add", "-A"], cwd=repo)
        stat = sh(["git", "diff", "--cached", "--shortstat"], cwd=repo).stdout
        diff = sh(["git", "diff", "--cached"], cwd=repo).stdout
        (folder / "diff.patch").write_text(diff, encoding="utf-8")
        files = int(m.group(1)) if (m := re.search(r"(\d+) files? changed", stat)) else 0
        added = int(m.group(1)) if (m := re.search(r"(\d+) insertion", stat)) else 0
        removed = int(m.group(1)) if (m := re.search(r"(\d+) deletion", stat)) else 0
        vis_pass, vis_total, _ = pytest_counts(repo / "tests", repo)
        hid_pass, _, hidden_text = pytest_counts(HIDDEN, repo)
        (folder / "hidden_tests.txt").write_text(hidden_text, encoding="utf-8")

        breakdown = {}
        for t in tools:
            breakdown[t] = breakdown.get(t, 0) + 1
        row = {
            "run": run_id, "model": model, "wall_time_s": f"{wall:.1f}",
            "agent_duration_s": f"{result.get('duration_ms', 0) / 1000:.1f}" if result else "",
            "tool_calls": len(tools), "tool_breakdown": "; ".join(f"{k}={v}" for k, v in breakdown.items()),
            "visible_passed": vis_pass, "visible_total": vis_total, "hidden_passed_of_9": hid_pass,
            "lines_added": added, "lines_removed": removed, "files_changed": files,
        }

        if a.self_report and session:
            rep = sh([binary, "-p", "--output-format", "json", "--model", model, "--mode", "ask", "--trust",
                      "--workspace", str(repo), "--resume", session, SELF_REPORT_PROMPT], cwd=repo)
            est = extract_json(json.loads(rep.stdout).get("result", "") if rep.stdout.strip().startswith("{") else "")
            (folder / "self_report.json").write_text(json.dumps(est, indent=2), encoding="utf-8")
            row.update({
                "self_est_wall_time_s": est.get("estimated_wall_time_s", ""),
                "self_est_tokens": est.get("estimated_total_tokens", ""),
                "self_est_tool_calls": est.get("estimated_tool_calls", ""),
                "self_confidence": est.get("confidence_all_requirements_met", ""),
            })

        header = (f"# {run_id}: {model}\n\nWall time {row['wall_time_s']} s · {len(tools)} tool calls · "
                  f"visible tests {vis_pass}/{vis_total} · hidden tests {hid_pass}/9 · +{added}/-{removed} lines\n\n"
                  f"**User:** {PROMPT}\n\n")
        (folder / "transcript.md").write_text(header + "\n\n".join(transcript) + "\n", encoding="utf-8")
        (folder / "results.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
        rows[run_id] = row
        manifest[run_id] = model
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        write_log(rows)
        print(f"[{run_id}] done: {row['wall_time_s']} s, {len(tools)} tool calls, hidden {hid_pass}/9", flush=True)
    print(f"\nLogged to {LOG}. Add tokens and cost from your Cursor usage dashboard.")


def cmd_grade(a):
    binary = agent_bin(a.agent_bin)
    manifest = json.loads((RUNS / "manifest.json").read_text())
    rows = read_log()
    for run_id, model in manifest.items():
        if model == a.grader:
            print(f"[{run_id}] skipped: the grader wrote this run; grade it with a different model.")
            continue
        folder = RUNS / run_id
        hidden = (folder / "hidden_tests.txt").read_text(encoding="utf-8")[-3000:]
        diff = (folder / "diff.patch").read_text(encoding="utf-8")[:20000]
        prompt = GRADER_PROMPT.replace("<<TASK>>", PROMPT).replace("<<HIDDEN>>", hidden).replace("<<DIFF>>", diff)
        print(f"[{run_id}] grading with {a.grader}...", flush=True)
        out = sh([binary, "-p", "--output-format", "json", "--model", a.grader, "--mode", "ask", "--trust",
                  "--workspace", str(folder / "repo"), prompt], cwd=folder / "repo")
        text = json.loads(out.stdout).get("result", "") if out.stdout.strip().startswith("{") else out.stdout
        grade = extract_json(text)
        (folder / f"grade_{re.sub(r'[^A-Za-z0-9._-]', '_', a.grader)}.json").write_text(
            json.dumps(grade or {"raw": text}, indent=2), encoding="utf-8")
        row = rows.get(run_id, {"run": run_id, "model": model})
        row.update({
            "grader_model": a.grader,
            "spec_correctness": grade.get("spec_correctness", ""), "code_quality": grade.get("code_quality", ""),
            "scope_discipline": grade.get("scope_discipline", ""), "would_merge_as_is": grade.get("would_merge_as_is", ""),
            "grader_verdict": grade.get("one_line_verdict", ""),
        })
        rows[run_id] = row
        write_log(rows)
    print(f"Grades added to {LOG}.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--agent-bin", help="path to the Cursor CLI if it isn't on PATH")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("models")
    r = sub.add_parser("run")
    r.add_argument("--models", nargs="+", required=True)
    r.add_argument("--self-report", action="store_true", help="after each timed run, ask the model to estimate its own cost")
    r.add_argument("--timeout", type=int, default=1800)
    g = sub.add_parser("grade")
    g.add_argument("--grader", required=True)
    a = p.parse_args()
    {"models": cmd_models, "run": cmd_run, "grade": cmd_grade}[a.cmd](a)


if __name__ == "__main__":
    main()
