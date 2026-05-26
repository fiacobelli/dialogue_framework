# Android Chrome Speech Pipeline Final Plan

**Date:** 2026-05-26  
**Author:** Bernard  
**Status:** Final plan for implementation  
**Scope:** Transplant microsite speech input on Android Chrome/Samsung tablet

---

## 1. Problem Summary

Android Chrome sessions can pass microphone preflight and still fail during the actual interview. The avatar asks a question, the patient speaks, VAD detects some audio activity, but the submitted user turn becomes `[no speech detected]`.

This is not primarily a permission problem. The EC2 telemetry shows microphone access was granted, the input track was live, VAD was available, and VAD initialized successfully. The failure happens when the current production pipeline tries to use Web Speech API for transcription while VAD is also active.

## 2. Evidence From EC2

The relevant production sessions were on Android Chrome:

- `2026-05-26 18:37-18:39 UTC`
- User agent: Android Chrome mobile
- Mic preflight results: `status=ready`, `active_track_state=live`, `vad_available=true`, `speech_recognition_supported=true`
- VAD events appeared: `vad_init=ready`, `vad_fired`, `vad_speech_end`
- User turns were saved as `[no speech detected]`
- Events repeatedly showed `recognition_started` followed by `recognition_ended` with `transcript_words=0`

Shortly after, a desktop Chrome session captured real voice text. That confirms the app, backend, and general speech flow were working outside the Android Web Speech path.

Production is still on the old speech pipeline:

- EC2 `SpeechManager.js` still uses `SpeechRecognition`.
- EC2 still has `onSpeechEnd: () => this._onVADSpeechEnd()`, which discards the VAD audio.
- EC2 still emits `recognition_started`.
- EC2 does not yet use the `/api/transcribe` Whisper path.

Local code already contains a partial VAD-to-Groq-Whisper implementation, but it needs cleanup, tests, and a controlled deployment.

---

## 3. Root Cause

The current production architecture asks two browser subsystems to use the microphone during the same user turn:

1. Silero VAD through AudioWorklet, for detecting speech start/end.
2. Web Speech API, for transcription.

On Android Chrome, this combination is unreliable. VAD can see audio activity, but Web Speech ends with an empty transcript. Because transcription is empty, the app submits `[no speech detected]`.

There is also a concrete implementation bug in production:

```javascript
onSpeechEnd: () => this._onVADSpeechEnd()
```

The VAD library provides the audio buffer to `onSpeechEnd(audio)`, but production discards it. That prevents us from using VAD audio for transcription.

---

## 4. Final Architecture Decision

Use VAD as the only browser microphone owner. Use the audio buffer from VAD for transcription.

Final flow:

```text
Patient speaks
  -> VAD owns microphone and detects speech end
  -> Browser receives Float32Array audio from VAD
  -> Browser buffers nearby speech chunks to tolerate pauses
  -> Browser encodes merged audio as 16 kHz mono WAV
  -> Browser POSTs WAV to /api/transcribe
  -> Flask sends audio to Groq Whisper
  -> Browser receives transcript
  -> Existing /api/chat flow continues unchanged
```

Decisions:

- Do not call Groq directly from browser JavaScript, because that would expose the API key.
- Keep `/api/transcribe` on the backend.
- Prefer a dedicated `web/routes_transcribe.py` module if we are still cleaning up file size. If implementation speed is the priority, keeping it in `web/routes_api.py` is acceptable temporarily, but it should be split later.
- Use a 3000 ms commit timer after VAD speech end. This supports patients who pause mid-thought.
- Keep `setLanguage()` and `getSpeechConfidence()` as compatibility methods in `SpeechManager.js`; `getSpeechConfidence()` should return `null`.
- Do not fall back to Web Speech API on Android. If VAD is unavailable, show a clear microphone error and allow typed input.

---

## 5. Files To Modify

Core implementation:

- `static/js/SpeechManager.js`
- `static/js/App.js`
- `web/config.py`
- `web/routes_api.py` or new `web/routes_transcribe.py`
- `web/app.py` if a new blueprint is created
- `web/database_common.py` or `web/database.py`, depending on current database module split

Tests:

- `tests/test_interview_flow.py`

Documentation:

- `docs/plans/ANDROID_SPEECH_PIPELINE_PLAN.md`

Important working tree note:

The local working tree currently contains mixed changes from the database cleanup and the speech pipeline work. Before committing or deploying, separate the speech fix from unrelated cleanup as much as possible.

---

## 6. Implementation Plan

### Phase 1: Stabilize The Local Speech Code

Update `static/js/SpeechManager.js` so the speech path is internally consistent:

- Remove Web Speech API transcription from active voice input.
- Keep VAD initialization and preflight.
- Change VAD callback to receive audio: `onSpeechEnd: (audio) => this._onVADSpeechEnd(audio)`.
- Add or verify audio buffering state: `_audioChunks`, `_commitTimer`, `_transcribing`.
- On speech start, clear the commit timer if transcription has not begun.
- On speech end, append the `Float32Array` audio and start a 3000 ms commit timer.
- On commit, merge chunks into one `Float32Array`.
- Encode merged audio as 16 kHz mono WAV.
- POST the WAV to `/api/transcribe`.
- Emit `complete` only if a non-empty transcript returns and the turn state is still `USER_SPEAKING`.
- Emit `empty` only when there is no speech, transcription fails, or transcript is empty.
- Pause VAD while transcription is in flight.
- Preserve typed input as the fallback.

Keep these compatibility methods:

```javascript
setLanguage(langCode) {
    this.lang = langCode;
}

getSpeechConfidence() {
    return null;
}
```

### Phase 2: Backend Transcription Endpoint

Implement or harden `POST /api/transcribe`:

- Accept multipart form field `audio`.
- Accept optional `language`, defaulting to `en`.
- Reject missing audio with `400`.
- Reject audio larger than 1 MB with `413`.
- Reject missing `GROQ_API_KEY` with a clear server-side error and safe JSON response.
- Send audio to Groq Whisper using `whisper-large-v3-turbo`.
- Return `{"transcript": "..."}` on success.
- Return safe JSON errors; do not leak API details to the browser.
- Log failures server-side with enough context to debug.

Security decision:

- Minimum acceptable for this prototype: keep API key server-side and do not expose it in browser JS.
- Better before field deployment: require the patient session token on `/api/transcribe` so the endpoint is not a public relay to Groq.

### Phase 3: Telemetry And Database Compatibility

Update the allowed event list so new speech events are not silently dropped:

- `listening_started`
- `listening_ended`
- `transcribe_started`
- `transcribe_ended`
- `transcribe_error`

Preserve useful metadata:

- `duration_ms`
- `transcript_words`
- `status`
- `reason`
- `error_name`
- `error_message`

Expected telemetry after the fix:

- Android sessions should no longer show `recognition_started`.
- Successful voice turns should show `listening_started`, `vad_fired`, `vad_speech_end`, `transcribe_started`, `transcribe_ended`, `listening_ended`.
- Failed voice turns should show `transcribe_error` or `silence_timeout`, not Web Speech `recognition_ended`.

### Phase 4: App.js Integration

Check `static/js/App.js` for stale Web Speech assumptions:

- Keep `speechManager.setLanguage('en-US')` only if the compatibility method remains.
- Keep `speechManager.getSpeechConfidence()` only if it returns `null`.
- Remove any `recognitionEnded` event listener if still present.
- Ensure `_buildTurnMetadata()` uses `listening_started` and `listening_ended` for `answer_duration_ms`.
- Ensure UI shows a short processing state while transcription is in flight.

### Phase 5: Tests

Add focused backend tests:

- `/api/transcribe` returns `400` when audio is missing.
- `/api/transcribe` returns `413` when audio is too large.
- `/api/transcribe` returns transcript text when Groq succeeds.
- `/api/transcribe` returns safe error JSON when Groq fails.
- `/api/transcribe` returns safe error JSON when `GROQ_API_KEY` is missing.
- New speech events are accepted and saved by the DB event logger.

Run:

```bash
python3 -m pytest -q
```

Browser behavior still requires manual testing because unit tests cannot validate Android microphone ownership.

---

## 7. Deployment Plan

1. Finish and test the local speech fix.
2. Commit only speech-related changes if possible.
3. Push the branch.
4. Pull the branch on EC2.
5. Restart `microsite.service`.
6. Confirm the deployed files no longer contain active Web Speech transcription.
7. Confirm `/microsite/api/transcribe` exists.
8. Test on desktop Chrome.
9. Test on Android Chrome/Samsung tablet.
10. Review DB events after the Android test.

Deployment verification commands:

```bash
sudo systemctl restart microsite
sudo systemctl status microsite --no-pager
curl --max-time 10 https://ludi.a4hlab.org/microsite/api/health
```

Expected Android test result:

- Mic preflight is ready.
- VAD initializes.
- The browser sends `/microsite/api/transcribe`.
- User message content is the actual transcript, not `[no speech detected]`.
- DB events include `transcribe_ended`.
- No `recognition_started` events appear in new turns.

---

## 8. Rollback Plan

If the Whisper path causes a production blocker:

1. Revert the speech pipeline commit.
2. Restart `microsite.service`.
3. Confirm the app loads and typed input still works.
4. Keep the EC2 logs and DB rows from the failed test for diagnosis.

Do not roll back unrelated database cleanup commits unless they are part of the same deployment and directly implicated.

---

## 9. Risks And Mitigations

| Risk | Severity | Mitigation |
|---|---:|---|
| Groq latency on weak clinic Wi-Fi | Medium | Show processing state while transcription is in flight |
| Patient pauses longer than commit timer | Medium | Use 3000 ms timer and preserve typed fallback |
| `/api/transcribe` abused as public endpoint | Medium | Keep key server-side now; add patient token validation before field deployment |
| VAD unavailable on a device | Medium | Show clear error and allow typed input |
| Missing API key on EC2 | High | Add explicit config check and health/deploy verification |
| New telemetry silently dropped | Medium | Update DB event allowlist |
| Mixed working tree causes accidental deploy | High | Commit speech fix separately from database cleanup if possible |

---

## 10. Definition Of Done

The fix is complete when:

- Local tests pass.
- Production `SpeechManager.js` no longer uses Web Speech API for voice transcription.
- Production `onSpeechEnd` receives the VAD audio argument.
- `/api/transcribe` is deployed and returns safe JSON responses.
- Android Chrome voice input produces real transcript text in the DB.
- New speech events are saved in DB telemetry.
- Typed input still works.
- The Samsung tablet test no longer gets stuck on repeated `[no speech detected]`.

