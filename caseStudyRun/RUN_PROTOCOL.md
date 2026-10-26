# Cursor run protocol (Fair A, A4)

One fixed task, four runs: three frontier models plus Composer 2. One run doubles as the annotated-transcript exhibit.

## Folders

- `cursor-task/`: the repo the agent works on. Every run starts from its FIRST commit, whatever is checked out.
- `cursor-eval/test_hidden.py`: 9 held-out tests the agent never sees.
- `harness.py`: runs, measures, logs and grades automatically (below).
- `harness_log.csv`: written by the harness. `runs_log.csv`: your manual runs, left alone.

## Automated runs (recommended)

Needs the Cursor CLI (`agent`) logged in and `pip install pytest`. Check flags with `agent --help` if anything errors.

```
cd caseStudyRun
python harness.py models
python harness.py run --models <model-1> <model-2> <model-3> composer-2 --self-report
python harness.py grade --grader <a model that did not write the runs>
```

What each step does:

1. **run**: for each model, makes a fresh copy of the base repo in `runs/runN/repo`, runs the exact prompt headless (`agent -p --output-format stream-json --model ... --force`), and times it. It then logs wall time, the agent's own `duration_ms`, every tool call by type, visible and hidden test results, and diff size. It saves `events.ndjson` (raw), `transcript.md` (readable, every tool call numbered) and `diff.patch`.
2. **--self-report**: after the timed run, resumes the same chat in read-only Ask mode and asks the model to estimate its own time, tokens and tool calls, plus its confidence. This runs after the timer stops, so it doesn't change the measured run. Comparing its guesses with the measured numbers is a result in itself.
3. **grade**: a second model reads each run's diff and hidden-test output in read-only Ask mode and scores spec correctness, code quality and scope (0 to 5), plus merge Y/N. Run folders are named run1, run2, ..., so the grader isn't told which model wrote the code; it skips any run it wrote itself. The model mapping is in `runs/manifest.json`.

The CLI doesn't report tokens or cost: copy those from your Cursor usage dashboard into `harness_log.csv`.

## The prompt (built into the harness; paste exactly for manual runs)

```
In this repo, add late fees to the library. A loan is late for each day after its due date until it is returned (or until `today` if it's still out). Charge 25 cents per late day, capped at $10.00 per loan. Premium members get their first 3 late days free on each loan. Add `Library.fees_owed(member_id, today)` returning the total in cents as an int, and add fees to each line of the `report` CLI output in the form `, fees $X.YZ`. Keep existing behavior working and make the tests pass.
```

## Manual runs (in the editor)

1. `git checkout main` (your base branch), then `git checkout -b run-<model>`.
2. New chat, Agent mode, pick the model by name (not Auto). Don't switch models mid-chat.
3. Paste the prompt and time it; don't step in (if it asks, reply `Use your best judgment.`).
4. Save the transcript, and copy tokens and cost from the usage dashboard.
5. Score it:
   ```
   git add -A
   git commit -m "agent run"
   git diff main --shortstat
   copy ..\cursor-eval\test_hidden.py tests\
   python -m pytest -q
   del tests\test_hidden.py
   ```
6. Log it in `runs_log.csv`.

## Send back

`harness_log.csv` (with tokens and cost added), `runs_log.csv`, the `runs/` folder (or just each `transcript.md` and grade file), and 4 screenshots of one run for Canting's slide.
