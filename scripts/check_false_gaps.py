#!/usr/bin/env python3.12
"""Check which gap-queue entries are FALSE gaps (already live on YouTube)."""
import json, re, os

# Load gap queue
gq = json.load(open('/root/projects/pipeline_wiki/state/upload_gap_queue.json'))
gaps = gq.get('gaps', gq) if isinstance(gq, dict) else gq
pending = [g for g in gaps if not g.get('done', False)]

print(f'Pending gaps: {len(pending)}')
for g in sorted(pending, key=lambda x: (x.get('pipeline',''), x.get('day',0))):
    pl = g.get('pipeline', '?')
    day = g.get('day', '?')
    lang = g.get('lang', '?')
    state_file = g.get('state_file', '')
    # Load state
    status = '?'
    yt_in_state = ''
    if state_file and os.path.exists(state_file):
        try:
            d = json.load(open(state_file))
            if pl.startswith('prayer'):
                key = 'cn_status' if lang == 'cn' else 'approval_status'
                status = d.get(key, '?')
                upl = d.get('upload_cn' if lang == 'cn' else 'upload', {})
            elif pl.startswith('bd'):
                status = d.get('status', {}).get('uploading', '?')
                upl = d.get('assets', {})
            else:  # bm
                status = d.get('approval_status', d.get('meta', {}).get('status', '?'))
                upl = d.get('upload', {})
            yt_in_state = upl.get('yt_video_id', '') or upl.get('yt_url', '') or upl.get('youtube_url', '')
        except Exception as e:
            status = f'ERR {e}'
    flag = ''
    if status == 'uploaded':
        flag = '⚠️ FALSE GAP — state says uploaded (URL missing from old-format state)'
    print(f'  {pl:<12} day={day:<4} lang={lang} state_status={status} yt_in_state={bool(yt_in_state)} {flag}')
