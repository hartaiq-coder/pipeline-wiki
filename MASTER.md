# Pipeline Wiki — Master Index

> **Single source of truth for BD, BM, Prayer pipelines.**
> Agents MUST read the relevant section file(s) before making any external API call.
> If `last_verified` is within 24h, trust it. If stale, trigger the looper.

---

## Quick Nav

- [BD EN](BD_EN.md) — Bible Devotionals English pipeline
- [BD CN](BD_CN.md) — Bible Devotionals Chinese pipeline
- [BM EN](BM_EN.md) — Biblical Motivation English pipeline
- [BM CN](BM_CN.md) — Biblical Motivation Chinese pipeline
- [PRAYER EN](PRAYER_EN.md) — Prayer English pipeline
- [PRAYER CN](PRAYER_CN.md) — Prayer Chinese pipeline
- [SHARED INFRA](SHARED_INFRA.md) — APIs, quotas, credentials, shared infra

---

## IDs & URLs

| ID | Value | Where used |
|----|-------|------------|
| YT Channel (Caddy Khaw) | UCPmKHR0GAcqv4ylvvKpeuJw | All uploads |
| YT Upload Playlist | (see script config) | BD uploads |
| CF Zone 1 | bacakomen.xyz | hosting |
| CF Zone 2 | nikkohosting.com | hosting |
| GCloud Project | essential-wharf-492818-i4 | YT API, Drive |

- Facebook/Instagram post IDs: tracked per-day in state files under `data/`
- BD latest day: see `BD_EN.md` → Current Progress
- Prayer latest day: see `PRAYER_EN.md`

---

## Schedules

| Time (MYT) | Job | Script |
|---|---|---|
| 00:00 | BD Daily Prep | `run_daily_bible.sh` |
| 02:00 | Prayer EN Daily | agent prompt |
| 02:30 | Prayer CN Daily | `prayer_daily_cn.sh` |
| 04:30 (daily) | **Pipeline Wiki Looper** | `pipeline_wiki_looper_force.sh` |
| 05:00 (Sun) | Weekly Asset Cleanup | `cleanup_assets.py` |
| 05:30 (Sun) | Cross-Platform Weekly Report | `cross_platform_report.py` |
| 06:00 | Bible Daily Upload | `bd_upload.py` |
| 07:00 | IG Metrics | `bd_ig_metrics.py` |
| 07:10 | FB Metrics | `bd_fb_metrics.py` |
| 07:20 | Social Dashboard | `bd_socialdash.py` |
| 07:30 | Bible Social Digest (FB+IG) | `bd_digest_001` agent prompt |
| 08:00 | BDCN CTA Correction | `replace_cn_cta.py` |
| 09:00 | Backfill (Prayer/BM) | `backfill_run.py` |
| 10:00 | BM EN Daily | agent prompt |
| 11:00 | BM CN Daily | `run_mb_cn.sh` |
| 04:00 (Mon-Fri) | BM CN Daily Backfill | `backfill_mb.sh` |

---

## Quota

- **YT API:** 10,000 units/day (project: essential-wharf-492818-i4).
  - Shared by BD + BM + Prayer (3 pipelines).
  - Approximate cost: 6 uploads/day ≈ 10,500 units — **exceeds limit**.
  - Fix: request 50K quota increase in Google Cloud Console.
  - Strategy for looper: **only call YT APIs if local state files are missing IDs or metrics timestamps are stale.**
- **LLM:** DeepSeek `deepseek-v4-pro` for agent/coder; DeepSeek `deepseek-v4-flash` for all pipeline generation & translation (content scripts, fallbacks).
- **Prayer Pipeline v2:** Current-events-driven. Research cron at 01:30 MYT scrapes economy/warfare/social/disaster headlines. Mon-Fri prayers address real headlines. Sat = community intercession with #prayerrequest CTA. Sun = Jesus worship aligned with BM Jesus Sunday.
- **TTS:** varies by pipeline, uses local cache aggressively.

---

## Known Issues & Rules

- **Contamination**: CN pipeline translated from EN via LLM. Must have `validate_cn_content` pass before TTS/upload. If fails, mark `contaminated: true` and trigger backfill.
- **Tone (BD EN)**: "Key takeaway:" label in TTS, then warm hook → hard biblical truth → sharp question. ~450-500 chars, 2-4 sentences. Like a friend who loves you enough to tell you hard truth.
- **Schedule preference**: 07:00 AM MYT for morning-facing outputs.
- **No hardcoded tokens**: always source from `.env` files.
- **Fixing scripts**: fix the actual script, never manual workarounds.

---

## State Schema Standard

Every pipeline day state file must conform to:
```json
{
  "meta": {
    "project": "BD",
    "lang": "EN",
    "day": 52,
    "date": "2026-06-18",
    "weekday": "Thursday",
    "status": "uploaded",
    "stage": "production",
    "last_modified": "2026-06-27T08:00:25Z",
    "modified_by": "script_name.py"
  },
  "readings": { "ot1": "Genesis 1-2", "ot2": "...", "nt": "...", "wisdom": "..." },
  "content": {
    "title": "...",
    "description": "...",
    "takeaways": {"ot1":"...",...},
    "prayer": "...",
    "scripture_full_text": {}
  },
  "media": {
    "image": "/abs/path",
    "thumbnail": "/abs/path",
    "duration_seconds": 52,
    "resolution": "1080x1920"
  },
  "uploads": {
    "youtube": {"video_id":"...","url":"...","playlist_id":"...","uploaded_at":"...","status":"public"},
    "facebook": {"post_id":"...","url":"..."},
    "instagram": {"post_id":"...","url":"..."}
  },
  "metrics": {
    "youtube": {"views":0,"likes":0,"collected_at":"..."},
    "last_synced": "2026-06-27T07:20:29Z"
  },
  "flags": {
    "contaminated": false,
    "needs_backfill": false,
    "qa_approved": true
  }
}
```

---

## Storage

- Wiki root: `/root/projects/pipeline_wiki/`
- State snapshots: `/root/projects/pipeline_wiki/state/next_days.json`, `/root/projects/pipeline_wiki/state/links.json`
- Legacy state dirs (migration targets):
  - BD: `/root/projects/bible_devotionals/data/`
  - Prayer: `/root/projects/prayer/data/`
  - BM: `/root/projects/motivational-biblical/data/`

---

## Agent Contract

1. **Before any external API call**, read the relevant `*_EN.md` or `*_CN.md` from `/root/projects/pipeline_wiki/`.
2. If `last_verified` < 24h, proceed using wiki data.
3. If stale, run/check `pipeline_wiki_looper.py` output.
4. **Do not** re-discover IDs/credentials/strategy by hitting live APIs.
5. Update schema-compliant state file after every stage change.
