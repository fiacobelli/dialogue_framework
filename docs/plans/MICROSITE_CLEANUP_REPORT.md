# Microsite Cleanup Report

Date: 2026-05-26

## Purpose

This report answers one question: is the codebase still a clean fit for the simple donor-story microsite, or has it accumulated too much framework, safety, and historical baggage?

Short answer: the active microsite is still understandable, but the repository is carrying too many historical framework files, generated artifacts, planning documents, and oversized orchestration files. The core product is not broken by scope alone; it is obscured by clutter and by several layers of compatible-but-overlapping architecture.

## Summary Assessment

- The product goal is still simple.
- The active web app mostly matches that goal.
- The repository around it is larger and noisier than the scope requires.
- The biggest complexity is not feature count, but overlap between the old dialogue framework, the new microsite flow, and local runtime artifacts.
- The cleanup should be conservative: archive first, delete later, and only after behavior is confirmed.

## Files To Keep

These files are core to the current working microsite and should remain source-of-truth files.

| File / Module | Why it should stay |
|---|---|
| `web/app.py` | Flask app entrypoint and route mounting. |
| `wsgi.py` | Deployment entrypoint under `/microsite`. |
| `web/session.py` | Session creation and framework wiring. |
| `web/session_store.py` | Durable session rehydration and persistence. |
| `web/goal_interview.py` | Active interview/LLM bridge. |
| `web/interview_flow.py` | Core interview state machine. |
| `web/interview_answer_analysis.py` | Deterministic answer parsing and sufficiency. |
| `web/interview_flow_config.py` | Question order and prompt config. |
| `web/turn_interpreter.py` | Pre-evidence turn classification. |
| `web/microsite.py` | Draft and publish generation logic. |
| `web/routes_api.py` | Session/chat/generate/publish API. |
| `web/routes_photos.py` | Photo upload, metadata, QR, preview. |
| `web/routes_publication.py` | Unpublish/delete lifecycle. |
| `web/routes_admin.py` | Staff review and takedown UI. |
| `web/database.py` | Needed, but should be split later. |
| `web/patient_auth.py` | Patient capability token checks. |
| `web/takedown.py` | Shared deletion lifecycle helper. |
| `web/content_moderation.py` | Public-content safety gate. |
| `web/story_evaluator.py` | Structured answer evaluation. |
| `web/emotional_support.py` | Guarded emotional follow-up logic. |
| `web/llm_provider.py` | Provider abstraction. |
| `web/structured_logging.py` | Structured event logging. |
| `templates/select_avatar.html` | Product entry point. |
| `templates/interview.html` | Main interview UI. |
| `templates/upload_mobile.html` | QR/mobile upload flow. |
| `templates/microsite.html` | Public donor page template. |
| `templates/admin_login.html`, `templates/admin_sessions.html`, `templates/admin_session_detail.html` | Staff workflow pages. |
| `templates/avatar_preview.html` | Avatar preview support. |
| `static/js/App.js` | Orchestration for the current UI. |
| `static/js/ConversationAPI.js` | Backend client. |
| `static/js/SpeechManager.js` | Mic/VAD/speech handling. |
| `static/js/TurnManager.js` | Turn-taking state machine. |
| `static/js/UIController.js` | DOM/view controller. |
| `static/js/config.js` | Browser config. |
| `static/css/base.css`, `static/css/interview.css`, `static/css/avatar.css` | Active styling. |
| `prompts/interviewer.txt` | Interview prompt. |
| `prompts/microsite.txt` | Microsite generation prompt. |
| `domains/interview.json` | Framework knowledge base for the web session. |
| `tests/test_interview_flow.py`, `tests/test_turn_interpreter.py`, `tests/test_e2e_interview.py` | Current regression coverage. |
| `goal.py`, `information_state.py`, `dialogue_manager.py`, `dialogue_manager_passive.py`, `nlg.py`, `rules.py`, `strings.py`, `web/nlu_web.py` | These are still part of Prof. Francisco’s framework scaffolding and the current web session wiring. |

## Files To Review Carefully

These files are active, but they are also where complexity concentrates.

| File / Module | Why to review carefully | Risk if removed too early |
|---|---|---|
| `web/database.py` | It is too large and mixes schema, lifecycle, and query logic. | Breaking persistence, auditability, and delete/recovery behavior. |
| `static/js/App.js` | It owns too many browser behaviors. | Reintroducing UI bugs or breaking the interview flow. |
| `static/js/UIController.js` | It is large enough to be hard to trace. | Losing UI state consistency. |
| `static/js/SpeechManager.js` | It handles microphone warm-up, VAD, and speech telemetry. | Regressing the patient mic experience. |
| `web/routes_api.py` | It orchestrates many separate concerns. | Breaking session, chat, generate, or publish flows. |
| `web/microsite.py` | It mixes evidence formatting, draft building, and rendering. | Duller donor pages or broken publish output. |
| `web/routes_photos.py` | It combines auth, upload, preview, metadata, and QR flow. | Photo flow regressions. |
| `web/routes_publication.py` | It is now short, but still lifecycle-critical. | Breaking unpublish/delete. |
| `web/routes_admin.py` | Staff controls are security-sensitive. | Losing admin takedown capability. |
| `web/goal_interview.py` | It bridges framework state and LLM behavior. | Rebreaking conversation flow. |
| `web/session_store.py` | It currently owns in-memory + pickle + DB rehydration. | Session loss or delete/recovery bugs. |
| `web/patient_auth.py` | New security layer; should stay isolated until policy settles. | Overcomplicating auth if merged too early. |
| `static/js/vad/*` | Large binaries, but currently needed for mic support. | Mic regression on the tablet/phone flow. |
| `docs/plans/*` | Important history, but too many competing plans confuse the current path. | Losing useful rationale if archived too aggressively. |
| `docs/CODEBASE_GUIDE.md`, `docs/PROJECT_NOTES.md`, `docs/MEETING_PREP.md`, `docs/meeting_transcripts/*` | Valuable history, but not active product code. | Loss of institutional memory if deleted outright. |

## Files That Appear Unnecessary

These are likely legacy, experimental, or no longer part of the active microsite path. They should be archived or removed only after confirming they are not needed for any current workflow.

| File / Module | Why it looks unnecessary | Removal risk |
|---|---|---|
| `dialogue_application.py` | Original CLI entrypoint, not used by Flask app. | Low for microsite runtime, medium for historical docs. |
| `goal_manager.py` | Depends on missing legacy `goal_bc` path; not used by the web app. | Low runtime risk, but legacy docs may reference it. |
| `goal_llm.py` | Old LLM goal implementation, superseded by `web/goal_interview.py`. | Low runtime risk. |
| `nlu.py` | Original speech NLU path with missing dependencies. | Low runtime risk, high if someone still uses CLI experiments. |
| `speech_system.py`, `speech_system_test.py` | Legacy speech stack, not used by current microsite. | Low for microsite, but may be useful for historical reference. |
| `similarity.py`, `similarity_custom.py`, `test_mle.py` | Original similarity/scoring tooling. | Low for microsite, medium for old research workflows. |
| `prompts/dialysis.txt` | Old system prompt for the original dialysis assistant. | Low runtime risk. |
| `templates/chat.html` | Old chat UI, not wired into the current Flask routes. | Low runtime risk. |
| `static/microsites/*` | Generated public pages, not source. | Safe to keep ignored; do not version as code. |
| `photos/*`, `user_models/*`, `logs/*`, `db/transplant.db` | Runtime artifacts, not source. | Removing local copies is safe after backups, but do not delete production data blindly. |
| `docs/~$ETING_PREP.docx`, `*.docx` lock/temp files | Office artifacts, not source. | Low. |

## Files Or Modules That May Be Merged

These are not all urgent merges, but they are candidates if the goal is to reduce file count and make responsibilities clearer.

| Merge Candidate | Why it is a candidate | Merge risk |
|---|---|---|
| `web/patient_auth.py` into a broader `web/security.py` or `web/session_security.py` | Patient token logic is tiny and closely related to session/auth flow. | Too early a merge could blur patient auth and admin auth. |
| `web/routes_publication.py` into a broader patient-lifecycle module | It shares session validation and takedown behavior with routes_api/routes_photos. | Could make route files too large again. |
| `web/turn_interpreter.py` into `web/interview_flow.py` only if it stays small | It is tightly coupled to the interview state machine. | Merging now could make `interview_flow.py` grow beyond traceable size. |
| `web/story_evaluator.py` and parts of `web/interview_answer_analysis.py` | Both participate in answer interpretation. | Over-merging could remove useful boundaries. |
| `static/js/ConversationAPI.js`, `App.js`, `UIController.js`, `SpeechManager.js` into smaller controllers/modules | The current browser layer has too many responsibilities in a few files. | Premature merging would make the frontend even harder to debug. |
| `dialogue_manager.py` and `dialogue_manager_passive.py` | Passive manager is a very small variant. | Low risk, but only if the original framework is still required. |

## Logic That Can Be Simplified

These are simplifications that preserve behavior but reduce mental overhead.

- Replace one-off phrase tuning with the `turn_interpreter` + state-machine pattern.
- Keep interview state transitions in code and let the LLM only phrase the response.
- Reduce the hybrid session model over time by making SQLite the durable source and pickle a temporary compatibility layer.
- Make `web/database.py` a package or smaller modules once the current lifecycle semantics are fully stabilized.
- Move story evidence formatting into a dedicated evidence builder rather than constructing everything inline in `web/microsite.py`.
- Split frontend orchestration into smaller controllers so `App.js` does not own all turn, photo, and publication logic.
- Treat generated microsites and photo uploads as runtime data, not source.

## Risks Of Removing Items Too Early

| Item | Risk if removed too early |
|---|---|
| `web/database.py` | Breaks the only durable record of visits, messages, photos, consents, and audit events. |
| `web/session_store.py` | Loses restart-safe rehydration and can break field use after restart. |
| `web/goal_interview.py` | Reintroduces robotic or unstructured conversation behavior. |
| `web/interview_flow.py` | Removes the current conversation contract and root-cause fixes. |
| `web/microsite.py` | Breaks story generation and publish flow. |
| `static/js/SpeechManager.js` | Regresses microphone behavior and turn timing. |
| `dialogue_manager.py` / `information_state.py` / `rules.py` / `nlg.py` | Loses the framework scaffolding still used by the web session. |
| `nlu.py`, `speech_system.py`, `similarity.py`, `goal_manager.py` | Low risk for the microsite, but these are still useful as historical references until the framework cleanup is confirmed. |
| `docs/plans/*` and `docs/meeting_transcripts/*` | Removes reasoning history that explains why the current design exists. |

## Recommended Cleanup Sequence

1. Keep the current working microsite behavior frozen.
2. Separate runtime artifacts from source in the workspace and leave them ignored by Git.
3. Keep only one active plan document visible as the canonical plan.
4. Move legacy framework files into an archived area or clearly label them as historical.
5. Split `web/database.py` into smaller modules without changing behavior.
6. Split frontend orchestration files only after the backend contracts are stable.
7. Reassess whether the legacy CLI/speech/similarity stack should be archived or deleted after confirming no active workflow depends on it.
8. Only then continue with new product features.

## What Should Be Preserved

- The active microsite workflow: interview, photo upload, review, publish.
- The patient-safety controls: consent, publication gating, takedown, audit logging.
- The conversational foundation from Prof. Francisco’s framework: information state, goal manager pattern, rules, and NLG separation.
- The fact that the LLM is bounded, not in charge of state transitions.
- The database records that help explain what happened in a session.
- The microphone/VAD support, because that is still part of the real patient workflow.
- The test coverage around interview flow, turn interpretation, deletion, upload, and publication.

## Cleanup Conclusion

The codebase is not wildly overengineered for the product goal, but it is carrying too many historical layers and runtime artifacts. The right cleanup strategy is not a broad delete pass. It is:

- archive legacy framework files first,
- reduce the visible surface area of runtime artifacts,
- split the biggest orchestration files after behavior is stable,
- keep the active microsite, safety, and interview logic intact.

