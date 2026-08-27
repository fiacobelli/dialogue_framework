# SDOH Screening Task 2 Dataset

This folder contains the Task 2 analysis assets for the AMIA poster work.

Task 2 goal:
- Export the production cohort messages.
- De-identify patients.
- Tag assistant turns with topic/theme and question number.
- Link patient answers to the preceding assistant prompt.
- Identify factual repeated-visit examples for the Results section.

## Folder Layout

- `raw/`: local-only production exports from `https://ludi.a4hlab.org/admin`.
- `processed/`: de-identified outputs generated from the raw export.
- `task2_export_summary.md`: counts, workbook structure, and manual-review steps.

## Privacy Rule

Do not publish raw exports. They include production patient identifiers.

The `processed/` files replace patient IDs with labels such as Patient A and redact detected names from message text. Review before sharing outside the project.

## Rebuild

Run from the repo root:

```bash
python3 scripts/analysis/build_task2_exports.py
```

