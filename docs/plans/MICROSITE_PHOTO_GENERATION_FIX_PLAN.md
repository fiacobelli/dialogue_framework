# Microsite Photo and Generation Fix Plan

Date: 2026-05-27

## Scope

This plan covers the Samsung tablet tester feedback related to:

- donor page generation appearing to freeze after photo upload,
- unclear photo slot guidance,
- unnecessary photo move controls,
- redundant or confusing photo/generation buttons,
- recovery behavior when generation is blocked.

Speech timing and natural pause handling are intentionally out of scope for this plan. That should be handled as a separate speech-interaction plan after the photo/generation flow is stable.

## Production Incident Summary

The Samsung tablet session did not fail because of a server crash or photo upload failure.

Session:

`17d332d7-41c1-468c-92c5-e447b0815e19`

Visit:

`88cb8533-b4c7-4a32-9a95-b7592778f335`

Observed production behavior:

- The interview reached `COMPLETE`.
- Three photos uploaded successfully.
- Photo metadata updates returned `200`.
- Repeated `/microsite/api/generate` requests returned `409`.
- No donor page draft was created.

Backend response:

```json
{
  "error": "generation_not_ready",
  "missing": ["story_evidence"],
  "missing_story_sections": ["identity"],
  "photo_count": 3,
  "max_photos": 3,
  "phase": "COMPLETE"
}
```

Root cause:

The interview flow allowed the user to proceed to the photo stage, but the generation gate still required accepted identity evidence. The tester gave identity-related answers, but those answers were classified as too thin and not accepted as generation-ready story evidence. This created a state mismatch:

`interview complete` + `photos complete` + `identity evidence missing`

The UI then made the failure feel like a freeze because generation stayed blocked and the user-facing recovery path was weak.

## Current Evidence From Logs

What worked:

- Samsung tablet voice transcription worked in this session.
- There were 16 `transcribe_started` events and 16 `transcribe_ended` events.
- There were no `transcribe_error` events.
- Three photos were saved in the database.
- Photo roles were assigned as `before`, `during`, and `hope`.

What failed:

- `donor_page_drafts` had no draft for this visit.
- `/api/generate` repeatedly returned `409`.
- The user could repeatedly attempt generation instead of being clearly guided back to the missing story requirement.

## Goals

1. Prevent the app from reaching a dead-end state where the interview appears complete but generation is blocked.
2. Make photo guidance obvious before upload, not only after upload.
3. Reduce unnecessary controls and decision points in the photo stage.
4. Make generation errors visible, actionable, and recoverable.
5. Keep the implementation compact and avoid broad refactoring.

## Non-Goals

- Do not change speech silence timing in this fix.
- Do not build a Flutter wrapper in this fix.
- Do not add AI photo analysis in this fix.
- Do not redesign the whole donor page template in this fix.

## Fix 1: Resolve Interview Completion vs Generation Gate Mismatch

Issue:

The backend can mark the story complete even when `story_evidence_ready()` later rejects generation because required identity evidence is missing.

Why it matters:

This is the core cause of the freeze-like experience. A user should not be sent to the photo stage if the backend already knows the donor page cannot be generated.

Recommended solution:

Before transitioning to photos, validate generation evidence readiness or run a lighter pre-generation readiness check. If required evidence is missing, ask one targeted recovery question before closing the interview.

For this incident, the recovery question should be identity-specific:

`Before we move to photos, can you share one more detail about who you are outside of kidney disease, such as family, work, school, community, or something you enjoy?`

Implementation notes:

- The fix should live in the interview flow, not only in the frontend.
- The frontend should not guess whether evidence is sufficient.
- If a section is intentionally skipped, the generation gate should treat the skip as acceptable.
- If a user gives a thin but usable identity answer, the system should either accept it or ask the recovery question before photos.

Likely files:

- `web/interview_flow.py`
- `web/microsite.py`
- `tests/test_interview_flow.py`

Success criteria:

- A session cannot enter the photo/generation stage while `story_evidence_ready()` would return missing required sections.
- The test case based on the Samsung tablet session does not end in generate-time `409`.
- Generation is either allowed or the user is asked a clear recovery question before photos.

## Fix 2: Make Generate Failure Actionable

Issue:

When generation is blocked, the UI only shows a status message. On tablet, this can feel like a freeze, especially after repeated generate attempts.

Recommended solution:

Show a clear recovery panel or message near the generate button when `/api/generate` returns `generation_not_ready`.

Suggested copy:

`I need one more detail before I can draft the page. Please add a short detail about: who you are outside of kidney disease.`

For now, the recovery can be typed in a small text box or can route the user back to the interview input. The cleanest first implementation is to prevent this state via Fix 1, but the UI should still handle it defensively.

Likely files:

- `static/js/App.js`
- `static/js/UIController.js`
- `templates/interview.html`
- `tests/test_interview_flow.py`

Success criteria:

- A `409 generation_not_ready` response does not look like a frozen page.
- The generate button is re-enabled after failure.
- The user sees exactly what is missing.

## Fix 3: Redesign Photo Slot Meaning

Issue:

The current interface does not clearly tell users what each of the three photos is for. Labels only appear after photos are uploaded, inside a dropdown.

Recommendation:

Use fixed guided slots:

1. `Who I am`
2. `My kidney journey`
3. `My hope after transplant`

Reasoning:

`Before / During / After` is not quite right because the patient has not had the transplant yet. `After` can imply a completed future. `My hope after transplant` is more accurate and emotionally appropriate.

Suggested slot descriptions:

- `Who I am`: A photo that shows your life, personality, family, work, school, community, or something meaningful to you.
- `My kidney journey`: A photo that helps show what treatment, dialysis, appointments, or daily life with kidney disease has been like.
- `My hope after transplant`: A photo that represents what you hope to return to, do again, or experience with a transplant.

Likely files:

- `templates/interview.html`
- `templates/upload_mobile.html`
- `static/js/UIController.js`
- `web/routes_photos.py`
- `web/microsite.py`
- `tests/test_interview_flow.py`

Success criteria:

- Empty photo slots show their purpose before upload.
- Mobile upload page shows the same slot meanings.
- Generated donor page captions use the same language.

## Fix 4: Remove Move Left / Move Right Photo Controls

Issue:

Move left/right is no longer useful if slots have fixed meanings. It adds cognitive load and makes the workflow feel more like editing a gallery than telling a story.

Recommended solution:

- Remove `Move left` and `Move right` buttons from uploaded photo cards.
- Remove the related click handler if no longer used.
- Preserve backend display order for existing photos.
- Keep replacement behavior by clicking a photo slot.

Likely files:

- `static/js/UIController.js`
- `static/js/App.js`
- `static/css/avatar.css`

Success criteria:

- Uploaded photo cards no longer show move controls.
- Slot click-to-replace still works.
- Photo order remains stable.

## Fix 5: Simplify Photo and Generation Buttons

Issue:

The photo stage currently has several actions that can feel redundant:

- clickable photo slots,
- `Upload Photos From This Device`,
- `Continue with uploaded photos`,
- `Generate My Donor Page`.

Recommended solution:

- Keep clickable slots as the primary upload action.
- Keep one explicit upload button as secondary accessibility/support action, but label it clearly.
- Hide `Continue with uploaded photos` unless the user has uploaded 1-2 photos.
- After 3 photos are uploaded, show one primary action: `Review and Draft My Donor Page`.
- Disable the generate button while generation is in progress.
- Re-enable it on failure with an actionable message.

Suggested copy:

- Main photo heading: `Choose photos for your donor page`
- Upload button: `Choose Photos From This Device`
- Generate button after 3 photos: `Review and Draft My Donor Page`
- Partial photo button: `Continue with these photos`

Likely files:

- `templates/interview.html`
- `static/js/App.js`
- `static/js/UIController.js`
- `static/css/avatar.css`

Success criteria:

- Users have one obvious next action at each step.
- Generate cannot be spam-clicked while a request is active.
- Partial-photo continuation is visible only when relevant.

## Recommended Execution Order

1. Add a regression test for the Samsung tablet session failure: story complete, 3 photos, missing identity evidence, generation blocked.
2. Fix the interview/generation gate mismatch so the user cannot reach photos when required evidence is missing.
3. Improve frontend generation failure handling as a defensive fallback.
4. Update photo slot labels and descriptions on desktop and mobile.
5. Remove move left/right controls and related frontend code.
6. Simplify the button states and generation loading state.
7. Run tests locally.
8. Commit, push, deploy, and retest on the Samsung tablet.

## Deferred Follow-Up: Speech Timing

The tester's feedback about natural pauses is valid, but it should be handled separately because it changes the speech interaction model.

Known current behavior:

- VAD speech-end waits about 3 seconds before transcription.
- Initial no-speech timeout is about 3.5 seconds.
- After repeated empty detections, the app submits a no-response turn.

This should be investigated and planned separately with real tablet testing, because making the app wait longer can improve reflective speech but may also make the app feel slower if tuned poorly.

