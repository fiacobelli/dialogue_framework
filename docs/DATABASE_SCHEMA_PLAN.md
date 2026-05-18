# TRANSPLANT Microsite Database Plan

## Purpose

The microsite builder needs durable, queryable records for the donor-page interview lifecycle. The database should help us answer:

- What happened in each interview?
- Where did users pause, struggle, or drop off?
- Which questions produce thin answers?
- Do follow-ups improve answer quality?
- How long does each interaction step take?
- What draft was generated, reviewed, and published?

This plan is intentionally microsite-specific. It should not copy the screening schema blindly.

## Current State

The microsite currently stores data in several non-queryable places:

- In-memory Flask sessions.
- Pickle files in `user_models/{session_id}.pkl`.
- Text logs in `logs/interview_{session_id}.txt`.
- Uploaded photos in `photos/`.
- Published donor-page HTML in `static/microsites/`.

This is enough for basic operation, but not enough for analysis, recovery, or reliable audit of the donor-page creation process.

## Database Choice

Use local SQLite first: `db/transplant.db`.

Reasons:

- The app currently runs as one Flask service on one EC2 instance.
- PHI should stay on our server.
- SQLite is simple, reliable, and already proven in the sibling screening project.
- The schema can later migrate to PostgreSQL or self-hosted Supabase if traffic, concurrency, or reporting needs grow.

Do not use hosted Supabase at this stage. The previous Supabase plan in this file was based on older phases and old avatar IDs, and it adds infrastructure before we have stable local capture.

## Privacy Rules

- Do not store audio.
- Do not store arbitrary browser metadata.
- Do not store raw user filenames as trusted paths.
- Keep the database file out of git.
- Keep pickle compatibility temporarily, but avoid adding new duplicate PHI surfaces.
- Treat messages, drafts, photos, logs, pickle files, and generated HTML as PHI-bearing artifacts.
- Add retention, backup, restore, and deletion procedures before production research use.

## Core Schema

### `visits`

One row per donor-page interview session.

Fields:

- `id TEXT PRIMARY KEY`: internal visit UUID, separate from the browser session ID.
- `session_id TEXT UNIQUE`: Flask/session correlation ID.
- `language TEXT`.
- `avatar_id TEXT`.
- `avatar_profile_json TEXT`.
- `phase TEXT`: `WELCOME`, `INTRO`, `STORY`, `FINAL_DETAILS`, `PHOTOS`, `COMPLETE`.
- `awaiting TEXT`: current expected user input, such as `name`, `readiness`, `main_answer`, `followup_answer`, `photos`.
- `patient_display_name TEXT`.
- `patient_name_status TEXT`: `missing`, `confirmed`, `corrected`.
- `patient_name_source TEXT`: `user_explicit`, `manual_edit`, `review_edit`.
- `current_step_id TEXT`.
- `last_task_type TEXT`.
- `last_decision_json TEXT`.
- `story_complete INTEGER DEFAULT 0`.
- `photo_count INTEGER DEFAULT 0`.
- `draft_status TEXT`: `none`, `draft`, `published`.
- `total_user_turns INTEGER DEFAULT 0`.
- `total_assistant_turns INTEGER DEFAULT 0`.
- `user_agent TEXT`.
- `started_at TEXT`.
- `updated_at TEXT`.
- `completed_at TEXT`.
- `published_at TEXT`.

Indexes:

- `idx_visits_started_at`
- `idx_visits_phase`
- `idx_visits_draft_status`
- `idx_visits_session_id`

### `messages`

One row per user or assistant message.

Fields:

- `id TEXT PRIMARY KEY`.
- `visit_id TEXT NOT NULL REFERENCES visits(id) ON DELETE CASCADE`.
- `turn_number INTEGER NOT NULL`.
- `role TEXT NOT NULL`: `user`, `assistant`, or `system`.
- `content TEXT NOT NULL`.
- `phase TEXT`.
- `awaiting TEXT`.
- `task_type TEXT`.
- `step_id TEXT`.
- `probe_depth INTEGER`: `0` for main answer, `1` for follow-up answer.
- `followup_count INTEGER`.
- `sufficiency_reason TEXT`.
- `sufficiency_json TEXT`.
- `input_modality TEXT`: `voice`, `typed`, `system`, or `unknown`.
- `response_latency_ms INTEGER`: time from assistant speech ending to user answer start or typed send.
- `answer_duration_ms INTEGER`: time from user answer start to recognition end, or first keystroke to send for typed input.
- `answer_word_count INTEGER`.
- `answer_char_count INTEGER`.
- `speech_confidence REAL`.
- `no_response INTEGER DEFAULT 0`.
- `retry_count INTEGER DEFAULT 0`.
- `client_sent_at TEXT`.
- `llm_latency_ms INTEGER`: assistant generation time.
- `tts_duration_ms INTEGER`: assistant speech start to speech end.
- `message_word_count INTEGER`.
- `message_char_count INTEGER`.
- `created_at TEXT`.

Constraints:

- Unique `(visit_id, turn_number, role)` if one user and one assistant message are stored per turn.

Indexes:

- `idx_messages_visit_turn`
- `idx_messages_step_id`
- `idx_messages_task_type`
- `idx_messages_created_at`

### `turn_events`

Allowlisted browser-side event timeline. This supports detailed timing analysis without accepting arbitrary client metadata.

Fields:

- `id TEXT PRIMARY KEY`.
- `visit_id TEXT NOT NULL REFERENCES visits(id) ON DELETE CASCADE`.
- `message_id TEXT REFERENCES messages(id) ON DELETE CASCADE`.
- `turn_number INTEGER`.
- `event_type TEXT NOT NULL`.
- `client_ts_ms INTEGER NOT NULL`.
- `metadata_json TEXT DEFAULT '{}'`.
- `created_at TEXT`.

Allowed `event_type` values:

- `tts_started`
- `tts_ended`
- `vad_fired`
- `recognition_started`
- `recognition_ended`
- `empty_input`
- `typed_started`
- `typed_sent`
- `pause_clicked`
- `resume_clicked`
- `repeat_clicked`
- `mic_error`

Allowed metadata keys:

- `source`
- `reason`
- `state`
- `duration_ms`

Reject or drop all other metadata keys server-side.

### `photos`

One row per uploaded image. The image itself stays on disk.

Fields:

- `id TEXT PRIMARY KEY`.
- `visit_id TEXT NOT NULL REFERENCES visits(id) ON DELETE CASCADE`.
- `stored_filename TEXT NOT NULL`.
- `display_order INTEGER NOT NULL`.
- `source TEXT`: `desktop`, `mobile`, or `unknown`.
- `mime_type TEXT`.
- `byte_size INTEGER`.
- `sha256 TEXT`.
- `width INTEGER`.
- `height INTEGER`.
- `uploaded_at TEXT`.
- `deleted_at TEXT`.

Constraints:

- Unique `(visit_id, display_order)`.
- App-level max of 3 active photos per visit.

### `donor_page_drafts`

One row per generated or reviewed draft version.

Fields:

- `id TEXT PRIMARY KEY`.
- `visit_id TEXT NOT NULL REFERENCES visits(id) ON DELETE CASCADE`.
- `version INTEGER NOT NULL`.
- `status TEXT`: `draft`, `reviewed`, `published`, `superseded`.
- `name TEXT`.
- `headline TEXT`.
- `my_story TEXT`.
- `my_struggle TEXT`.
- `my_hope TEXT`.
- `content_json TEXT`.
- `raw_llm_output TEXT`: optional; can be disabled in production if PHI duplication is a concern.
- `llm_model TEXT`.
- `prompt_version TEXT`.
- `generation_latency_ms INTEGER`.
- `published_url TEXT`.
- `html_path TEXT`.
- `generated_at TEXT`.
- `reviewed_at TEXT`.
- `published_at TEXT`.

Constraints:

- Unique `(visit_id, version)`.

## Timing Metrics

The database should capture both summary metrics and raw event timings.

### User Response Timing

For each user message:

- `response_latency_ms`: assistant finished speaking to user beginning to answer.
- `answer_duration_ms`: user beginning to answer to final transcript or send.
- `answer_word_count`.
- `answer_char_count`.
- `speech_confidence`.
- `input_modality`.
- `retry_count`.
- `no_response`.

This lets us identify questions where users hesitate, answer briefly, retry, or switch from voice to typing.

### Assistant Timing

For each assistant message:

- `llm_latency_ms`: backend LLM generation time.
- `tts_duration_ms`: frontend avatar/audio speaking duration.
- `message_word_count`.
- `message_char_count`.
- `task_type`.
- `step_id`.

This lets us identify slow model responses, long prompts, and places where spoken output may be too long.

### Event Timeline

`turn_events` stores the raw timing sequence used to calculate and audit timing metrics:

```text
tts_started -> tts_ended -> vad_fired -> recognition_started -> recognition_ended
```

For typed input:

```text
tts_ended -> typed_started -> typed_sent
```

The summary columns on `messages` are for normal reporting. `turn_events` is for debugging and recomputation.

## Write Lifecycle

### `/api/session`

Create a visit row.

Store:

- `session_id`
- `language`
- `avatar_id`
- `avatar_profile_json`
- `phase`
- `user_agent`
- opening assistant message as a system/assistant message with `turn_number = 0`

### `/api/chat`

For each user turn:

1. Receive user text and turn metadata.
2. Save the user message with timing/count fields.
3. Save allowlisted `turn_events`.
4. Run the interview state machine and LLM/deterministic response.
5. Save the assistant message with task, step, latency, word/character count, and phase.
6. Update `visits` with current phase, awaiting state, current step, name status, counters, and last decision.

### `/api/upload`

For each photo:

1. Save image file using trusted generated filename.
2. Calculate metadata such as size and hash.
3. Insert photo row.
4. Update visit `photo_count`.

### `/api/generate`

Create a draft only.

Store:

- draft version
- generated content
- model/prompt metadata if available
- generation latency
- status `draft`

Do not write the public HTML file here.

### `/api/publish`

Publish after review.

Recommended sequence:

1. Save reviewed content as a new draft version or update final draft status.
2. Render HTML to a temporary file.
3. Atomically move the temporary file into the public microsite path.
4. Mark draft `published`.
5. Update visit `draft_status`, `published_at`, and `phase = COMPLETE`.

This avoids a database row claiming the page is published when the HTML file was not written.

## Frontend Metadata Plan

Add metadata to `ConversationAPI.sendMessage()`.

Payload fields:

- `input_modality`
- `response_latency_ms`
- `answer_duration_ms`
- `speech_confidence`
- `client_sent_at`
- `retry_count`
- `events`

`SpeechManager` already records some events internally. We should standardize the event names and consume them when sending the answer.

Add typed-input tracking:

- First keystroke records `typed_started`.
- Send button or Enter records `typed_sent`.
- `answer_duration_ms = typed_sent - typed_started`.
- `response_latency_ms = typed_started - last_tts_ended`, or send time if no first-keystroke data exists.

## What Not To Implement First

- No cross-visit participant identity table until we need repeat-user tracking.
- No raw audio storage.
- No field-level review edit audit table yet.
- No full user-model snapshot every turn by default.
- No external hosted database.

## Implementation Phases

### Phase 1: Database Foundation

Files likely touched:

```text
web/database.py
web/config.py
web/app.py
.gitignore
tests/test_database.py
```

Deliverables:

- `db/transplant.db` path config.
- SQLite initialization and migrations.
- WAL mode, busy timeout, foreign keys.
- Core tables and indexes.
- Tests for schema creation and basic inserts.

### Phase 2: Session And Conversation Capture

Files likely touched:

```text
web/routes_api.py
web/goal_interview.py
static/js/ConversationAPI.js
static/js/App.js
static/js/SpeechManager.js
tests/test_interview_flow.py
```

Deliverables:

- Visit row on session start.
- Opening message saved.
- User and assistant messages saved.
- Timing metadata sent from frontend.
- Allowlisted turn events saved.
- Visit phase/state updated every turn.

### Phase 3: Photo, Draft, And Publish Capture

Files likely touched:

```text
web/routes_photos.py
web/microsite.py
web/routes_api.py
tests/test_interview_flow.py
```

Deliverables:

- Photo metadata rows.
- Draft versions saved on generation.
- Publish marks final draft and visit complete.
- Publish file write handled safely.

### Phase 4: Operational Hardening

Deliverables:

- Backup and restore command.
- DB inspection command.
- Retention/deletion workflow.
- Log/pickle cleanup policy.
- Optional migration notes for PostgreSQL or self-hosted Supabase.

## Acceptance Criteria

- Starting a session creates exactly one visit row.
- Each completed turn creates one user message and one assistant message.
- User messages include response latency, answer duration, modality, and word/character counts.
- Assistant messages include LLM latency, TTS duration when available, task type, and step ID.
- Only allowlisted browser events are stored.
- Uploading photos creates photo rows and updates visit photo count.
- Generating creates a draft but does not publish HTML.
- Publishing creates/updates the public HTML and marks the draft/visit published.
- No database file or PHI artifact is committed to git.

