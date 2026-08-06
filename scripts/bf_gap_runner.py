#!/usr/bin/env python3
"""Upload gap runner — processes ALL pending first-time uploads per run.
Respects configurable daily limit (env BF_MAX_DAILY, default 15).
User paradigm 2026-08-01: quality content + availability over view-chasing,
so upload as many as possible each run, record results, residuals continue
tomorrow's run (queue persists)."""
import os, sys, json, subprocess, time
from pathlib import Path
from datetime import datetime, timezone, timedelta

QUEUE_PATH = '/root/projects/pipeline_wiki/state/upload_gap_queue.json'
DONE_PATH  = '/root/projects/pipeline_wiki/state/upload_gap_done.json'
LOG_PATH   = '/root/projects/pipeline_wiki/state/upload_gap_stats.json'

MAX_DAILY = int(os.environ.get('BF_MAX_DAILY', '15'))  # was 5 — raised per new paradigm
STAGGER_S = int(os.environ.get('BF_STAGGER_S', '30'))  # min seconds between uploads

sys.path.insert(0, '/root/projects/prayer')
sys.path.insert(0, '/root/projects/prayer/modules')
sys.path.insert(0, '/root/projects/bible_devotionals/modules')
sys.path.insert(0, '/root/projects/bible_devotionals')


def load_json(path, default=None):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def count_todays_uploads():
    """Count uploads in last 24h using YouTube API."""
    try:
        from youtube_upload import get_credentials
        from googleapiclient.discovery import build
        creds = get_credentials()
        yt = build('youtube', 'v3', credentials=creds)
        channel_resp = yt.channels().list(part='id', mine=True).execute()
        channel_id = channel_resp['items'][0]['id']
        yesterday = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        count = 0
        page_token = None
        while True:
            resp = yt.search().list(
                part='id', channelId=channel_id, type='video', maxResults=50,
                publishedAfter=yesterday, pageToken=page_token
            ).execute()
            count += len(resp.get('items', []))
            page_token = resp.get('nextPageToken')
            if not page_token:
                break
        return count
    except Exception as e:
        print(f'  [WARN] Could not count uploads: {e}')
        return 999


def extract_thumb(video_path, asset_dir):
    """Extract thumbnail from video at 0.5s mark."""
    thumb = Path(asset_dir) / 'thumbnail.jpg'
    if thumb.exists():
        return str(thumb)
    try:
        subprocess.run([
            'ffmpeg', '-y', '-ss', '00:00:00.5', '-i', str(video_path),
            '-vframes', '1', '-q:v', '2', str(thumb)
        ], capture_output=True, text=True, timeout=30)
        if thumb.exists():
            return str(thumb)
    except Exception as e:
        print(f'  Thumb extraction failed: {e}')
    return None


def upload_gap(item):
    """Upload a single gap item using pr_upload.run()."""
    day = item['day']
    lang = item['lang']
    asset_dir = item['asset_dir']
    state_file = item['state_file']
    video_path = str(Path(asset_dir) / 'final.mp4')

    if not Path(video_path).exists():
        raise FileNotFoundError(f'Video missing: {video_path}')

    # BD items use the BD uploader (BD titles/descriptions/playlist differ
    # from Prayer/BM). bd_upload.run() updates the state file itself.
    pipeline = item.get('pipeline', '')
    if pipeline.startswith('bd_'):
        from bd_upload import run as bd_upload_run
        bd_upload_run(lang.upper(), day)
        st = load_json(state_file)
        # bd_upload writes youtube_url (not yt_video_id) — parse the ID
        yt_id = st.get('assets', {}).get('yt_video_id', '')
        if not yt_id:
            yt_url = st.get('assets', {}).get('youtube_url', '')
            if 'v=' in yt_url:
                yt_id = yt_url.split('v=')[-1]
            elif 'youtu.be/' in yt_url:
                yt_id = yt_url.split('youtu.be/')[-1]
        if not yt_id:
            raise RuntimeError(
                f'BD upload for day {day} {lang.upper()} did not produce a video ID '
                f'(check state file: {state_file})'
            )
        return yt_id

    # Load state for script info
    state = load_json(state_file)
    if lang == 'cn':
        script_data = state.get('script_cn', {})
    else:
        script_data = state.get('script', {})

    prayer_type = state.get('prayer_type', '')
    scripture = script_data.get('scripture', '')
    prayer_text = script_data.get('full_text', '')
    hashtags = script_data.get('hashtags', [])

    # Extract thumbnail
    thumb_path = extract_thumb(video_path, asset_dir)

    # BM items must use the BM uploader (BM titles/descriptions/playlist).
    # Using pr_upload for BM produces Prayer-branded videos (bug 2026-08-02).
    if pipeline.startswith('bm_'):
        from mb_upload import run as mb_upload_run
        theme = state.get('theme', '')
        sunday = state.get('sunday', False)
        result = mb_upload_run(day, theme, sunday, script_data, asset_dir, lang=lang)
        yt_id = result.get('yt_video_id', '')
        yt_url = result.get('yt_url', '')
        ig_id = result.get('ig_post_id', '')
    else:
        from pr_upload import run as run_upload
        result = run_upload(
            day, prayer_type, scripture, prayer_text, hashtags,
            asset_dir, lang=lang
        )
        yt_id = result.get('yt_video_id', '')
        yt_url = result.get('yt_url', '')
        ig_id = result.get('ig_post_id', '')

    # Update state file — handle both Prayer/BM and BD file structures
    pipeline = item.get('pipeline', '')
    if pipeline.startswith('bd_'):
        # BD day files: assets + status.uploading (no upload_cn / assets_cn keys)
        state.setdefault('assets', {})['youtube_url'] = yt_url
        if yt_id:
            state['assets']['yt_video_id'] = yt_id
            state['assets']['final_video'] = video_path
        state.setdefault('status', {})['uploading'] = 'completed'
    else:
        # Prayer: upload / upload_cn + assets / assets_cn + approval_status / cn_status
        # BM: always uses 'upload' (no upload_cn / assets_cn keys in mb_state).
        if pipeline.startswith('bm_'):
            upload_key = 'upload'
            status_key = 'cn_status' if lang == 'cn' else 'approval_status'
        else:
            upload_key = 'upload_cn' if lang == 'cn' else 'upload'
            status_key = 'cn_status' if lang == 'cn' else 'approval_status'
        state[upload_key] = {
            'yt_video_id': yt_id,
            'yt_url': yt_url,
            'ig_post_id': ig_id,
            'ig_url': result.get('ig_url', ''),
        }
        if yt_id:
            state['assets' if lang == 'en' else 'assets_cn']['final_video'] = video_path
        state[status_key] = 'uploaded'
    state['updated_at'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    save_json(state_file, state)

    return yt_id


def main():
    queue = load_json(QUEUE_PATH, {'gaps': []})
    gaps = queue.get('gaps', [])

    # All pending gaps
    pending = [g for g in gaps if not g.get('done', False)]
    if not pending:
        print('Queue empty — all gaps processed.')
        return

    print(f'Pending gaps: {len(pending)} (max {MAX_DAILY} per run)')

    # Check daily limit once
    today_count = count_todays_uploads()
    print(f'Uploads in last 24h: {today_count} / {MAX_DAILY} limit')
    if today_count >= MAX_DAILY:
        print(f'SKIPPING: Daily upload limit ({MAX_DAILY}) reached.')
        return
    budget = MAX_DAILY - today_count

    # Process gaps until budget exhausted
    uploaded = 0
    for item in pending:
        if uploaded >= budget:
            print(f'  (Budget exhausted — {budget} uploaded this run, residuals continue tomorrow)')
            break

        # Skip items with missing video files (zombie entries)
        video_path_check = str(Path(item['asset_dir']) / 'final.mp4')
        if not Path(video_path_check).exists() or Path(video_path_check).stat().st_size < 100_000:
            lang_upper = item['lang'].upper()
            print(f'Day {item["day"]} {lang_upper}: video missing — marking as removed (zombie entry).')
            item['done'] = True
            item['done_at'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            item['removed_reason'] = 'video file missing — zombie entry'
            save_json(QUEUE_PATH, queue)
            continue

        day_str = str(item['day'])
        lang_str = item['lang'].upper()
        pipeline = item['pipeline']
        asset_dir = item['asset_dir']
        status_before = item['status_before']
        print(f'Gap target: Day {day_str} {lang_str} — {pipeline}')
        print(f'  Asset dir: {asset_dir}')
        print(f'  Status before: {status_before}')

        try:
            yt_id = upload_gap(item)
        except Exception as e:
            print(f'  ❌ Upload FAILED for Day {day_str} {lang_str}: {e}')
            item['done'] = True
            item['done_at'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            item['removed_reason'] = f'upload error: {str(e)[:100]}'
            save_json(QUEUE_PATH, queue)
            continue

        print(f'  ✅ Uploaded: {yt_id}')

        # Mark done
        item['done'] = True
        item['done_at'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        item['new_video_id'] = yt_id
        save_json(QUEUE_PATH, queue)

        # Update done log
        done = load_json(DONE_PATH, [])
        done.append({
            'day': item['day'], 'lang': item['lang'],
            'pipeline': item['pipeline'], 'new_video_id': yt_id,
            'done_at': item['done_at'],
        })
        save_json(DONE_PATH, done)

        uploaded += 1
        if uploaded < budget:
            print(f'  (staggering {STAGGER_S}s before next upload...)')
            time.sleep(STAGGER_S)

    # Stats
    remaining = len([g for g in gaps if not g.get('done', False)])
    done = load_json(DONE_PATH, [])
    stats = {
        'total': len(gaps),
        'done': len(done),
        'remaining': remaining,
        'last_run': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'uploaded_this_run': uploaded,
        'last_video': item.get('new_video_id', ''),
    }
    save_json(LOG_PATH, stats)
    print(f'Done. Uploaded {uploaded} this run. Remaining gaps: {remaining} (continue tomorrow).')


if __name__ == '__main__':
    main()
