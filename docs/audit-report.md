# Audit Report: Epic/Task Documentation vs. Codebase

**Date:** 2026-05-30  
**Scope:** 7 epics, 29 tasks, 54 subtasks vs. actual code in `bot/`, `worker/`, `tests/`

---

## 1. Executive Summary

| Metric | Count |
|--------|-------|
| Epics documented | 7 |
| Tasks documented | 29 |
| Subtasks documented | 54 |
| Bot source files | 16 |
| Worker source files | 25 |
| Unit tests | 30 |
| Integration tests | 0 |
| Test fixtures | 5 |

**Overall status:** All 7 epics are **partially or fully implemented**, but with significant structural issues:
- **7 duplicate implementation pairs** (same responsibility, two different files)
- **18 undocumented modules** (code exists but no corresponding task/subtask)
- **11 file name mismatches** (docs reference different filenames than actual code)
- **1 missing epic** (epic-001 has no task files despite 5 tasks documented)
- **Critical test gap** (only 15/30 tests pass; 0 integration tests; 20+ modules untested)

---

## 2. Epic-by-Epic Audit

### Epic 001 — Project Foundation (T1.1–T1.5)

| Task | Status | Notes |
|------|--------|-------|
| T1.1 Project Scaffolding | ✅ Implemented | bot/config.py, worker/config.py, Dockerfiles, requirements.txt |
| T1.2 Matrix Client | ✅ Implemented | bot/matrix_client.py, bot/client.py, bot/matrix/client.py |
| T1.3 Redis Queue | ✅ Implemented | bot/client.py enqueue_task(), worker/main.py blpop loop |
| T1.4 Logging Setup | ✅ Implemented | bot/logging_setup.py (JsonFormatter, setup_logging) |
| T1.5 CI-CD | ❌ **Not implemented** | No .github/workflows/, no Makefile, no .pre-commit-config.yaml, no .env.example |

**Gaps:**
- `docs/tasks/epic-001/` — **0 files** (T1.1–T1.5 task specs missing)
- `docs/subtasks/epic-001/` — **0 files**
- T1.5 CI-CD not implemented at all

---

### Epic 002 — Bot Matrix Audio (T2.1–T2.5)

| Task | Status | Notes |
|------|--------|-------|
| T2.1 Audio Download | ✅ Implemented | bot/audio_downloader.py (360 lines) |
| T2.2 Matrix Client Integration | ✅ Implemented | bot/matrix_client.py, bot/client.py |
| T2.3 Task Queue Push | ✅ Implemented | bot/client.py, bot/__main__.py |
| T2.4 Bot Error Handling | ✅ Implemented | bot/exceptions.py, bot/__main__.py |
| T2.5 Bot Graceful Shutdown | ✅ Implemented | bot/__main__.py signal handlers |

**Gaps:**
- `bot/notifications.py` (send_status with emojis) — **documented in task files but not epic spec**
- `bot/client.py` — duplicate of `bot/matrix_client.py` (both have create_client())
- `bot/matrix/client.py` — exists but not mentioned in epic spec

---

### Epic 003 — Worker Audio Transcription (T3.1–T3.4)

| Task | Status | Notes |
|------|--------|-------|
| T3.1 Audio Conversion | ✅ Implemented | worker/audio.py + worker/audio_converter.py (duplicates) |
| T3.2 Whisper Transcription | ✅ Implemented | worker/transcriber.py + worker/whisper_engine.py (duplicates) |
| T3.3 Task Processing Pipeline | ✅ Implemented | worker/pipeline.py, worker/main.py, worker/__main__.py |
| T3.4 Whisper Model Loading | ✅ Implemented | worker/transcriber.py, worker/__main__.py |

**Gaps:**
- `worker/audio.py` (standalone convert_to_wav) — **no corresponding task**
- `worker/whisper_engine.py` (WhisperEngine class) — **no corresponding task**
- `worker/transcriber.py` mentions `faster_whisper` but epic spec says `whisper`
- Task T3.4 name is "error-handling-logging" (in docs/tasks/) but spec says "Whisper Model Loading"

---

### Epic 004 — Worker LLM + PDF (T4.1–T4.4)

| Task | Status | Notes |
|------|--------|-------|
| T4.1 LLM Client | ✅ Implemented | worker/llm_client.py + worker/llm_engine.py (duplicates) |
| T4.2 PDF Generator | ✅ Implemented | worker/pdf_generator.py |
| T4.3 Result Publisher | ✅ Implemented | worker/result_publisher.py |
| T4.4 End-to-End Summary Pipeline | ✅ Implemented | worker/pipeline.py, worker/__main__.py |

**Gaps:**
- `worker/llm_engine.py` (LLMAPI with check_risks()) — **no corresponding task**
- `worker/chunking.py` (chunk_text, merge_summaries) — **mentioned in epic spec but no task**
- `worker/pipeline.py` (parse_task, process_transcription_task) — **no corresponding task**
- File name mismatch: epic spec says `worker/llm.py` → actual is `worker/llm_client.py`
- File name mismatch: epic spec says `worker/pdf.py` → actual is `worker/pdf_generator.py`
- File name mismatch: epic spec says `worker/templates.py` → **does not exist**
- `worker/llm_client.py` uses `asyncio.sleep()` inside a **synchronous** method (bug: await in sync function)

---

### Epic 005 — Bot Result Delivery (T5.1–T5.4)

| Task | Status | Notes |
|------|--------|-------|
| T5.1 Result Listener | ✅ Implemented | bot/result_listener.py + bot/__main__.py inline (duplicates) |
| T5.2 PDF Uploader | ✅ Implemented | bot/pdf_uploader.py |
| T5.3 Bot Error Handling Results | ✅ Implemented | bot/__main__.py, bot/notifications.py |
| T5.4 Bot Graceful Shutdown Results | ✅ Implemented | bot/__main__.py, bot/result_listener.py |

**Gaps:**
- `bot/result_consumer.py` (deliver_result with retry) — **no corresponding task**
- `bot/notifications.py` (send_status) — **no corresponding task**
- File name mismatch: epic spec says `bot/results.py` → actual is `bot/result_listener.py`
- File name mismatch: epic spec says `bot/upload.py` → actual is `bot/pdf_uploader.py`
- File name mismatch: epic spec says `bot/delivery.py` → actual is `bot/result_consumer.py`

---

### Epic 006 — Reliability & Errors (T6.1–T6.4)

| Task | Status | Notes |
|------|--------|-------|
| T6.1 Retry Mechanism | ✅ Implemented | worker/retry.py + inline in bot/result_consumer.py |
| T6.2 Dead Letter Queue | ✅ Implemented | worker/dlq.py |
| T6.3 Graceful Shutdown | ✅ Implemented | worker/graceful_shutdown.py, bot/__main__.py |
| T6.4 Duplicate Task Prevention | ✅ Implemented | worker/task_tracker.py |

**Gaps:**
- `worker/errors.py` (TaskError dataclass, handle_error) — **no corresponding task**
- `worker/retry.py` spec says async decorator → actual is **synchronous** decorator
- `worker/dlq.py` spec says `send_to_dlq()` function → actual is `DeadLetterQueue` class
- File name mismatch: epic spec says `worker/monitor.py` → actual is `worker/task_tracker.py`

---

### Epic 007 — Observability & Config (T7.1–T7.4)

| Task | Status | Notes |
|------|--------|-------|
| T7.1 JSON Structured Logging | ✅ Implemented | bot/logging_setup.py, worker/errors.py |
| T7.2 Health Checks | ✅ Implemented | bot/health.py, worker/health.py |
| T7.3 Metrics Collection | ✅ Implemented + Verified | bot/metrics.py, worker/metrics.py, tests/unit/test_metrics.py (15/15 pass) |
| T7.4 Config Module | ✅ Implemented | bot/config.py, worker/config.py |

**Gaps:**
- File name mismatch: epic spec says `bot/logging.py` → actual is `bot/logging_setup.py`
- File name mismatch: epic spec says `worker/logging.py` → **does not exist** (logging is only in bot/)
- `worker/errors.py` has JSON logging but is under epic-006, not epic-007

---

## 3. Duplicate Implementations (Priority: HIGH)

| # | Module A | Module B | Responsibility | Recommendation |
|---|----------|----------|---------------|----------------|
| 1 | `bot/matrix_client.py` | `bot/client.py` | Matrix client creation + auth | Keep `bot/matrix_client.py`, remove `bot/client.py` |
| 2 | `bot/client.py` (enqueue_task) | `bot/__main__.py` (rpush) | Redis task queue push | Consolidate into `bot/client.py` |
| 3 | `worker/audio.py` | `worker/audio_converter.py` | Audio → WAV conversion | Keep `worker/audio_converter.py`, remove `worker/audio.py` |
| 4 | `worker/transcriber.py` | `worker/whisper_engine.py` | Whisper transcription | Keep `worker/transcriber.py`, remove `worker/whisper_engine.py` |
| 5 | `worker/llm_client.py` | `worker/llm_engine.py` | LLM API calls | Merge into single `worker/llm_client.py` |
| 6 | `bot/result_listener.py` | `bot/__main__.py` (inline) | Redis pub/sub listener | Remove inline from `__main__.py`, keep class |
| 7 | `bot/pdf_uploader.py` | `bot/__main__.py` (inline) | PDF upload to Matrix | Remove inline from `__main__.py`, use class |

---

## 4. Undocumented Modules (Priority: MEDIUM)

These files exist in the codebase but have no corresponding task or subtask:

| File | Epic | Responsibility |
|------|------|---------------|
| `bot/notifications.py` | 002/005 | send_status() with emoji prefixes |
| `bot/result_consumer.py` | 005 | deliver_result() with retry |
| `worker/llm_engine.py` | 004 | LLMAPI with check_risks() |
| `worker/chunking.py` | 004 | chunk_text(), merge_summaries() |
| `worker/pipeline.py` | 003/004 | parse_task(), process_transcription_task() |
| `worker/errors.py` | 006 | TaskError dataclass, handle_error() |
| `worker/audio.py` | 003 | convert_to_wav() standalone |
| `worker/whisper_engine.py` | 003 | WhisperEngine class |
| `bot/matrix/client.py` | 002 | nio.AsyncClient wrapper |

---

## 5. File Name Mismatches (Priority: LOW)

| Epic | Task | Spec Filename | Actual Filename |
|------|------|---------------|-----------------|
| 004 | T4.1 | `worker/llm.py` | `worker/llm_client.py` |
| 004 | T4.2 | `worker/pdf.py` | `worker/pdf_generator.py` |
| 004 | T4.2 | `worker/templates.py` | *(does not exist)* |
| 005 | T5.1 | `bot/results.py` | `bot/result_listener.py` |
| 005 | T5.2 | `bot/upload.py` | `bot/pdf_uploader.py` |
| 005 | T5.3 | `bot/delivery.py` | `bot/result_consumer.py` |
| 006 | T6.4 | `worker/monitor.py` | `worker/task_tracker.py` |
| 006 | T6.2 | `worker/dlq.py` (function) | `worker/dlq.py` (class) |
| 007 | T7.1 | `bot/logging.py` | `bot/logging_setup.py` |
| 007 | T7.1 | `worker/logging.py` | *(does not exist)* |

---

## 6. Test Coverage Gaps (Priority: CRITICAL)

### Existing Tests (30 files)
- `tests/unit/test_metrics.py` — **15 tests, all passing** ✅
- 29 other test files exist but most are **stubs or minimal**

### Untested Modules (20+ files)
| Module | Criticality |
|--------|-------------|
| `worker/errors.py` (TaskError) | High |
| `worker/task_tracker.py` | High |
| `worker/graceful_shutdown.py` | High |
| `worker/retry.py` | High |
| `worker/dlq.py` | High |
| `worker/chunking.py` | Medium |
| `worker/pipeline.py` | High |
| `worker/llm_client.py` | High |
| `worker/llm_engine.py` | Medium |
| `worker/pdf_generator.py` | High |
| `worker/transcriber.py` | High |
| `worker/audio_converter.py` | Medium |
| `bot/audio_downloader.py` | High |
| `bot/matrix_client.py` | High |
| `bot/result_consumer.py` | High |
| `bot/notifications.py` | Medium |
| `bot/pdf_uploader.py` | Medium |
| `bot/result_listener.py` | High |
| `bot/client.py` | High |

### Missing Test Infrastructure
- **No integration tests** (end-to-end bot → worker → bot flow)
- **No fixture audio files** (short.wav, medium.mp3, long.flac, invalid.mp3)
- **No conftest.py** at project root
- **No test for worker/__main__.py** (main loop)
- **No test for bot/__main__.py** (main loop)

---

## 7. Critical Bugs Found

1. **`worker/llm_client.py` line ~111:** `await asyncio.sleep()` inside a **synchronous** `def summarize()` method — will raise `SyntaxError: await outside async function`
2. **No type hints** across any module
3. **No docstrings** on most classes
4. **No version pinning** in requirements.txt files
5. **No dependency management** (pip-tools, poetry, uv)

---

## 8. Recommendations (Priority Order)

### P0 — Fix Immediately
1. Fix `worker/llm_client.py` async/sync bug
2. Add missing task files for `docs/tasks/epic-001/` (T1.1–T1.5)
3. Implement T1.5 CI-CD (GitHub Actions workflow)

### P1 — Reduce Duplication
4. Consolidate 7 duplicate implementation pairs (see §3)
5. Move inline logic from `bot/__main__.py` and `worker/__main__.py` into proper modules

### P2 — Add Documentation
6. Create task files for 9 undocumented modules (see §4)
7. Update epic specs to match actual filenames (see §5)
8. Add subtask files for epic-001

### P3 — Improve Testing
9. Add unit tests for all P1-critical modules (18 files in §6)
10. Create integration test suite (bot → worker → bot flow)
11. Add fixture audio files for audio conversion tests

### P4 — Polish
12. Add type hints across all modules
13. Add docstrings to all public classes/functions
14. Pin dependency versions in requirements.txt
15. Add .env.example, Makefile, .pre-commit-config.yaml

---

## 9. Implementation Plan for Gaps

### Phase 1: Fix Critical (1 day)
- [ ] Fix `worker/llm_client.py` async bug
- [ ] Create `docs/tasks/epic-001/T1.1-T1.5.md`
- [ ] Create GitHub Actions CI workflow

### Phase 2: Deduplication (3 days)
- [ ] Merge bot/matrix_client.py + bot/client.py
- [ ] Merge worker/audio.py + worker/audio_converter.py
- [ ] Merge worker/transcriber.py + worker/whisper_engine.py
- [ ] Merge worker/llm_client.py + worker/llm_engine.py
- [ ] Clean up __main__.py inline logic

### Phase 3: Documentation (2 days)
- [ ] Add task files for 9 undocumented modules
- [ ] Update epic specs with correct filenames
- [ ] Add subtask files for epic-001

### Phase 4: Testing (5 days)
- [ ] Unit tests for 18 untested modules
- [ ] Integration test suite
- [ ] Fixture audio files
- [ ] Achieve 80%+ coverage

---

*End of audit report.*
