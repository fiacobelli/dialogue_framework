# Microsite Foundation Final Plan

Date: 2026-05-26

Reviewed plan source:

```text
docs/plans/MICROSITE_FOUNDATION_REVIEW_PLAN.md
```

Critical review incorporated from review agent:

```text
Aristotle
```

## Purpose

This is the final foundation plan before any new implementation work. The goal is to stop symptom-level patching and stabilize the transplant microsite around the actual root causes:

- Patient privacy and data lifecycle are not yet strong enough for broader field use.
- Patient-session authorization relies too heavily on session IDs.
- The interview still treats some conversational repair turns as story evidence.
- Story generation is limited by weak evidence assembly, not only prompt wording.
- Frontend and database files are oversized, but broad refactoring should not come before semantic fixes.
- Mobile upload and browser behavior need real device validation, not only Python tests.

This plan is intentionally not a feature wishlist. It defines what to keep, improve, remove/simplify, fix before adding features, and defer until the foundation is stronger.

## Current State

Current branch:

```text
bernard
```

Current local head:

```text
8c59e85 Improve microsite conversation and mobile uploads
```

Important deployment state:

```text
8c59e85 is pushed but was not confirmed deployed.
The last confirmed live EC2 commit was d5989c8.
```

Important file pressure points:

```text
web/database.py           1329 lines
static/js/App.js           822 lines
static/js/UIController.js  549 lines
templates/microsite.html   496 lines
web/routes_api.py          490 lines
web/interview_flow.py      477 lines
```

Important repo hygiene concern:

```text
docs/ and tests/ appear to be ignored by .gitignore.
Runtime artifacts should stay ignored, but project plans and tests should be tracked intentionally.
```

## What We Should Keep

### Keep Code-Owned Interview State

Keep `web/interview_flow.py` as the owner of interview phase, step order, completion, skip behavior, and photo transition. The LLM should phrase patient-facing speech, not own workflow decisions.

Preserve:

- Deterministic interview phases.
- Deterministic final transition to photos.
- Backend generation gate.
- Backend publication gate.
- Outgoing-turn contract.
- Bounded LLM usage for phrasing/evaluation/generation.

### Keep Review Before Publish

The patient must review and approve the page before it becomes public.

Preserve:

- Draft before publish.
- Review/edit screen.
- Publication consent.
- Controlled public page serving.
- Controlled public photo serving.
- Unpublish/delete workflows.

### Keep Database Observability

The current SQLite foundation is valuable and should not be thrown away.

Preserve:

- Visits.
- Messages.
- Turn events/timing.
- Photos.
- Drafts.
- Consents.
- Audit events.
- Upload tokens.
- Session snapshots.

### Keep Tokenized QR Upload

The QR upload concept is right because it ties mobile uploads to a visit/session instead of relying only on filenames.

Preserve:

- Per-visit upload tokens.
- Token expiry.
- Token revocation.
- DB photo slot reservation.
- DB photo metadata.

### Keep Grounded Generation

The donor page must stay grounded in patient-provided evidence.

Preserve:

- No invented medical facts.
- No invented family details.
- No invented motivations.
- No manipulative donor language.
- Content moderation before publication.

## What We Should Improve

### Improve Privacy And Data Lifecycle First

The current delete/unpublish behavior is not enough. It soft-deletes database state and removes generated HTML, but uploaded photo files, raw logs, pickle user models, and session-state blobs may remain.

Improve:

- Define soft-delete vs hard-delete semantics.
- Decide what must be retained for research/audit and what must be removed.
- Ensure deleted sessions cannot serve photos from any route, including private preview.
- Ensure delete behavior covers database rows, generated HTML, uploaded photo files, logs, `user_models/*.pkl`, and `session_state` blobs.
- Add tests proving deleted content is inaccessible.

### Improve Patient-Session Security

Several patient lifecycle APIs depend primarily on knowing the session ID. That is not strong enough once real patient data and public pages are involved.

Improve:

- Add a patient-session capability token or equivalent authorization model.
- Protect private preview URLs.
- Protect desktop uploads, not only mobile uploads.
- Protect publish/unpublish/delete actions.
- Ensure upload tokens cannot be reused after completion, publication, deletion, or expiration.

### Improve Conversation Semantics

The root conversation issue is not just repeated phrases. The current flow can record a repair/prior-reference statement as story evidence because evidence recording happens before a richer turn interpretation layer exists.

Improve:

- Add a pre-advancement turn interpreter.
- Classify turns before `_record_story_evidence`.
- Detect direct answers, thin answers, prior-reference answers, corrections, refusal/skip, clarification requests, operational issues, emotional disclosures, and off-topic turns.
- Do not store "I already mentioned that" as fresh story evidence.
- If prior evidence is sufficient, acknowledge it and advance.
- If prior evidence is not sufficient, ask a specific clarification without sounding repetitive.

### Improve Story Evidence Assembly

The generated page can still feel bare even when the interview captured useful details. The issue is not only prompt wording; it is also how evidence is organized before generation.

Improve:

- Build a structured evidence packet before generation.
- Separate accepted evidence, skipped sections, rejected/operational turns, corrections, and follow-up answers.
- Identify strongest details: relationships, values, timeline, activities, support network, daily impact, hopes, and direct quotes.
- Track richness, not only whether a required group exists.
- Add a policy for too many skipped/thin sections before generation.

### Improve Frontend Workflow Contracts

The frontend currently owns too many workflow decisions. It should render a backend workflow state rather than reconstructing rules from scattered flags.

Improve:

- Add a backend workflow-status response.
- Include phase, progress, required actions, allowed actions, photo state, publication state, consent requirements, and errors.
- Make UI components render from that status.
- Reduce frontend duplication of backend business rules.

## What We Should Remove Or Simplify

### Remove Phrase-List Fixes As The Main Strategy

Phrase lists can be guardrails, but they should not be the primary conversation engine.

Replace with:

- Intent categories.
- Structured turn interpretation.
- Evidence-aware state decisions.
- Transcript-based tests.

### Simplify Session Storage Over Time

The current model uses in-memory sessions, pickle files, database snapshots, and normalized tables. This is acceptable as a bridge, but it increases privacy and debugging risk.

Simplify toward:

- Database-backed session state as the durable source.
- Pickle compatibility as temporary fallback only.
- Clear deletion behavior across all session artifacts.

### Simplify File Growth Strategy

Do not start with broad refactoring just because files are large. Refactor only to create seams for root fixes first.

Create seams for:

- `turn_interpreter`.
- `evidence_packet`.
- `data_lifecycle` / takedown cleanup.
- `workflow_status`.
- Patient-session authorization.

Broader file-size cleanup should follow once behavior is characterized.

### Simplify Generated Artifact Handling

Generated patient artifacts should not be mixed with source files unless intentionally kept as fixtures.

Simplify toward:

- Runtime photos/pages/logs ignored by Git.
- Source templates and tests tracked by Git.
- Test fixtures stored intentionally and scrubbed.

## What Must Be Fixed Before Adding New Features

## P0: Deployment And Repo Hygiene

Goal:
Know exactly what code is live and make plans/tests trackable.

Work:

- Confirm local head, GitHub branch, and EC2 commit.
- Deploy `8c59e85` only after the team agrees it should be the current baseline.
- Fix GitHub-to-EC2 authentication using a deploy key or scoped token.
- Keep runtime artifacts ignored.
- Stop ignoring `docs/` and `tests/` if these are intended project assets, or force-add selected plans/tests intentionally.
- Add a short deploy checklist: local test, commit, push, deploy, health check, browser smoke test, database/log review.

Exit criteria:

- The live health endpoint reports the expected commit.
- Plans and tests that matter are version-controlled intentionally.
- Deployment no longer depends on ad hoc bundle transfer except emergency fallback.

## P0: Privacy, Deletion, And Data Lifecycle

Goal:
Make sure patient data cannot remain accessible accidentally.

Work:

- Document all PHI-bearing storage:
  - SQLite tables.
  - uploaded photos.
  - generated HTML.
  - logs.
  - `user_models/*.pkl`.
  - session-state blobs.
  - LLM prompt/response payloads.
- Define soft-delete and hard-delete behavior.
- Update delete/takedown behavior to clear or block:
  - public page route.
  - public photo route.
  - private photo preview route.
  - uploaded photo files if hard-delete is required.
  - upload tokens.
  - session snapshots.
  - pickle files.
  - logs, or document retained logs explicitly.
- Add tests for deleted sessions:
  - public page unavailable.
  - public photo unavailable.
  - private preview unavailable.
  - upload token revoked.
  - session cannot be rehydrated into a deleted usable state.

Exit criteria:

- Deleted content cannot be served by any route.
- The team can explain what remains after delete and why.
- Tests prove the expected lifecycle behavior.

## P0/P1: Patient-Session Security

Goal:
Stop treating session ID alone as sufficient authority for sensitive patient actions.

Work:

- Design a patient-session capability token.
- Require it for private preview, desktop upload, publish, patient unpublish, and patient delete.
- Keep mobile upload tokens scoped to photo upload only.
- Revoke patient/session capabilities after delete.
- Add expiry or rotation strategy.
- Keep admin actions separately authenticated and audited.

Exit criteria:

- Knowing a session ID is not enough to upload, preview private photos, publish, unpublish, or delete.
- Tokens are scoped by purpose.
- Tests cover unauthorized and expired-token behavior.

## P1: Conversation Root Fix

Goal:
Fix the interview semantics, not just the wording.

Work:

- Create a `turn_interpreter` seam before evidence recording.
- Return structured categories:
  - `answer`.
  - `thin_answer`.
  - `prior_reference`.
  - `correction`.
  - `skip`.
  - `clarification_request`.
  - `operational_issue`.
  - `emotional_disclosure`.
  - `off_topic`.
- Change `decide_next_task` so `_record_story_evidence` only records evidence-worthy turns.
- For `prior_reference`, inspect existing evidence for the current or related step.
- If existing evidence is enough, acknowledge that and advance.
- If evidence is missing, ask a specific non-repetitive clarification.
- Add transcript fixtures from real sessions.

Exit criteria:

- "I already mentioned that" is not stored as new evidence.
- The assistant can use prior evidence instead of blindly asking again.
- Follow-up answers are not treated as checklist completions when they are actually corrections or refusals.
- Tests prove classification, evidence recording, and next-task behavior.

## P1: Story Evidence And Generation Quality

Goal:
Make donor pages better by improving source evidence structure before generation.

Work:

- Create an `evidence_packet` builder.
- Include per-section accepted evidence, skipped status, thin status, corrections, direct quotes, and strongest details.
- Add a richness summary.
- Update generation to consume the evidence packet.
- Update prompt to use the packet rather than relying on a flat transcript.
- Add generation tests using a rich real-like transcript.
- Add tests that generic/manipulative phrases are rejected or avoided.

Exit criteria:

- Generated pages use concrete patient-specific details.
- Thin evidence is surfaced before generation.
- Skipped sections do not silently produce generic filler.
- Unsupported details are not invented.

## P1: Mobile Upload And UX Validation

Goal:
Validate the actual patient workflow, not just backend upload functions.

Work:

- Test phone QR upload on a real phone.
- Test Samsung tablet browser flow.
- Test selecting three photos at once.
- Test replacing each photo.
- Test desktop sync after phone upload.
- Test expired/revoked upload link behavior.
- Add Playwright/mobile-browser tests if feasible.
- If browser tests are not feasible immediately, maintain a manual device checklist.

Exit criteria:

- Multi-select uploads all selected photos in order.
- Replacement replaces the intended slot.
- Desktop updates after phone upload.
- Mobile page fits the viewport.
- Patient does not need hidden scrolling for core actions.

## P1/P2: Admin And Operational Security

Goal:
Make staff/admin controls safe enough for supervised testing.

Work:

- Remove default `dev-secret` risk in deployed environments.
- Require secure `FLASK_SECRET_KEY`.
- Add secure cookie settings for production.
- Add CSRF protection for admin POST actions.
- Add login failure logging and rate limiting if feasible.
- Audit admin login/logout/failure, unpublish, delete, and review actions.
- Consider separate staff accounts if more than one staff member will use admin.

Exit criteria:

- Admin state-changing actions are protected against accidental/cross-site submission.
- Production cannot run with default Flask secret.
- Admin actions are auditable.

## P1/P2: Database And Migration Discipline

Goal:
Make future schema changes safe for field-test data.

Work:

- Add schema version tracking.
- Add migration history.
- Add backup/restore instructions before migrations.
- Add migration tests.
- Keep opportunistic `_ensure_columns()` only as a temporary prototype tool.
- Split `web/database.py` only around stable seams after lifecycle/security changes are defined.

Exit criteria:

- Schema changes are repeatable.
- Existing field-test data can be upgraded safely.
- Database code is no longer a single growing catch-all file.

## P2: Frontend Structure And Workflow Status

Goal:
Make the UI easier to reason about and less fragile.

Work:

- Add backend workflow-status contract.
- Split frontend around stable responsibilities:
  - interview controller.
  - photo controller.
  - publication controller.
  - API/telemetry client.
  - conversation UI.
  - photo UI.
  - review/publication UI.
- Move mobile upload JavaScript out of inline template after behavior is stable.
- Keep files below roughly 500 lines.

Exit criteria:

- Frontend renders backend workflow state instead of duplicating core rules.
- Future UI bugs are traceable to smaller modules.
- No large file absorbs unrelated behavior by default.

## P2: Field Testing Review Workflow

Goal:
Make session review after patient testing routine and reliable.

Work:

- Add or document a compact session review command/report.
- Include visit status, phase, turns, photos, draft status, publication status, errors, VAD/mic issues, and generation details.
- Include prompt/model version for generation.
- Include whether the session used fallback behavior.

Exit criteria:

- After a field session, review does not require ad hoc database digging.
- Failures can be classified quickly.

## What To Add Only After The Foundation Is Stronger

Defer these until the P0/P1 foundation is stable:

- Flutter wrapper.
- Analytics dashboard.
- Deidentified research export.
- Additional donor-page themes.
- Photo caption suggestions.
- AI photo role recommendations.
- Multi-language donor-story flow.
- Advanced social sharing.
- Automated story-quality scoring beyond basic richness checks.

## Final Recommended Sequence

### Phase 0: Baseline And Safety

1. Confirm local/GitHub/EC2 commit alignment.
2. Fix repo hygiene for docs/tests.
3. Deploy or intentionally hold `8c59e85`.
4. Establish reliable deploy/health workflow.
5. Define privacy/data lifecycle behavior.
6. Close private-preview-after-delete and session rehydration risks.

### Phase 1: Authorization And Lifecycle

1. Add patient-session capability model.
2. Protect private preview, desktop upload, publish, unpublish, and delete.
3. Strengthen admin/session security.
4. Add lifecycle tests for delete/unpublish/access.

### Phase 2: Conversation Semantics

1. Add `turn_interpreter`.
2. Prevent repair/prior-reference turns from becoming story evidence.
3. Add real transcript fixtures.
4. Update state transitions around prior evidence, corrections, refusals, and operational issues.

### Phase 3: Evidence And Generation

1. Add `evidence_packet`.
2. Add richness and skipped/thin-section policy.
3. Generate from structured evidence.
4. Improve donor-page output only after the evidence packet is stable.

### Phase 4: UX And Mobile Validation

1. Validate phone QR flow.
2. Validate Samsung tablet flow.
3. Add browser/mobile tests or a maintained manual device checklist.
4. Improve no-scroll and full-screen completion UX.

### Phase 5: Targeted Refactor

1. Split only around stable seams.
2. Reduce `web/database.py`, `static/js/App.js`, and `static/js/UIController.js`.
3. Keep route files from becoming orchestration catch-alls.

### Phase 6: Future Enhancements

Only after the above gates are stable:

- Flutter.
- Analytics.
- Export tools.
- New page templates.
- Advanced AI features.

## Non-Goals For The Next Implementation Plan

Do not prioritize:

- More hardcoded phrase bans as the main conversation fix.
- More donor-page visual polish before evidence quality is fixed.
- Flutter before web/tablet reliability is proven.
- Broad refactoring before root semantic and privacy risks are addressed.
- Analytics before data semantics and retention are clear.

## Final Position

The next implementation plan should start with safety and semantic correctness, not new features.

Recommended order:

```text
baseline/deploy hygiene
-> privacy/data lifecycle
-> patient-session security
-> turn interpretation
-> structured evidence packet
-> mobile/UX validation
-> targeted refactor
-> future enhancements
```

This order directly addresses the review agent's strongest concerns and reduces the risk of another round of whack-a-mole fixes.
