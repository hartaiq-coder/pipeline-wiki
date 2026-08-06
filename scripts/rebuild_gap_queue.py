#!/usr/bin/env python3
"""Rebuild upload_gap_queue.json from CURRENT local state vs YouTube.
Scans BD, Prayer, BM for days with rendered final.mp4 but no yt_video_id.
Preserves existing pending entries, keeps done history as reference."""
import json, os, sys
from pathlib import Path

QUEUE_PATH = '/root/projects/pipeline_wiki/state/upload_gap_queue.json'

PLAYLIST_KEYS = {
    'prayer_en': 'prayer_en', 'prayer_cn': 'prayer_cn',
    'bd_en': 'bd_en', 'bd_cn': 'bd_cn',
    'bm_en': 'bm_en', 'bm_cn': 'bm_cn',
}

def load_json(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default if default is not None else {}

def video_ok(vp):
    return os.path.exists(vp) and os.path.getsize(vp) > 100_000

gaps = []

# ── BD ────────────────────────────────────────────────
BD = Path('/root/projects/bible_devotionals/data')
for lang, lkey in [('EN', 'en'), ('CN', 'cn')]:
    for p in sorted((BD / lang).glob('day_*.json'), key=lambda x: int(x.stem.split('_')[1])):
        d = int(p.stem.split('_')[1])
        try:
            dj = json.loads(p.read_text())
        except Exception:
            continue
        st = dj.get('status', {})
        assets = dj.get('assets', {})
        yt = assets.get('yt_video_id', '')
        if yt or st.get('uploading') == 'completed':
            continue  # already uploaded
        vp = assets.get('video_path', '') or assets.get('final_video', '')
        if not vp:
            vp = str(BD / lang / '..' / 'assets' / f'day_{d}' / lang / 'final.mp4')
        vp = str(Path(vp).resolve()) if vp else ''
        if video_ok(vp):
            gaps.append({
                'day': d, 'lang': lkey, 'pipeline': f'bd_{lkey}',
                'playlist_key': f'bd_{lkey}',
                'status_before': 'rendered_unuploaded',
                'asset_dir': str(Path(vp).parent),
                'state_file': str(p),
                'has_video': True,
                'priority': 1,
                'done': False,
            })

# ── Prayer ────────────────────────────────────────────
PR = Path('/root/projects/prayer')
for lang, lkey in [('EN', 'en'), ('CN', 'cn')]:
    for p in sorted(PR.joinpath('data').glob('day_*_state.json')):
        if '_state_' in p.name or '.bak' in p.name:
            continue
        d = int(p.stem.split('_')[1])
        try:
            dj = json.loads(p.read_text())
        except Exception:
            continue
        upl = dj.get('upload', {}) if lang == 'EN' else dj.get('upload_cn', {})
        if upl.get('yt_video_id'):
            continue
        vp = PR / 'assets' / f'day_{d}' / 'final.mp4'
        if video_ok(vp):
            gaps.append({
                'day': d, 'lang': lkey, 'pipeline': f'prayer_{lkey}',
                'playlist_key': f'prayer_{lkey}',
                'status_before': 'rendered_unuploaded',
                'asset_dir': str(vp.parent),
                'state_file': str(p),
                'has_video': True,
                'priority': 1,
                'done': False,
            })

# ── BM ────────────────────────────────────────────────
BM = Path('/root/projects/motivational-biblical')
for lang, lkey in [('EN', 'en'), ('CN', 'cn')]:
    for p in sorted(BM.joinpath('data').glob('day_*_state.json')):
        if '_state_' in p.name or '.bak' in p.name:
            continue
        d = int(p.stem.split('_')[1])
        try:
            dj = json.loads(p.read_text())
        except Exception:
            continue
        upl = dj.get('upload', {})
        upl_cn = dj.get('upload_cn', {})  # some BM CN uploads landed here
        # BM mostly stores under 'upload', but older CN uploads used 'upload_cn'.
        # Old-format states (meta.status) may be marked uploaded without URLs —
        # trust approval_status too so we don't re-queue live days (false gaps).
        status = dj.get('approval_status', dj.get('meta', {}).get('status', ''))
        if upl.get('yt_video_id') or upl_cn.get('yt_video_id') or status == 'uploaded':
            continue
        vp = BM / 'assets' / f'day_{d}' / 'final.mp4'
        if video_ok(vp):
            gaps.append({
                'day': d, 'lang': lkey, 'pipeline': f'bm_{lkey}',
                'playlist_key': f'bm_{lkey}',
                'status_before': 'rendered_unuploaded',
                'asset_dir': str(vp.parent),
                'state_file': str(p),
                'has_video': True,
                'priority': 1,
                'done': False,
            })

# Deduplicate by (day, lang, pipeline) — keep existing pending entries' fields
seen = set()
dedup = []
for g in gaps:
    key = (g['day'], g['lang'], g['pipeline'])
    if key in seen:
        continue
    seen.add(key)
    dedup.append(g)

# Priority order: oldest content first (BM started earliest → upload first)
PIPE_ORDER = {'bm_en': 0, 'bm_cn': 1, 'prayer_en': 2, 'prayer_cn': 3, 'bd_en': 4, 'bd_cn': 5}
gaps = sorted(dedup, key=lambda g: (PIPE_ORDER.get(g['pipeline'], 99), g['day']))

# Merge with existing queue: keep done entries + any pending not re-scanned
existing = load_json(QUEUE_PATH, {'gaps': []})
existing_gaps = existing.get('gaps', [])
new_pending_keys = {(g['day'], g['lang'], g['pipeline']) for g in gaps}
merged = [g for g in existing_gaps if g.get('done', False)]
# Replace pending with fresh scan (avoids stale status_before / missing files)
for g in gaps:
    merged.append(g)
# Re-dedup on merge
seen2 = set()
final = []
for g in merged:
    key = (g['day'], g['lang'], g['pipeline'])
    if key in seen2:
        continue
    seen2.add(key)
    final.append(g)

out = {'gaps': final, 'rebuilt_at': '2026-08-01T12:30:00+08:00'}
with open(QUEUE_PATH, 'w') as f:
    json.dump(out, f, indent=2, ensure_ascii=False)

pending = [g for g in final if not g.get('done', False)]
print(f'Queue rebuilt: {len(final)} entries ({len(pending)} pending)')
for g in sorted(pending, key=lambda x: (x['pipeline'], x['day'])):
    print(f'  {g["pipeline"]:12s} Day {g["day"]:3d} {g["lang"].upper()}  {g["asset_dir"]}')
