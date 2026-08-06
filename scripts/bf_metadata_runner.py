#!/usr/bin/env python3
"""Daily backfill: upload replacement video, clean old from playlist, add new."""
import os, sys, subprocess, json, time
from pathlib import Path

sys.path.insert(0, '/root/projects/bible_devotionals/modules')
from youtube_upload import get_credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

QUEUE_PATH = '/root/projects/pipeline_wiki/state/backfill_queue.json'
DONE_PATH = '/root/projects/pipeline_wiki/state/backfill_done.json'
LOG_PATH = '/root/projects/pipeline_wiki/state/backfill_stats.json'

PLAYLIST_IDS = {
    'prayer_en': 'PLgsAd6HNQy7mJBtui-DpTL-QJKeP4CjDW',
    'prayer_cn': 'PLgsAd6HNQy7lpA3YbFReNwqFiMqoOCWi1',
    'bm_en': 'PLgsAd6HNQy7mCkZFi9VNkBUMUuKPEqxoI',
    'bm_cn': 'PLgsAd6HNQy7mq_CFgbfWhTQSh_qeFMSQL',
}


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict) and 'backfills' in data and isinstance(data['backfills'], list):
            return data['backfills']
        if isinstance(data, list):
            return data
        return default
    return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def next_video():
    queue = load_json(QUEUE_PATH, [])
    done = load_json(DONE_PATH, [])
    done_ids = {d['video_id'] for d in done}
    for item in queue:
        if item['video_id'] not in done_ids:
            return item
    return None


def extract_thumb(video_path: str, asset_dir: str) -> str | None:
    thumb = Path(asset_dir) / 'thumbnail.jpg'
    if thumb.exists():
        return str(thumb)
    try:
        proc = subprocess.run(
            ['ffmpeg', '-y', '-ss', '00:00:00.5', '-i', str(video_path),
             '-vframes', '1', '-q:v', '2', str(thumb)],
            capture_output=True, text=True, timeout=30,
        )
        if thumb.exists():
            return str(thumb)
    except Exception as e:
        print(f'  Thumbnail extraction failed: {e}', flush=True)
    return None


def process(item):
    creds = get_credentials()
    yt = build('youtube', 'v3', credentials=creds)
    print(f'Processing: {item["title"][:60]}')

    video_path = str(Path(item['asset_dir']) / 'final.mp4')
    if not Path(video_path).exists():
        raise FileNotFoundError(f'Video not found: {video_path}')

    # 1. Upload replacement
    thumb_path = extract_thumb(video_path, item['asset_dir'])
    media_video = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    body = {
        'snippet': {
            'title': item['title'],
            'description': item['description'],
            'tags': item['tags'],
            'categoryId': '27',
            'defaultLanguage': 'zh' if item['lang'] == 'cn' else 'en',
            'defaultAudioLanguage': 'zh' if item['lang'] == 'cn' else 'en',
        },
        'status': {'privacyStatus': 'public'},
    }
    resp = yt.videos().insert(part='snippet,status', body=body, media_body=media_video).execute()
    new_vid = resp['id']
    print(f'  Uploaded new: {new_vid}')

    # 2. Upload thumbnail
    if thumb_path:
        try:
            media_thumb = MediaFileUpload(thumb_path, mimetype='image/jpeg', resumable=False)
            yt.thumbnails().set(videoId=new_vid, media_body=media_thumb).execute()
            print(f'  Thumbnail uploaded')
        except Exception as e:
            print(f'  Thumbnail FAILED: {e}')

    # 3. Remove old from playlist if present
    old_pl_id = PLAYLIST_IDS.get(item.get('playlist_key'))
    if old_pl_id:
        try:
            page_token = None
            old_pl_item_id = None
            while True:
                resp = yt.playlistItems().list(
                    part='snippet', playlistId=old_pl_id, maxResults=50, pageToken=page_token
                ).execute()
                for pi in resp.get('items', []):
                    if pi['snippet']['resourceId']['videoId'] == item['video_id']:
                        old_pl_item_id = pi['id']
                        break
                if old_pl_item_id or not page_token:
                    break
                page_token = resp.get('nextPageToken')
            if old_pl_item_id:
                yt.playlistItems().delete(id=old_pl_item_id).execute()
                print(f'  Removed old from playlist')
        except Exception as e:
            print(f'  Remove old from playlist FAILED: {e}')

    # 4. Add new to playlist
    if old_pl_id:
        try:
            yt.playlistItems().insert(
                part='snippet',
                body={'snippet': {'playlistId': old_pl_id, 'resourceId': {'kind': 'youtube#video', 'videoId': new_vid}}}
            ).execute()
            print(f'  Added new to playlist')
        except Exception as e:
            print(f'  Add new to playlist FAILED: {e}')

    return new_vid


def count_todays_uploads() -> int:
    """Count how many videos were uploaded to the channel in the last 24h."""
    try:
        creds = get_credentials()
        yt = build('youtube', 'v3', credentials=creds)
        from datetime import datetime, timedelta, timezone

        # Get channel ID first
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
        return 999  # fail-safe: assume too many

MAX_DAILY_UPLOADS = int(os.environ.get('BF_MAX_DAILY', '15'))

def main():
    # Check daily upload limit before proceeding
    today_count = count_todays_uploads()
    print(f'Uploads in last 24h: {today_count} / {MAX_DAILY_UPLOADS} limit')
    if today_count >= MAX_DAILY_UPLOADS:
        print(f'SKIPPING: Daily upload limit ({MAX_DAILY_UPLOADS}) reached. Try again tomorrow.')
        return

    item = next_video()
    if not item:
        print('Queue empty.')
        return

    print(f'Backfill target: {item["video_id"]}')
    new_vid = process(item)

    # Mark done
    done = load_json(DONE_PATH, [])
    done.append({
        'video_id': item['video_id'],
        'new_video_id': new_vid,
        'pipeline': item.get('pipeline'),
        'lang': item.get('lang'),
        'day': item.get('day'),
        'title': item['title'],
        'done_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    })
    save_json(DONE_PATH, done)

    # Update stats
    queue = load_json(QUEUE_PATH, [])
    stats = {
        'total': len(queue),
        'done': len(done),
        'remaining': len(queue) - len(done),
        'last_run': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'last_video': item['video_id'],
        'new_video': new_vid,
    }
    save_json(LOG_PATH, stats)
    print(f'Done. Remaining: {stats["remaining"]}')


if __name__ == '__main__':
    main()
