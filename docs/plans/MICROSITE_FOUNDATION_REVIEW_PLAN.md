# Microsite Foundation Review Plan

Date: 2026-05-26

## Purpose

This document is a review checkpoint before creating another implementation plan. The goal is not to keep adding features. The goal is to identify what is already solid, what is fragile, what should be simplified, and what must be fixed before the transplant microsite becomes harder to maintain.

The current product is a working prototype with meaningful progress: it can run an avatar-led donor-story interview, collect photos, generate a draft donor page, require review and publication consent, serve public pages through controlled routes, and record useful database telemetry. The current risk is that repeated patches are starting to hide deeper product and architecture issues.

## Current State Summary

Current branch:

```text
bernard
```

Current local head:

```text
8c59e85 Improve microsite conversation and mobile uploads
```

Important deployment note:

```text
8c59e85 is pushed but was not confirmed deployed during the last review.
The live EC2 service was last confirmed at d5989c8.
```

Current file-size pressure points:

```text
web/database.py           1329 lines
static/js/App.js           822 lines
static/js/UIController.js  549 lines
templates/microsite.html   496 lines
web/routes_api.py          490 lines
web/interview_flow.py      477 lines
```

The backend interview files are close to the preferred size limit but still understandable. The frontend and database layers are too large and should not absorb more feature patches without being split.

## What Already Exists

### Interview Flow

- `web/interview_flow.py` owns the interview state, phase transitions, story step order, follow-up count, skip handling, final transition to photos, and outgoing-turn contract.
- `web/interview_answer_analysis.py` provides deterministic guards for names, readiness, short answers, skip intent, operational issues, and sufficiency.
- `web/goal_interview.py` connects the deterministic state machine to the LLM and logs interview turns.
- `web/interview_flow_config.py` contains story steps, questions, progress labels, section transitions, and follow-up configuration.

### Story Generation

- `web/microsite.py` builds the donor page result.
- `prompts/microsite.txt` constrains the LLM to use only supported patient evidence.
- Generation is blocked unless the backend says story, name, and photo requirements are ready.
- The patient can review/edit the generated draft before publishing.

### Photos

- `web/routes_photos.py` handles desktop and mobile uploads.
- Uploads are tied to visits and upload tokens.
- Photos have database records, slots, source metadata, roles, ordering, and replacement support.
- The mobile upload page supports QR-based upload into the desktop session.

### Publication And Admin

- Publication requires explicit publication consent.
- Public pages and photos are served only when database publication status allows it.
- Unpublish and soft-delete workflows exist.
- Admin routes exist for review, unpublish, and delete.

### Database And Sessions

- SQLite stores visits, messages, turn events, photos, drafts, consents, audit events, upload tokens, and session snapshots.
- Session state can be rehydrated from the database if in-memory state or pickle files are unavailable.
- Structured logs and lifecycle events exist.

### Tests

- Tests cover interview flow, generation gates, consent, publication status, unpublish/delete, admin auth, session rehydration, photo slot reservation, upload rejection, and recent conversation/mobile upload regressions.
- The latest local full test suite after `8c59e85` was reported as passing with 69 tests.

## What Is Working Well And Should Be Kept

### Keep Code-Owned State

The strongest design choice is that code owns the interview contract. The LLM should make the agent sound natural, but it should not decide when the interview is complete, when to move to photos, whether publication is allowed, or whether a session is safe to publish.

Keep:

- Deterministic interview phases.
- Deterministic photo transition.
- Deterministic generation gate.
- Deterministic publication gate.
- Bounded LLM use for language, evaluation, and story generation.

### Keep Review Before Publish

The donor page is sensitive. The patient must remain in control before anything becomes public.

Keep:

- Draft generation before publication.
- Review/edit screen.
- Publication consent requirement.
- Controlled serving of public pages and photos.
- Unpublish and delete workflows.

### Keep Database-Backed Observability

The database foundation is valuable for debugging, research review, and field testing.

Keep:

- Visit records.
- Message records.
- Turn timing/events.
- Photo records.
- Draft records.
- Consent records.
- Audit events.
- Session snapshots.

### Keep Upload Token Model

QR upload should remain tokenized and tied to the active visit. This is the right foundation for multiple simultaneous users.

Keep:

- Per-visit upload tokens.
- Token expiry.
- Token revocation after publication/delete.
- DB-owned photo slot reservation.

### Keep Grounded Generation Rules

The donor page must be emotionally useful without inventing medical details, family facts, motivations, or promises.

Keep:

- Grounded generation.
- Unsupported-fact restrictions.
- Content moderation before publication.
- Tests for risky language and unsupported details.

## What Should Be Improved

### Conversation Quality

The current interview still behaves too much like a checklist. The root issue is not only wording. The root issue is that the flow is step-index-driven and mostly treats each answer as belonging only to the current question.

Improve:

- Add a conversation interpretation layer before state advancement.
- Classify each patient turn as direct answer, thin answer, already-mentioned reference, correction, refusal/skip, clarification request, operational issue, emotional disclosure, or off-topic.
- Use prior story evidence when the patient says something like "I already mentioned that."
- Avoid treating conversational repair statements as new story evidence.
- Make the assistant respond to what the patient actually said before moving on.

The important principle: do not solve this with a bigger phrase list. Use intent categories, structured decisions, real transcript fixtures, and deterministic state transitions.

### Story Evidence Assembly

The generated donor page can still feel bare because the generation layer receives the interview as relatively flat evidence. The system needs a clearer evidence packet before asking the LLM to write the page.

Improve:

- Build a structured story evidence packet by section.
- Separate accepted evidence, rejected/operational turns, skipped sections, corrections, and follow-up answers.
- Track strongest concrete details: relationships, values, activities, timeline, daily impact, support network, hopes, and direct quotes.
- Add a richness score or readiness summary before generation.
- If evidence is thin, ask one respectful story-building follow-up before generation, not after the page is already dull.

### Frontend Maintainability

The frontend has absorbed too much responsibility in a small number of files.

Improve:

- Split `static/js/App.js` into smaller controllers.
- Split `static/js/UIController.js` into focused UI modules.
- Move mobile upload behavior out of inline template JavaScript when stable.
- Keep future files below roughly 500 lines unless there is a strong reason.

### Database Maintainability

`web/database.py` is doing too much. It now contains schema creation, migrations, visits, messages, photos, drafts, consents, upload tokens, admin queries, audit events, and session snapshots.

Improve:

- Split database responsibilities into smaller modules or a `web/db/` package.
- Keep a stable public database API so route files do not need large rewrites.
- Add clearer migration discipline.
- Document which tables contain PHI.

### Deployment Reliability

The GitHub-to-EC2 deployment path has been unreliable due to authentication issues.

Improve:

- Fix EC2 GitHub authentication using a deploy key or scoped token.
- Avoid manual bundle deployments except as emergency fallback.
- Make health/version checks part of every deploy.
- Confirm whether local head, GitHub branch, and EC2 service commit match before testing.

## What Should Be Removed Or Simplified

### Remove Phrase Whack-A-Mole

Do not keep adding one-off phrase bans as the main method for improving conversation. Phrase bans can be useful as guardrails, but they do not solve the root problem.

Simplify toward:

- Intent classification.
- Structured turn interpretation.
- Transcript-based regression tests.
- State-machine decisions that understand correction, refusal, and prior evidence.

### Simplify Canned Transition Logic

Recent work moved some transition language from deterministic canned text to the LLM. That helps surface-level repetition, but it does not fully solve the deeper issue.

Simplify toward:

- Code decides what must happen next.
- LLM writes the transition under a strict outgoing-turn contract.
- The transition prompt includes the patient detail being acknowledged, the reason for the next step, and the exact next question.

### Simplify Frontend State Ownership

The UI should not guess product state from scattered flags. It should render from backend state where possible.

Simplify toward:

- Backend returns explicit phase/progress/photo/publication state.
- Frontend renders those states.
- Frontend avoids duplicating core business rules.

### Simplify Generated Artifact Handling

The repo should be checked for generated public microsite artifacts or sample pages that may not belong in Git.

Simplify toward:

- Runtime-generated pages/photos stored outside Git-managed source files.
- Static templates and source assets remain in Git.
- Generated patient artifacts excluded unless deliberately kept as fixtures.

### Simplify Session Storage Over Time

The current hybrid model of in-memory session, pickle files, database snapshots, and normalized database rows is understandable as a bridge. Long-term, it is confusing and increases privacy risk.

Simplify toward:

- Database-backed session state as the primary durable source.
- Pickle compatibility only as a temporary migration bridge.
- Clear deletion behavior across all session artifacts.

## What Must Be Fixed Before Adding New Features

### Urgent Fixes

1. Deploy and validate the latest pushed commit.

`8c59e85` contains important fixes for conversation transitions and mobile multi-photo upload. The live service should not be evaluated against older code.

2. Confirm mobile upload behavior on a real phone.

The recent bug where selecting three photos populated only the last one was a root logic bug in the mobile selection loop. It needs live validation after deploy.

3. Add regression tests from the latest real session.

Use the session where the patient said "I did mention it before" as a fixture. The system should not treat that as fresh evidence, should acknowledge prior context, and should not repeat stock phrases.

4. Stabilize GitHub-to-EC2 deployment.

Before more product changes, the team needs a reliable path: local change, test, commit, push, deploy, health check, browser test.

5. Re-test generation quality with a known rich transcript.

The donor page should use concrete details from a rich session. If it still outputs generic content, the issue is evidence assembly and generation design, not just prompt wording.

## What Should Be Added Only After The Foundation Is Stronger

### Future Enhancements

These are useful, but they should not be implemented until the urgent foundation work is stable:

- Flutter wrapper or tablet app shell.
- Analytics dashboard.
- Deidentified research export pipeline.
- Multi-language donor-story interview.
- Photo caption suggestions.
- AI-assisted photo role recommendations.
- Multiple donor-page design themes.
- Social sharing previews beyond basic metadata.
- Advanced story quality scoring.

## Prioritized Workstreams

## 1. Urgent Stabilization

Priority:

```text
P0
```

Goal:
Make sure the current product works as intended before adding more.

Work:

- Confirm local, GitHub, and EC2 commits.
- Deploy latest pushed commit if not already live.
- Run health/version checks.
- Run local tests.
- Run one desktop test and one real-phone QR upload test.
- Verify three-photo multi-select, individual replacement, desktop sync, and photo status updates.
- Review database records after test.
- Capture any failures as test fixtures.

Exit criteria:

- Live service reports expected commit.
- Mobile upload works with selecting three photos at once.
- Desktop session updates after phone upload.
- Generated page uses the uploaded photos in the expected roles/order.
- No new server errors in logs.

## 2. Cleanup And Simplification

Priority:

```text
P0/P1
```

Goal:
Stop adding product behavior into files that are already too large.

Work:

- Split `web/database.py` by responsibility while preserving public function names during the first pass.
- Split `static/js/App.js` into interview, photo, publication, and API/telemetry modules.
- Split `static/js/UIController.js` into conversation, photo, review, and publication UI modules.
- Keep `web/routes_api.py` from growing beyond its current size by moving helper logic out before adding new route behavior.
- Move mobile upload JavaScript to a static module after the upload behavior is stable.

Exit criteria:

- No main application file is growing as the default place for new behavior.
- Tests still pass after module splits.
- Function ownership is easier to trace.

## 3. UX Improvements

Priority:

```text
P1
```

Goal:
Make the product feel calm, clear, and usable for dialysis patients who may not be able to scroll or troubleshoot.

Work:

- Keep agent messages short enough to fit without awkward scrolling.
- Avoid initial text flashes before the avatar starts speaking.
- Make upload status visible on both desktop and phone.
- Make photo replacement obvious by allowing users to click the photo slots directly.
- Make completion/page-ready state full-screen and clear.
- Keep progress language non-redundant.
- Validate responsive layout on desktop, phone, and Samsung tablet.

Exit criteria:

- A patient can complete the flow without needing hidden scrolling.
- The phone upload page fits the viewport.
- Photo sync status is obvious.
- The final page-ready screen is not cramped by the avatar split view.

## 4. AI And Interview Improvements

Priority:

```text
P1
```

Goal:
Make the interview conversational without giving the LLM unsafe control.

Work:

- Add a structured turn interpreter before state advancement.
- Classify patient turns into clear categories.
- Add handling for "I already said that", corrections, refusals, and operational issues.
- Use prior evidence memory in follow-up decisions.
- Store why an answer was accepted, rejected, skipped, or treated as repair.
- Add transcript fixtures from real tests.
- Build a structured evidence packet for generation.
- Improve generation using structured evidence rather than only broad prompt wording.

Exit criteria:

- The assistant responds to the substance of the latest answer.
- The assistant can gracefully handle a patient saying the information was already provided.
- Follow-ups feel grounded in the patient's own words.
- The generated page contains concrete patient-specific details without unsupported claims.

## 5. Database And Session Improvements

Priority:

```text
P1/P2
```

Goal:
Make session data reliable, queryable, and safe to operate.

Work:

- Keep DB-backed snapshots as the durable source of session recovery.
- Reduce dependence on pickle files over time.
- Add or document migrations for every schema change.
- Add a compact query/report for session review after field tests.
- Track model/prompt version used for generation.
- Consider a normalized story evidence table only after the evidence packet design is stable.

Exit criteria:

- A session can be reconstructed after restart.
- Field-test review does not require ad hoc Python snippets.
- Generated page output can be traced to prompt/model/version and source evidence.

## 6. Privacy And Safety Improvements

Priority:

```text
P1/P2
```

Goal:
Reduce avoidable risk before broader patient use.

Work:

- Document which tables and files contain PHI.
- Decide retention and deletion policy for visits, messages, photos, drafts, logs, and generated pages.
- Confirm whether collection/storage/photo-use consent is needed separately from publication consent.
- Ensure delete/unpublish covers photos, pages, drafts, upload tokens, and session snapshots.
- Review what raw LLM prompts/responses are stored and whether any can be minimized.
- Strengthen admin authentication before broader production use.

Exit criteria:

- The team can explain what data is stored, why it is stored, who can access it, and how it is deleted.
- Public content cannot remain accessible after unpublish/delete.
- Consent language matches the actual workflow.

## 7. Future Enhancements

Priority:

```text
P3
```

Goal:
Add value only after the core workflow is stable.

Candidates:

- Flutter wrapper.
- Research dashboard.
- Deidentified export.
- More donor-page templates.
- Social sharing improvements.
- Photo caption assistance.
- Multilingual support.
- Better analytics around drop-off and answer richness.

Exit criteria:

- Core interview, upload, generation, review, publish, and deletion flows are reliable first.

## Recommended Sequence Before Final Implementation Planning

### Step 1: Stabilize What Is Already Built

Do this before conversation redesign:

- Deploy latest pushed commit.
- Validate mobile upload and desktop sync.
- Confirm live commit.
- Review one clean database session.

Reason:
We should not plan against stale production behavior.

### Step 2: Stop File Growth

Do this before more behavioral patches:

- Split oversized frontend/database files.
- Keep route and flow files below the maintainability threshold.

Reason:
The next changes will be harder and riskier if they are added into oversized files.

### Step 3: Redesign Conversation At The Root

Do this before adding more follow-up wording:

- Add turn interpretation.
- Add repair/correction/prior-reference handling.
- Add transcript-based tests.

Reason:
The current problem is not just repeated phrases. It is that the system does not fully understand what kind of turn the patient just gave.

### Step 4: Redesign Story Evidence Assembly

Do this before more donor-page polish:

- Convert transcript into structured evidence.
- Track concrete details and rejected turns.
- Generate from that packet.

Reason:
A stronger page requires better source material organization, not just a prettier template.

### Step 5: Then Improve Design And Future Features

Do this after the foundation is stable:

- Improve templates.
- Add analytics.
- Consider Flutter.
- Add advanced AI features.

Reason:
These are useful only if the core interview and publication system is reliable.

## Non-Goals For The Next Implementation Plan

The next implementation plan should not focus on:

- Adding another donor-page template before evidence quality is solved.
- Adding more hardcoded phrases as the main conversation fix.
- Adding Flutter before web/tablet behavior is stable.
- Adding analytics dashboards before data semantics are stable.
- Adding new publication features before consent, deletion, and admin workflows are verified.

## Decision Questions Before Final Implementation Plan

1. Should the next phase start with deployment validation of `8c59e85`, or should we first refactor oversized local files before deploying more?
2. Should conversation redesign be implemented as a new `turn_interpreter` module rather than more edits inside `interview_flow.py`?
3. Should story generation wait until a structured evidence packet exists?
4. Should database refactoring happen before or after the conversation redesign?
5. Should collection/storage/photo-use consent be added now, or is publication consent enough for the current supervised testing workflow?

## Recommended Position

The safest path is:

```text
stabilize current live build
-> split oversized files enough to prevent more complexity
-> implement structured turn interpretation
-> implement structured story evidence assembly
-> improve donor-page output
-> then consider future enhancements
```

This avoids another round of symptom fixes and keeps the product moving toward a stable, testable, patient-safe tool.
