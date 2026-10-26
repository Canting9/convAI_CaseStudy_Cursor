# Cursor Case Study (Fair A, A4)

ECE 6256 / CS 6604 Conversational AI, Fall 2026. Team: Greyson, Michael, Heeba, Canting.
Written case study due Wed Oct 28, 11:59 pm; fair Thu Oct 29.

## What's here

| Folder | Contents |
| --- | --- |
| `docs/` | Assignment handout, the team brief (two versions), Michael's policy + interfaces section |
| `slides/` | The 8-slide PowerPoint deck and who presents each slide |
| `caseStudyRun/` | Our measured experiment: the task repo, hidden tests, harness, logs |

## Who owns what

| Member | Section and slides | Still open |
| --- | --- | --- |
| Greyson | Understanding + state (slides 2, 3) | Review slide 3's diagram and numbers |
| Michael | Policy + interfaces (slides 4, 5) | Annotated transcript on slide 5, from one run |
| Heeba | Seams + economics (slide 6) | "$20 Pro buys" column, from run costs |
| Canting | Measured behavior + verdict (slides 7, 8) | Results table, screenshot sequence, verdict line |

## Running the experiment

See `caseStudyRun/RUN_PROTOCOL.md`. Short version, from `caseStudyRun/`:

```
python harness.py models
python harness.py run --models <model-1> <model-2> <model-3> composer-2 --self-report
python harness.py grade --grader <a model that did not write the runs>
```

Needs the Cursor CLI (`agent`) logged in and `pip install pytest`. Results land in `caseStudyRun/harness_log.csv`; add tokens and cost from your Cursor usage dashboard. Manual runs go in `caseStudyRun/runs_log.csv`. Run 1 (Grok, manual) is logged there, with its diff in `caseStudyRun/manual_runs/`.

Two rules so the runs stay fair:

- Don't edit `caseStudyRun/cursor-task/`. It is the untouched starting code every run copies.
- Don't open `caseStudyRun/` as a Cursor workspace; `cursor-eval/` holds the hidden tests.
