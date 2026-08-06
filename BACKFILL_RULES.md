# Backfill Rules

## Backfill Types

This system now handles THREE distinct backfill types, consolidated into one cron (`675cf9bb73b2` at 12:00 MYT):

1. **Upload gap** (`bf_gap_runner.py`): First-time YouTube upload of videos that were rendered locally but never uploaded. Highest priority — these are content gaps, not replacements.

2. **Metadata replacement** (`bf_metadata_runner.py`): Re-upload low-performing videos (views < 10) with improved title/description/tags. Replaces old video in playlist.

3. **BM content generation** (`backfill_days.py`): Generate missing Motivational Biblical days from themes.json.

## Queue Files

| File | Purpose |
|---|---|
| `state/upload_gap_queue.json` | First-time upload gaps (rendered but unuploaded) |
| `state/backfill_queue.json` | Metadata replacement queue (0-view re-uploads) |
| `state/backfill_done.json` | Completed metadata replacements |
| `state/upload_gap_done.json` | Completed upload gaps |
| `state/backfill_stats.json` | Metadata replacement stats |
| `state/upload_gap_stats.json` | Upload gap stats |

## Metadata Replacement Backfill

What it does: replace a low-performing or 0-view video with a fresh upload of the same `final.mp4` but improved metadata. This resets the YouTube algorithm clock so the video can be recommended again.

**Core rule:** 1 backfill per day, after BDCN CTA backfill completes.

## Backfill steps (exact sequence — metadata replacement)

1. Upload replacement video with new title/desc/tags/thumbnail.
2. Remove old video from its playlist entry.
3. Insert new video into the same playlist (position handled by YouTube).
4. Mark old video_id as done in queue.
5. Log result to stats.

## Queue format

File: `/root/projects/pipeline_wiki/state/backfill_queue.json`

```json
[
  {
    "video_id": "abc123",
    "pipeline": "prayer_en",
    "day": 25,
    "lang": "en",
    "playlist_key": "prayer_en",
    "title": "...",
    "description": "...",
    "tags": ["..."],
    "asset_dir": "/root/projects/prayer/assets/day_25"
  }
]
```

## Playlist mapping

| Key | Playlist ID |
|---|---|
| prayer_en | PLgsAd6HNQy7mJBtui-DpTL-QJKeP4CjDW |
| prayer_cn | PLgsAd6HNQy7lpA3YbFReNwqFiMqoOCWi1 |
| bm_en | PLgsAd6HNQy7mCkZFi9VNkBUMUuKPEqxoI |
| bm_cn | PLgsAd6HNQy7mq_CFgbfWhTQSh_qeFMSQL |

## Scheduling

All backfills consolidated into 1 cron job:

- **Cron job ID:** `675cf9bb73b2`
- **Name:** Unified Backfill (12:00 MYT)
- **Script:** `bf_unified.sh` at `/root/.hermes/scripts/`
- **Runs:** Daily at 12:00 MYT (after all daily cron uploads: Prayer 02:00, BD 06:00, BM 10:00-11:00)
- **Runners (in order):**
  1. `bf_gap_runner.py` — 1 first-time upload
  2. `bf_metadata_runner.py` — 1 metadata replacement
  3. `backfill_days.py --max-days 1` — 1 BM content generation
- **Dependency:** After all pipeline uploads complete. Backfill has clear air until next day's 02:00 Prayer run.

## Upload Gap Backfill (NEW)

For videos rendered locally but never uploaded. Found via pipeline wiki looper drift analysis.

**Queue format** (`state/upload_gap_queue.json`):

```json
{
  "gaps": [
    {
      "day": 30,
      "lang": "en",
      "pipeline": "prayer_en",
      "playlist_key": "prayer_en",
      "status_before": "rendering",
      "asset_dir": "/root/projects/prayer/assets/day_30",
      "state_file": "/root/projects/prayer/data/day_30_state.json",
      "has_video": true,
      "priority": 1,
      "done": false
    }
  ]
}
```

**Key fields:**
- `status_before`: `rendering` | `upload_error` | `uploaded_no_yt_id` | `render_missing`
- `render_missing` items need re-rendering before upload (skipped by runner)

**Current queue** (2026-07-07):

| Day | Lang | Status Before | Has Video | Priority |
|---|---|---|---|---|
| 28 | EN | upload_error | ✅ | 1 |
| 29 | EN | uploaded_no_yt_id | ✅ | 2 |
| 30-33, 35-37 | EN | rendering | ✅ | 3 |
| 30-37 | CN | rendering | ✅ | 3 |
| 34 | EN | render_missing | ❌ | 4 |

**18 total gaps** (17 upload-only, 1 needs re-render).

## Stats file

File: `/root/projects/pipeline_wiki/state/backfill_stats.json`
Updated after each run.

## Selection criteria

Candidates are videos with **views < 10** in Prayer EN/CN and BM EN/CN, sorted by oldest date first.

## ⚠️ YouTube Shadow Ban / Bulk Upload Threshold

### Known Thresholds (observed from our channel)

YouTube algorithm suppresses viewership when a channel uploads too many videos in a short window. Based on analysis of 401 videos on this channel:

| Uploads/day | Risk |
|---|---|
| 0-5 | ✅ Safe — normal viewership |
| 6-9 | ⚠️ Borderline — some suppression |
| 10-19 | 🔴 High risk — multiple 0-view videos |
| 20+ | 💀 Guaranteed shadow ban — almost all 0 views |

### Paradigm change (2026-08-01)

**Owner decision:** We are NO LONGER chasing views. New priority = **quality content + availability**. Every day's content should exist on YouTube even if some uploads get 0 views. Therefore:

1. **Daily upload limit raised from 5 to 15** (`BF_MAX_DAILY` env, default 15). This sits in the "High risk" band but guarantees content availability — the new goal.
2. **Gap runner now processes MULTIPLE uploads per run** (up to the daily budget), not 1. Each upload staggered ~30s (`BF_STAGGER_S`).
3. **Gap queue is auto-rebuilt** every backfill run (`rebuild_gap_queue.py`) from current local state, so every rendered-but-unuploaded video gets found.
4. **Residuals continue next day** — the queue persists; whatever doesn't upload today stays pending for tomorrow's 12:00 run.
5. **Records everything** — done log (`upload_gap_done.json`) + stats (`upload_gap_stats.json`) track every upload.

### Worst Incidents (historical — view-chasing era)

| Date | Uploads | Result |
|---|---|---|
| **Jun 21** | **34** | 9 zero-view videos, channel suppressed for days |
| **May 22** | **20** | Major launch batch, low views across board |
| Jun 18 | 18 | 4 zero-view videos from BD CN bulk |
| Jul 5 | 9 | 3 zero-view videos (BM Day 15 backfills + BD CN) |

### Rules for ALL upload pipelines (BM, Prayer, BD, backfill)

1. **Daily limit: 15 uploads/day** across all pipelines combined (env `BF_MAX_DAILY`). Old 5/day limit retired 2026-08-01 — availability over views.
2. **Backfills count toward the limit.** A backfill = 1 upload. Plan accordingly.
3. **Stagger uploads** — minimum 30 seconds between each upload (runner handles this).
4. **Never batch-upload** more than the daily budget at once. The runner stops at the budget; residuals queue for tomorrow.
5. **Backfill cadence: as many as possible per day**, up to the budget, then residuals continue next day.
6. Before any backfill, the runner checks: `(today's uploads in 24h) < budget`.

### 2026-08-05: BD 74-87 gap + oldest-first backlog fix

**Incident:** BD playlist jumped 73 → 88. Days 74-87 (EN+CN) were rendered but never uploaded.

**Root cause chain:**
1. Production for days 74-87 completed *after* the 06:00 MYT upload window (Whisper captioning bottleneck) → `run_upload_batch.py` saw `production=pending` and skipped.
2. Pre-Aug-1 backlog logic scanned **backward but broke at the first hit = NEWEST** missing day, starving the oldest content. So when the backlog fix landed (2026-08-01), it uploaded 88, 89, 90, 91, 92 first, never touching 74-87.
3. `bf_gap_runner.py` was queue-order bound (BD is last: `PIPE_ORDER` puts bd_en=4, bd_cn=5) and used `pr_upload.run()` (Prayer metadata) for BD items — wrong titles/playlist if it had reached them.

**Fixes (2026-08-05):**
- `run_upload_batch.py`: backward scan now collects ALL missed days and picks the **MINIMUM (oldest)** day first. Forward scan likewise.
- `bf_gap_runner.py`: BD items (`pipeline` starts with `bd_`) now dispatch to `bd_upload.run()` (correct BD titles/playlist), and parse `yt_video_id` from `youtube_url` (bd_upload writes URL, not ID). Raises if no ID produced.
- Backfilled via `modules/bd_backfill_7487.py` (one-off; oldest first; stops on quota).

**Backfill result (2026-08-05 08:34 MYT):** 20/28 uploaded ✅ (74-84 EN + 74-83 CN complete; 84 CN + 85 EN videos live but thumbnails pending). Hit YT quota wall (403) at day 85 — daily quota reset is 03:00 MYT. One-shot cron `49769f7f37cb` (03:05 MYT Aug 6) resumes: retries 84 CN + 85 EN thumbnails, uploads remaining 85 CN, 86 EN/CN, 87 EN/CN. Day 85 EN URL was manually patched into state (video was live but exception before state save — prevented duplicate).

**Pitfall for future gaps:** the daily 06:00 uploader only does **1 backlog day per language per run**. A gap >1 day will take N days to clear automatically — run the one-off backfill script (or wait) instead of assuming the cron drains the queue fast. Also: YT quota ≈ 1751 units/upload, 10K/day → **~5-6 uploads/day max across all pipelines**; the 15/day `BF_MAX_DAILY` cap is aspirational, quota is the real ceiling.

### 2026-08-06: BM dispatch bug in bf_gap_runner (3 wrong-branded videos)

**Incident:** On 2026-08-02 the gap runner uploaded 3 BM-content videos with **Prayer branding** (titles/descriptions/playlist):
- `bm_en day 59` → `g45Xuq5kzQM` "Daily Prayer — Day 59" (deleted 2026-08-06)
- `bm_cn day 41` → `eW729QgyKBA` "祷告 — 第41天" (deleted)
- `bm_cn day 43` → `_k4EYODGq3E` "祷告 — 第43天" (deleted)

**Root cause:** `bf_gap_runner.upload_gap()` dispatched ALL non-BD items through `pr_upload.run()`.
The Aug-5 BD fix only added a `bd_` branch — BM items still fell into the Prayer uploader.

**Fix (2026-08-06):** `upload_gap()` now dispatches `bm_*` items to `mb_upload.run(day, theme, sunday, script, asset_dir, lang)`. State write fixed too: BM always uses `upload` key (mb_state has no `upload_cn`), but BM CN daily writes `upload_cn`/`cn_status` — runner now handles both.
**Also fixed:** `rebuild_gap_queue.py` re-queued old-format BM days (uploaded via `meta.status` but no stored URL) as false gaps → duplicate-upload risk. Now skips days with `approval_status == 'uploaded'` or a `yt_video_id` in `upload` OR `upload_cn`.

**Rule:** when adding a pipeline branch to a shared backfill runner, ALWAYS verify the dispatcher covers ALL pipeline prefixes (`bd_`, `bm_`, `prayer_`) — a one-off fix for one pipeline silently misroutes the others.

### 0-View Video Scan (last run: 2026-07-06)

34 videos with 0 views detected. Breakdown:

- **BD CN (Bible In A Year Chinese)**: ~25 videos — bulk upload on Jun 18-21
- **BM Day 15 EN+CN**: 4 videos (originals + backfills) — re-uploaded on heavy days
- **Prayer backfills**: 2 videos (Day 25 EN, Day 26 EN) — uploaded Jul 2, Jul 5 (9-upload days)

These need to be cleaned up and re-uploaded **with staggering** (max 1-2/day).

### Cleanup Strategy

1. Delete all 0-view duplicates and bulk-upload casualties
2. Re-upload **at most 2 per day**, staggered by 2+ hours
3. Priority: BM/Prayer backfills first (higher value content), BD CN backlog last
4. Track in `state/zero_view_cleanup.json`

## Selection criteria

## Current queue

| # | Video ID | Pipeline | Day | Views | Title |
|---|---|---|---|---|---|
| 1 | AkK0je5H9GY | prayer_en | 25 | 0 | Grateful Heart — Day 25 |
| 2 | hNX9EmD7v0E | prayer_cn | 25 | 0 | 感恩的心 — 第25天 |
| 3 | eR37lWvqLpo | bm_cn | 30 | 0 | 当复发控制了你 — 第30天 |
| 4 | 450VCbnSZj8 | bm_en | 15 | 0 | When Depression Takes Over |
| 5 | 4iBQRtXMRjg | bm_cn | 15 | 0 | 当抑郁控制了你 — 第15天 |
| 6 | KIR1xzkMWOY | prayer_en | 40 | 10 | Evening Release — Day 40 |
| 7 | LmDb37P8yxY | prayer_en | 39 | 10 | Morning Surrender — Day 39 |
| 8 | K2caBGUdmME | prayer_en | 26 | 6 | Healing Prayer — Day 26 |
| 9 | 4PsCNbPq6to | prayer_en | 14 | 5 | Seeking Guidance — Day 14 |
| 10 | krU_k2Dq3N8 | prayer_en | 13 | 10 | Honest Repentance — Day 13 |
