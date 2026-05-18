# Microsite Conversation Remediation Plan

Date: 2026-05-17

## Purpose

Fix the transplant microsite experience so it behaves like a real donor-story interview, not a thin question-and-answer script that jumps to page generation too early.

This plan responds to the live test run from session:

```text
531ebdb0-f63d-484f-850b-ac6706b1016d
```

Observed failure:

```text
USER: most of the time treatments dialysis treatment
FLOW_TASK: close_to_photos phase=PHOTOS step=None
LLM: The dialysis treatment has become a regular part of your routine, Sophia - that can be overwhelming. How would receiving a kidney transplant change your life?
_is_goodbye check: True
PHASE CHANGED TO: PHOTOS
```

The assistant asked a question, but the backend still moved to photo upload. That is the root class of bug this plan must eliminate.

## Reviewed By

A review agent was asked to critique the initial plan harshly. Its main corrections are included here:

- Do not commit `PHOTOS` before the final spoken response is known to be a true close.
- Do not rely on question-mark detection as a final-transition guard.
- Remove or tightly scope phrase-based goodbye detection.
- Add server-side generation gates, not just frontend sequencing.
- Use per-question story sufficiency rules, not generic keyword matching.
- Treat name capture as deterministic state, not LLM inference.
- Add frontend speech-cutoff verification, especially around final close and photo transition.
- Add review/edit before publishing a sensitive donor page.

## Current Root Causes

### 1. State Advances Too Early

`web/interview_flow.py` mutates the interview state before the LLM response is validated. Then `/api/chat` returns the mutated phase. This lets the app enter `PHOTOS` even when the assistant response is still asking a question.

Target invariant:

```text
If API returns phase=PHOTOS, the spoken response must be a deterministic photo-upload transition, not an LLM-generated question.
```

### 2. No Follow-Up Policy

Every user answer currently advances the story. Short answers like `okay`, `yes I do`, or vague fragments are accepted as complete.

The microsite needs a donor-story version of screening's follow-up logic, but stronger: story sufficiency must be based on the specific evidence needed for each donor-page section.

### 3. Name Is Unsafe

The user said:

```text
hi my name is
```

The generated page still used `Sophia`. The app likely let the LLM infer or hallucinate the name.

Target invariant:

```text
Generated donor pages must use a stored, confirmed patient name or fall back to neutral wording. They must never guess a name.
```

### 4. Opening Flow Is Wrong

The opening is displayed on page load and waits for a generic click before speaking. It also asks for a broad self-introduction even though the stored state says it is awaiting `name`.

Target opening flow:

```text
begin button -> spoken introduction -> ask name -> confirm readiness -> story interview
```

### 5. LLM Prompt Is Too Broad

`prompts/interviewer.txt` lists many donor-story questions. The runtime directive asks for one current step, but the LLM can drift into a different question from the broader list.

### 6. Generation Is Too Easy To Trigger

`/api/generate` can generate a page even if the interview is incomplete, the name is missing, or the story is too thin. The frontend sequence is not enough protection.

### 7. UI States Do Not Match Product States

The interface says it is creating a donor page while the story is still incomplete. The manual name field, auto-generation, photo upload, and generated page state are not clearly separated.

## Target Product Flow

The microsite should follow this state model:

```text
AVATAR_SELECTED
INTRO
AWAITING_NAME
CONFIRM_NAME
READINESS
STORY_MAIN
STORY_FOLLOWUP
FINAL_DETAILS
STORY_REVIEW
PHOTOS
GENERATING
PAGE_REVIEW
PUBLISHED
```

The practical implementation can use simpler internal names, but these product states must be represented clearly in backend state and frontend UI.

## Backend Design

### Phase 1: Add Observability First

Add structured logging before changing behavior.

Log per turn:

- `session_id`
- previous state
- user input
- stored patient name and source
- current story step
- sufficiency decision
- follow-up decision
- chosen task type
- generated response
- response classification
- next state
- transition reason
- whether generation is allowed

This makes future failures diagnosable from logs without guessing.

### Phase 2: Replace Simple Step Advancement

Replace `step_index`-only advancement with a state-machine helper in `web/interview_flow.py`.

Required task types:

```text
ask_name
repair_name
confirm_name
ask_readiness
answer_readiness_question
ask_main
ask_followup
ack_then_next
ask_final
close_to_photos
already_complete
```

The state machine must not blindly advance on every answer. It should evaluate the answer against the current state.

### Phase 3: Deterministic Name Capture

Add deterministic name extraction and confirmation.

Rules:

- If the answer contains a clear name, store it as `patient_name`.
- If the answer is incomplete, such as `hi my name is`, ask again.
- If the answer is ambiguous, ask for clarification.
- Do not use LLM extraction as the primary name source.
- Do not generate with an unconfirmed name.
- Allow name correction before generation.

Suggested stored fields:

```text
patient_name
patient_name_status: missing | captured | confirmed | corrected
patient_name_source: user_explicit | user_confirmed | manual_edit | fallback
```

### Phase 4: Readiness And Start Consent

Add a readiness phase similar to screening, but with microsite-specific wording.

The assistant should explain:

- It will ask about the patient's life, kidney journey, hopes, and message to possible donors.
- The goal is to help create a donor webpage.
- The patient can skip questions or correct anything.
- The patient should say when they are ready to begin.

Handle readiness answers:

- `yes`, `ready`, `okay`, `sure`: start story interview.
- `not yet`, `wait`, `no`: pause and ask what they need.
- `what is this for`: explain again briefly.
- silence or unclear answer: ask one repair question.

Avoid calling this legal consent unless the product explicitly needs consent tracking. Use patient-facing language like `ready to begin`.

### Phase 5: Per-Question Story Sufficiency

Add donor-story sufficiency criteria by step. Generic word count is not enough.

Minimum evidence examples:

```text
personal_background:
  Needs at least one identity detail: family role, work, community, hobby, value, or place.

medical_history:
  Needs timing, diagnosis context, dialysis start, or explicit uncertainty.

daily_life:
  Needs a concrete impact: dialysis schedule, fatigue, activity limits, emotions, work, family, or independence.

transplant_hope:
  Needs a concrete life change: energy, travel, family moment, work, independence, hobbies, or future goal.

donor_message:
  Needs a direct message, value, reason to consider donation, or explicit request for help wording.

support_network:
  Needs support people/community or explicit no-support statement.

final_details:
  Needs final addition, tone preference, quote/story, or explicit nothing else.
```

Follow-up policy:

- If the answer is short, vague, or missing required evidence, ask one targeted follow-up for the same step.
- If the follow-up is still thin, either ask one repair question if the story would be unusable, or store `thin_evidence=true` and generate conservatively.
- Do not treat broad words like `dialysis`, `treatment`, or `family` as sufficient by themselves.
- Emotional disclosures should be acknowledged gently and followed with a concrete, optional question.

### Phase 6: Deterministic Final Close

The final transition must be deterministic.

Rules:

- Remove phrase-based goodbye completion for normal story flow.
- `_is_goodbye()` must not move the app to `PHOTOS` unless the current task is already a final task.
- `close_to_photos` should return a deterministic response, not an LLM-generated response.
- The API must only return `phase=PHOTOS` with this deterministic photo-upload instruction.

Example close:

```text
Thank you for sharing your story with me. The story part is complete, and the next step is to add up to three photos that you may want on your donor page.
```

This avoids the exact logged failure where the assistant asked a question and the app advanced anyway.

### Phase 7: Server-Side Generation Gates

Add backend validation to `/api/generate`.

Generation should require:

- confirmed or manually entered `patient_name`
- story interview complete
- no pending story question
- sufficient story evidence or explicit thin-story override
- photo requirement satisfied or explicitly skipped/deferred

If blocked, return a structured error:

```json
{
  "error": "story_incomplete",
  "message": "We still need one more detail before creating the page.",
  "missing": ["transplant_hope"]
}
```

Do not rely on frontend UI to prevent invalid generation.

### Phase 8: Generated Page Safety

Update `prompts/microsite.txt`.

Rules:

- Use only details supported by the transcript or stored story evidence.
- Do not invent hobbies, children, work, personality traits, city details, or family moments.
- If details are thin, write conservative copy.
- Use stored `patient_name`; do not infer a name.
- Avoid overclaiming emotional details not stated by the patient.

Add a generated-page review step before publish/share:

```text
PAGE_REVIEW -> PUBLISHED
```

The patient should be able to:

- view generated text
- edit name
- regenerate
- approve/publish

## Frontend Design

### Phase 9: Replace Passive Opening With Begin Overlay

Current behavior:

```text
page loads -> opening appears as text -> generic click starts speech
```

Target behavior:

```text
page loads -> begin overlay -> user clicks Begin -> session starts -> Ludi speaks intro
```

This solves browser autoplay restrictions because `Begin` is the user gesture.

Required UI:

- Begin button
- short pre-start copy
- no story prompt visible before speech starts
- speech starts immediately after button click

### Phase 10: Align UI With Real States

Wording should match the current state:

```text
INTRO/NAME/READINESS: Tell Your Story
STORY_MAIN/FOLLOWUP: Story Interview
FINAL_DETAILS: Final Details
PHOTOS: Add Photos
GENERATING: Creating Your Donor Page
PAGE_REVIEW: Review Your Donor Page
PUBLISHED: Your Donor Page Is Ready
```

Remove the confusing manual name field from the normal generation path. Replace it with a name confirmation/edit control only when needed.

Add visible progress:

- story section count
- current section label
- clear indication when story interview is complete

### Phase 11: Speech Cutoff Verification

The final close must be spoken fully before photo UI appears.

Frontend requirements:

- `startPhotoFlow()` runs only after `speechManager.speak(finalClose)` resolves.
- Do not call `speechManager.destroy()` until final close speech finishes.
- Verify pause/resume and barge-in do not leave stale promises.
- Verify VAD restarts only after Ludi finishes speaking.
- Verify SitePal readiness fallback does not silently skip opening audio.

## Prompt Design

### Interview Prompt

Reduce `prompts/interviewer.txt` so it does not compete with runtime directives.

Keep:

- role/persona
- tone
- safety limits
- patient-facing style rules

Move step order and step questions into code-owned runtime directives.

Runtime directive should define:

- task type
- current step
- required evidence
- whether this is main question or follow-up
- whether to acknowledge, ask, repair, or close

### Follow-Up Style

Follow-ups should be open and concrete:

```text
Tell me a little more about what that looks like day to day.
What is one thing you miss being able to do?
How has that affected time with your family?
What would you want someone reading your page to understand about that?
```

Do not overuse:

```text
Can you elaborate?
Could you explain more?
```

## Testing Plan

### Unit Tests

Create tests for `web/interview_flow.py`.

Required cases:

- incomplete name: `hi my name is`
- clear name: `my name is Sophia`
- name correction
- readiness yes
- readiness no/not yet
- readiness question: `what is this for`
- short answer triggers follow-up
- vague dialysis answer does not satisfy daily-life by keyword alone
- sufficient daily-life answer advances
- sufficient transplant-hope answer advances
- final answer leads to deterministic close
- no phrase-based early `PHOTOS`
- existing old state normalizes safely

### Goal/API Tests With Fake LLM

Add fake-provider tests for adversarial LLM behavior:

- LLM asks a question during final close
- LLM says `thank you for sharing your story` early
- LLM ignores runtime directive
- LLM hallucinates a name
- LLM returns response with no `?` but still asks a question indirectly

Expected result:

- backend state remains valid
- `PHOTOS` only occurs with deterministic close
- name is not guessed

### Frontend Manual Tests

Browser checks on localhost before EC2:

- Begin button starts audio.
- Opening is spoken after Begin.
- Ludi asks for name only.
- Incomplete name triggers repair.
- Readiness happens before story questions.
- Short answers trigger follow-up.
- Final close is fully spoken before photo UI appears.
- Mic/VAD does not start while Ludi is speaking.
- Pause/resume works.
- Photo upload appears only after story completion.
- Generate is blocked until backend allows it.

### Live Verification

After local testing and commit/push:

```text
EC2 pull -> restart microsite.service -> live browser test
```

Check:

- `/microsite`
- `/microsite/interview?avatar=black_female`
- `/microsite/api/session`
- `/microsite/api/chat`
- `/microsite/api/generate` blocked when incomplete
- generated page URLs under `/microsite/site/...`
- photos under `/microsite/photos/...`

## Implementation Order

### Commit 1: Logging And Flow Tests

Files likely touched:

```text
web/interview_flow.py
web/goal_interview.py
tests/test_interview_flow.py
```

Deliverables:

- structured logs
- failing tests that capture the current bad behavior
- old-state normalization tests

### Commit 2: Intake, Name, Readiness, Sufficiency

Files likely touched:

```text
web/interview_flow.py
web/goal_interview.py
prompts/interviewer.txt
tests/test_interview_flow.py
tests/test_goal_interview.py
```

Deliverables:

- deterministic name capture
- readiness phase
- per-step sufficiency
- follow-up/repair behavior
- no blind step advancement

### Commit 3: Final Close And Generation Gates

Files likely touched:

```text
web/goal_interview.py
web/routes_api.py
web/microsite.py
prompts/microsite.txt
tests/test_goal_interview.py
tests/test_generation_gates.py
```

Deliverables:

- deterministic photo transition
- phrase-based goodbye removed or scoped
- `/api/generate` validates name, story, and photo readiness
- generated copy cannot invent unsupported details

### Commit 4: Frontend Begin Flow And UI State Alignment

Files likely touched:

```text
templates/interview.html
static/js/App.js
static/js/UIController.js
static/css/avatar.css
```

Deliverables:

- Begin overlay
- opening speaks immediately after Begin click
- clearer state labels and progress
- no premature photo UI
- final close completes before speech teardown

### Commit 5: Review/Edit Before Publishing

Files likely touched:

```text
templates/interview.html
static/js/App.js
static/js/UIController.js
static/css/avatar.css
web/routes_api.py
web/microsite.py
```

Deliverables:

- generated page review state
- edit name/content controls or minimal correction path
- publish/share only after review

## Acceptance Criteria

The fix is complete only when all of these are true:

- The assistant does not move to photos while asking a story question.
- Short/vague answers trigger a same-topic follow-up.
- A donor page is not generated from an incomplete or thin story without explicit handling.
- The app does not invent a patient name.
- Opening audio starts from a clear Begin action.
- The user is asked for readiness before story questions.
- The final close is spoken completely before photo upload appears.
- `/api/generate` rejects incomplete sessions server-side.
- Generated copy only uses supported transcript details.
- The patient sees a review step before publish/share.

## Workflow

Follow the project workflow:

```text
local changes -> commit -> push -> localhost test -> EC2 pull -> restart -> live verification
```

Do not deploy any implementation phase before local verification.

