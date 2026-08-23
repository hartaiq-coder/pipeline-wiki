# SHARED INFRA — APIs, Quotas, Credentials, Servers

## Google Cloud

- **Project:** essential-wharf-492818-i4
- **YT API quota:** 10,000 units/day (hard limit).
  - Shared by BD, BM, Prayer.
  - Approx 6 uploads/day ≈ 10.5K units — **over limit already**.
  - Action needed: request 50K increase in Google Cloud Console.
  - Quota reset: midnight PT = 03:00 MYT.
- **OAuth client:** see BD EN scripts; token stored in Drive config per service account pattern.

## Nous / LLM

- Active provider: `deepseek`
- Default model: `deepseek-v4-pro`
- Base URL: `https://api.deepseek.com/v1`
- Coder profile (heavy): `deepseek-v4-flash`
- Nous provider available as fallback (OAuth-based, requires periodic re-auth)
- Agent jobs inherit `default` profile model/provider.
- Pre-cron auth refresh via `/root/.hermes/scripts/refresh_nous.sh` for `no_agent` jobs

## Cloudflare

- Zones: `bacakomen.xyz`, `nikkohosting.com`
- Wrapper: `/usr/local/bin/cf` sources `/root/.cloudflare`

## Discord

- Guild: MyWorkspace (1512264737239466085)
- Gateway via platforms/discord plugin
- User: Bobby#7912
- Config: require_mention=false, 5 free_response_channels

## Telegram

- Home chat ID: 80119937
- Streaming enabled.

## YouTube Upload Targets

| Pipeline | Lang | Playlist ID |
|------|-----------|
| BD | EN | PLgsAd6HNQy7nuCC7d05oBM8x1Vt_iEGnF |
| BD | CN | PLgsAd6HNQy7lj_ur2Gcv2tHoj3tODVZ2Y |
| Prayer | EN | PLgsAd6HNQy7mJBtui-DpTL-QJKeP4CjDW |
| Prayer | CN | PLgsAd6HNQy7lpA3YbFReNwqFiMqoOCWi1 |
| BM | EN | PLgsAd6HNQy7mCkZFi9VNkBUMUuKPEqxoI |
| BM | CN | PLgsAd6HNQy7mq_CFgbfWhTQSh_qeFMSQL |
| Prayer (dedicated) | CN | PLgsAd6HNQy7lpA3YbFReNwqFiMqoOCWi1 |

## Backfill

- **Unified cron:** `675cf9bb73b2` at 12:00 MYT (moved from 09:00 to avoid 08:00-11:00 upload cluster)
- **Script:** `bf_unified.sh` at `/root/.hermes/scripts/`
- Scripts: `/root/projects/pipeline_wiki/scripts/`
  - `bf_gap_runner.py` — first-time upload gap filler
  - `bf_metadata_runner.py` — 0-view metadata replacement
- Queues: `/root/projects/pipeline_wiki/state/`
  - `upload_gap_queue.json`
  - `backfill_queue.json`
- Rules: `/root/projects/pipeline_wiki/BACKFILL_RULES.md`

## Script Naming Convention

All pipeline scripts follow: `{pipeline}_{action}.{ext}`

| Prefix | Pipeline | Example |
|---|---|---|
| `bd` | Bible Devotionals | `bd_upload_batch.py` |
| `pr` | Prayer | `pr_daily_en.py` |
| `bm` | Biblical Motivation | `bm_daily_cn.py` |
| `bf` | Backfill / shared infra | `bf_gap_runner.py` |

Language suffix (when script is lang-specific): `_en`, `_cn`, `_all`.

Wrapper/shell scripts follow the same convention (e.g., `bm_daily_cn.sh`, `bf_unified.sh`).

## Known Bugs & Fixes

### 2026-07-05: YouTube Playlist Duplicate (Day 62)

**Bug:** `youtube_upload.py` `upload_video()` retried playlist insert when verification failed due to YouTube eventual consistency. YouTube does NOT reject duplicate playlistItems for the same video, so the retry created real duplicates.

**Symptom:** BD EN Day 62 (`t62mh1o6JS4`) appeared twice in playlist at positions 61 & 62 (18s apart = 2s verify + 15s retry wait).

**Fix:** Insert → mark `playlist_added = True` → wait 120s → verify via `_video_in_playlist()` for **logging only**. NEVER retry the insert — YouTube doesn't reject duplicate playlistItems, so a retry creates real duplicates.

**File:** `/root/projects/bible_devotionals/modules/youtube_upload.py` (line ~329)

## DeepSeek Balance

- Logger job: every 6h (`log_deepseek_balance.py`)

## Translation Providers

- Primary: Nous (`inference-api.nousresearch.com/v1`)
- Fallback: DeepSeek
- Removed: Gemini (auth broken for individual accounts; 256-char limit fallback unreliable)
- Wrapper modules:
  - `/root/projects/motivational-biblical/modules/nous_fallback.py`
  - `/root/projects/prayer/modules/nous_fallback.py`
- Refactor applied to:
  - `mb_script.py`, `mb_pexels.py`
  - `pr_script.py`, `pr_translate.py`
  - `refresh_themes.sh`

## Bible Texts

- Local KJV corpus (persistent): `/root/projects/bible_devotionals/data/kjv_verses.json` (66 books, 31,102 verses, full KJV)
- Local KJV corpus (runtime copy): `/tmp/kjv_verses.json` (volatile — get_kjv_text prefers the persistent copy)
- Local CUV corpus (persistent): `/root/projects/bible_devotionals/data/zh_cuv.json` (66 books, BOM-aware)
- Local CUV corpus (runtime copy): `/tmp/zh_cuv.json` (volatile — get_cuv_text prefers the persistent copy)
- Both pipelines now use local-first lookup; external APIs are fallback only
- EN getter: `modules/bible_devotional_pipeline.py::get_kjv_text()`
- CN getter: `modules/bible_cuv_pipeline.py::get_cuv_text()`
- **Text quality gate (2026-08-07):** `modules/bd_text_quality.py` runs before gathering-save and before TTS — blocks on emoji, TTS leak phrases ("winky face"), cross-language mutation (CJK in EN / latin in CN), markdown/LLM artifacts, U+FFFD replacement chars, HTML/URLs in scripture. Warnings logged for emoticons (auto-fixed) and punctuation anomalies. Audit all days/SRTs: `scan_text_quality.py`. Status set to `blocked_quality` when a day fails the gate.
- **Emoticon sanitization (2026-08-07):** edge-tts speaks `;)` / `:)` as "winky face" / "smiley". KJV parentheticals like `(the same [is] Zoar;)` triggered this in 11 live EN videos (days 33, 43, 46, 54, 66, 67, 70, 74, 75, 78, 79). Fix: `sanitize_scripture_text()` in `bible_devotional_pipeline.py` strips `;`/`:` + adjacent paren; applied in `_clean_verse_separators`, `bd_tts.py` (defense-in-depth), and to the whole corpus + all day JSONs via `sanitize_bible_corpus.py`. Re-uploads queued via backfill manager (`delete_old=True`). Rebuild corpus anytime: `fetch_kjv_corpus.py`.
- **CUV corruption fix (2026-08-07):** bolls.life upstream returns U+FFFD at 5 spots (Jer 29:6 裡, Matt 6:19-20 銹, Col 1:29 裡, James 5:3 鏽). Repaired via `fix_cuv_corpus.py` with known-correct traditional CUV chars; CN day 6 re-pulled.

## Bible Reading Plan

- Replanned 2026-07-01 narration to align with locked days 1–62 for existing assets; days 63–365 use a fresh verified sequence.
- EN/CN both updated to match; Day 365 = Malachi / Revelation / Psalms end.

## BM CN Daily

- `run_daily_cn.py` is now **translation-only**.
- It ignores `themes.json`; it picks the latest EN `day_*_state.json` with a real `script` and translates/render/uploads that.
- First restored upload after decoupling: YT `R7Lvq_gt4Wg`, IG `18079152638281941`

## OS / Runtime

- Linux 6.8.0-106-generic
- Root home: `/root`
- Python venv active for all scripts.
- Hermes cron timeout: 1800s

## Credential Rule

- Never hardcode tokens. Load from:
- `/root/projects/.env.discord`
- `/root/projects/bible_devotionals/.env`
- `/root/projects/prayer/assets/.env`
- `/root/projects/motivational-biblical/.env`
- Drive service account JSON (path inside script)

## Storage / Runtime Notes

- We use Hermes Agent for narrative files and docs such as this wiki.
- For large binary or runtime state files (`/tmp/kjv_verses.json`, `/tmp/zh_cuv.json`, render outputs, media assets), Hermes does **not** manage binary payloads or `/tmp` state; those are handled by project scripts/terminal sessions directly.


**Last Verified** | 2026-07-01 12:10 MYT
