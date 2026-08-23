#!/usr/bin/env python3
"""
bf_progress.py — Backfill mission progress report for the unified cron summary.

Reads backfill_queue.json + backfill_done.json and prints:
  - Mission-level % completion (content-corruption re-uploads vs metadata refresh)
  - Remaining days (pending, not done), grouped by mission
  - ETA in days (drains at the daily 5-upload budget)

Already-completed items are ignored entirely.
"""
import json, os, sys, datetime

QUEUE = '/root/projects/pipeline_wiki/state/backfill_queue.json'
DONE = '/root/projects/pipeline_wiki/state/backfill_done.json'

# Missions: (key, label)
# delete_old=True = content-corruption fixes (winky face, U+FFFD, markdown)
# delete_old=False/None = metadata refresh (0-view re-uploads)
def classify(item):
    if item.get('delete_old'):
        return 'corruption'
    return 'metadata'


def main():
    if not os.path.exists(QUEUE):
        print('  No backfill queue')
        return
    q = json.load(open(QUEUE)).get('backfills', [])
    done_vids = set()
    if os.path.exists(DONE):
        for d in json.load(open(DONE)):
            done_vids.add(d.get('video_id'))
        # Also mark items with new_video_id present as done (same thing)

    # Pending = queued but not done
    pending = [i for i in q if i['video_id'] not in done_vids]
    # Also account for items that were fully completed AND removed from queue
    # (backfill_done may hold entries no longer in the queue)

    # Per-mission totals = queued items for that mission (done ones may be
    # removed from queue after completion, so track via queue + done history)
    missions = {}
    for i in q:
        m = classify(i)
        missions.setdefault(m, {'total': 0, 'done': 0, 'pending': []})
        missions[m]['total'] += 1
        if i['video_id'] in done_vids:
            missions[m]['done'] += 1
        else:
            missions[m]['pending'].append(i)
    # Items in done but no longer in queue (fully finished & removed)
    done_only = [d for d in (json.load(open(DONE)) if os.path.exists(DONE) else [])
                 if d.get('video_id') not in {i['video_id'] for i in q}]
    for d in done_only:
        m = 'corruption' if d.get('delete_old') else 'metadata'
        # done_only entries may not carry delete_old — infer from pipeline bd_*
        if d.get('delete_old') is None:
            m = 'corruption' if str(d.get('pipeline', '')).startswith('bd_') else 'metadata'
        missions.setdefault(m, {'total': 0, 'done': 0, 'pending': []})
        missions[m]['total'] += 1
        missions[m]['done'] += 1

    order = [('corruption', 'Content fixes (re-upload + delete old)'),
             ('metadata', 'Metadata refresh (0-view re-upload)')]

    for key, label in order:
        if key not in missions:
            continue
        m = missions[key]
        total, done = m['total'], m['done']
        pct = (done / total * 100) if total else 0
        remaining = total - done
        days = (remaining + 4) // 5  # 5-upload daily budget
        print(f"  {label}: {done}/{total} done ({pct:.0f}%) — {remaining} remaining (~{days}d)")
        for i in sorted(m['pending'], key=lambda x: (x.get('pipeline', ''), x.get('day', 0))):
            print(f"    Day {i.get('day'):>3} {i.get('pipeline',''):<8} {i.get('video_id')}")


if __name__ == '__main__':
    main()
