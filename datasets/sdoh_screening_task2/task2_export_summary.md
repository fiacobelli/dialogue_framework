# Task 2 Export Summary

Date: 2026-08-27
Source: production admin export from `https://ludi.a4hlab.org/admin`

## Raw Files

Raw exports are stored in:

`/home/bbofori/projects/TRANSPLANT/dialogue_framework/datasets/sdoh_screening_task2/raw/`

Files:
- `sdoh-screening-cohort.db`
- `screening_cohort_messages.csv`
- `screening_cohort_visits.csv`
- `screening_cohort_referrals.csv`
- `screening_cohort_patients.csv`
- `private_patient_key.csv`

The private key maps production patient IDs to Patient A, Patient B, etc. Do not share it in the poster or with anyone who should not see identifiers.

## Processed Files

Processed outputs are stored in:

`/home/bbofori/projects/TRANSPLANT/dialogue_framework/datasets/sdoh_screening_task2/processed/`

Files:
- `task2_annotated_messages.xlsx`
- `candidate_results_examples.md`

## Export Counts

- Patients in cohort export: 16
- Visits: 90
- Messages: 1,690
- Assistant messages: 852
- User messages: 838
- Referrals: 62
- Candidate repeated-topic/theme examples: 72
- Assistant rows needing manual review: 132

## Workbook Sheets

- `README`: source and privacy notes.
- `annotated_messages`: all messages with de-identified patient labels and topic tags.
- `linked_answers`: user answers linked to the preceding assistant prompt.
- `candidate_examples`: top repeated-topic/theme examples for Results review.
- `referrals_deidentified`: care-team recommendation text by de-identified patient and visit.
- `question_bank`: source questions from `prompts/questions.txt`.
- `topic_summary`: assistant-turn counts by turn type, theme, topic, and question number.

## Manual Review Steps

1. Review rows marked `needs_review=yes` in `annotated_messages`.
2. Review the top rows in `candidate_examples`.
3. Choose one candidate where the same patient gave a longer answer on a later visit.
4. Confirm the assistant prompt and patient answer are appropriate to quote.
5. Pull the care-team/social-worker recommendation for the same patient and visit.
6. Add the example to Results using only factual language.

## Results Writing Rule

The Results section should state what happened. It should not interpret why it happened.

Acceptable:

`Patient A gave a 1-word answer on Visit 7 and a 43-word answer on Visit 8 in response to Family and Friends Satisfaction prompts.`

Avoid:

`Patient A became more comfortable with the system.`
