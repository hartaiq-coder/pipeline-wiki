#!/usr/bin/env python3
"""
pipeline_wiki_looper.py
Reality checker for BD / BM / Prayer pipelines.
- Reads local state files and YouTube playlists
- Writes truth to wiki section files
- Updates state/next_days.json and state/links.json
"""
import argparse, json, os, re, sys, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    HAS_YT = True
except ImportError:
    HAS_YT = False

WIKI_DIR = "/root/projects/pipeline_wiki"
STATE_DIR = os.path.join(WIKI_DIR, "state")
MAX_STALENESS = timedelta(hours=24)

PROJECT_ROOTS = {
    "BD": "/root/projects/bible_devotionals",
    "BM": "/root/projects/motivational-biblical",
    "PRAYER": "/root/projects/prayer",
}

PLAYLISTS = {
    "BD_EN": "PLgsAd6HNQy7nuCC7d05oBM8x1Vt_iEGnF",
    "BD_CN": "PLgsAd6HNQy7lj_ur2Gcv2tHoj3tODVZ2Y",
    "PRAYER_EN": "PLgsAd6HNQy7mJBtui-DpTL-QJKeP4CjDW",
    "PRAYER_CN": "PLgsAd6HNQy7lpA3YbFReNwqFiMqoOCWi1",
    "BM_EN": "PLgsAd6HNQy7mCkZFi9VNkBUMUuKPEqxoI",
    "BM_CN": "PLgsAd6HNQy7mq_CFgbfWhTQSh_qeFMSQL",
}

THEME_FILES = {
    "BM": "/root/projects/motivational-biblical/data/themes.json",
    "PRAYER": "/root/projects/prayer/data/themes.json",
}

SECTION_FILES = {
    "BD_EN": os.path.join(WIKI_DIR, "BD_EN.md"),
    "BD_CN": os.path.join(WIKI_DIR, "BD_CN.md"),
    "BM_EN": os.path.join(WIKI_DIR, "BM_EN.md"),
    "BM_CN": os.path.join(WIKI_DIR, "BM_CN.md"),
    "PRAYER_EN": os.path.join(WIKI_DIR, "PRAYER_EN.md"),
    "PRAYER_CN": os.path.join(WIKI_DIR, "PRAYER_CN.md"),
    "SHARED_INFRA": os.path.join(WIKI_DIR, "SHARED_INFRA.md"),
}

CRED_PATH = "/root/.hermes/credentials/youtube_token.json"


def utcnow():
    return datetime.now(timezone.utc)


def get_youtube():
    if not HAS_YT:
        return None
    with open(CRED_PATH) as f:
        td = json.load(f)
    creds = Credentials(
        token=td["token"], refresh_token=td["refresh_token"], token_uri=td["token_uri"],
        client_id=td["client_id"], client_secret=td["client_secret"], scopes=td["scopes"],
    )
    if not creds.valid:
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def fetch_playlist_videos(youtube, pid):
    items = []
    next_page = None
    while True:
        kwargs = dict(part="snippet", playlistId=pid, maxResults=50)
        if next_page:
            kwargs["pageToken"] = next_page
        resp = youtube.playlistItems().list(**kwargs).execute()
        items.extend(resp.get("items", []))
        next_page = resp.get("nextPageToken")
        if not next_page:
            break
    return items


def extract_yt_ids(items):
    ids = []
    titles = []
    for it in items:
        vid = it["snippet"]["resourceId"]["videoId"]
        title = it["snippet"].get("title", "")
        published = it["snippet"].get("publishedAt", "")
        day = None
        m = re.search(r'Day\s+(\d+)', title, re.I)
        if not m:
            m = re.search(r'第\s*(\d+)\s*天', title)
        if m:
            day = int(m.group(1))
        ids.append({"id": vid, "title": title, "day": day, "published": published})
    return ids


def scan_local_state(project, lang=""):
    root = Path(PROJECT_ROOTS[project])
    rows = []
    if project == "BD":
        # BD tracks state in dashboard.json — now with yt_video_id support
        dashboard = root / "data" / "dashboard.json"
        if not dashboard.exists():
            return []
        try:
            data = json.loads(dashboard.read_text())
        except Exception:
            return []
        pipe = data.get("pipelines", {}).get(lang, {})
        days = pipe.get("days", {})
        for day_str, info in days.items():
            if not day_str.isdigit():
                continue
            day = int(day_str)
            stages = info.get("stages", {})
            uploaded = info.get("status") == "uploaded" or stages.get("uploading") == "completed"
            yt_id = info.get("yt_video_id", "")
            yt_url = info.get("yt_url", "")
            rows.append({
                "day": day,
                "path": str(dashboard),
                "status": info.get("status", ""),
                "yt_id": yt_id,
                "yt_url": yt_url,
                "has_script": True,
                "updated": info.get("updated_at", ""),
            })
        return sorted(rows, key=lambda x: x["day"])

    # BM / PRAYER: use day state files
    patterns = ["data/day_*_state.json"]
    seen = set()
    for patt in patterns:
        for p in root.glob(patt):
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            # Skip Prayer split language files
            if project == "PRAYER" and (p.suffix == ".en.json" or p.suffix == ".cn.json"):
                continue
            m = re.search(r'day_(\d+)_state\.json', p.name)
            day = int(m.group(1)) if m else None
            if not day:
                continue
            try:
                data = json.loads(p.read_text())
            except Exception:
                continue

            claimed_id = ""
            if project == "BM":
                claimed_id = (data.get("upload", {}).get("yt_video_id") or "") if lang == "EN" else (data.get("upload_cn", {}).get("yt_video_id") or "")
            elif project == "PRAYER":
                claimed_id = (data.get("upload", {}).get("yt_video_id") or "") if lang == "EN" else (data.get("upload_cn", {}).get("yt_video_id") or "")

            script = data.get("script", {})
            rows.append({
                "day": day,
                "path": str(p),
                "status": data.get("approval_status", ""),
                "yt_id": claimed_id,
                "yt_url": "",
                "has_script": bool(script),
                "updated": data.get("updated_at", ""),
            })
    return sorted(rows, key=lambda x: x["day"])


def parse_day_from_title(title):
    m = re.search(r'Day\s+(\d+)', title, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r'第\s*(\d+)\s*天', title)
    if m:
        return int(m.group(1))
    return None


def analyze_section(project, lang, yt_videos, local_rows):
    yt_ids = {v["id"] for v in yt_videos}
    yt_by_day = {}
    for v in yt_videos:
        if v["day"]:
            yt_by_day.setdefault(v["day"], []).append(v["id"])
    local_by_day = {r["day"]: r for r in local_rows}
    local_days = sorted({r["day"] for r in local_rows})
    highest_local = local_days[-1] if local_days else 0
    missing_days = [d for d in range(1, highest_local + 1) if d not in local_by_day] if highest_local else []

    phantom = []
    uploaded_local = 0
    for r in local_rows:
        claimed = r.get("yt_id") or ""
        if not claimed:
            continue
        if claimed in yt_ids:
            uploaded_local += 1
        else:
            phantom.append({"day": r["day"], "yt_id": claimed, "path": r["path"]})

    status = "✅ Aligned" if len(local_rows) == len(yt_videos) and not missing_days and not phantom else "⚠️ Drift"
    return {
        "project": project,
        "lang": lang,
        "local_state_count": len(local_rows),
        "local_days": local_days,
        "highest_local_day": highest_local,
        "yt_count": len(yt_videos),
        "yt_uploaded_count": len(yt_ids),
        "local_uploaded_count": uploaded_local,
        "missing_state_days": missing_days,
        "phantom_uploads": phantom,
        "status_override": status,
    }


def build_wiki_section(sec, analysis):
    project, lang = sec.split("_", 1)
    local = analysis["highest_local_day"]
    yt = analysis["yt_count"]
    gap = analysis["missing_state_days"]
    phantom = analysis["phantom_uploads"]
    status = analysis.get("status_override") or ("✅ Aligned" if not gap and not phantom else "⚠️ Drift")
    now = utcnow().astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")

    block = (
        f"\n---\n\n## Reality Check\n\n"
        f"- **Checked:** {now}\n"
        f"- **Status:** {status}\n"
        f"- Local state files: {analysis['local_state_count']}\n"
        f"- YouTube playlist videos: {yt}\n"
        f"- Highest local day: {local}\n"
        f"- Missing state days: {len(gap)}\n"
        f"- Phantom uploads: {len(phantom)}\n\n"
    )
    if gap:
        block += f"### Missing State Days\n\n" + "\n".join(f"- Day {d}" for d in gap[:20]) + "\n\n"
    if phantom:
        block += f"### Phantom Uploads\n\n"
        for p in phantom[:20]:
            block += f"- Day {p['day']}: `{p['yt_id']}` from `{p['path']}`\n"
        block += "\n"
    return block


# ── Health checks ──────────────────────────────────────────────────

def check_pipeline_errors(log_path: str, pipeline_name: str, max_age_hours: int = 48) -> list:
    """Scan the last 50 lines of a pipeline log for ERROR/FAIL/Traceback lines.
    Only reports errors from the last max_age_hours (default 48h)."""
    import glob as _glob
    errors = []
    try:
        log_files = sorted(_glob.glob(log_path), key=os.path.getmtime, reverse=True)
        if not log_files:
            return []
        with open(log_files[0]) as f:
            lines = f.readlines()[-50:]
        cutoff_utc = utcnow() - timedelta(hours=max_age_hours)
        for line in lines:
            lower = line.lower()
            if not any(kw in lower for kw in ('traceback', 'error', 'fail', 'modulenotfound', 'importerror')):
                continue
            # Skip transient network timeouts — these are retried and usually recover
            # (e.g. "Playlist insert attempt 1 (non-HTTP): TimeoutError" then retry OK).
            if 'timeouterror' in lower:
                continue
            # Parse timestamp: 2026-07-21 02:31:36,798 — logs are written in MYT (UTC+8)
            try:
                ts_str = line[:23]  # '2026-07-21 02:31:36,798'
                line_myt = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S,%f').replace(tzinfo=timezone(timedelta(hours=8)))
                line_utc = line_myt.astimezone(timezone.utc)
                if line_utc < cutoff_utc:
                    continue  # Too old — skip
            except (ValueError, IndexError):
                pass  # Can't parse timestamp, include anyway
            # Skip IG token noise (old entries with expired tokens)
            if 'access_token=IG' in line:
                continue
            # Skip expected "file not found" errors (days not yet produced)
            if re.search(r'ERROR:.*(?:not found|No such file)', line):
                continue
            # Skip script self-reported exit status (e.g. "bd_caption.py FAILED")
            if re.search(r'---.*(?:FAILED|finished)', line):
                continue
            # Skip IG errors (now handled by Composio; stale log entries)
            if 'ERROR IG:' in line or ('instagram' in lower and '400' in lower):
                continue
            # Skip "Done — FB=ok IG=FAIL" status lines (old digest runs)
            if 'Done —' in line and 'IG=FAIL' in line:
                continue
            errors.append(f"{pipeline_name}: {line.strip()[-200:]}")
    except Exception as e:
        errors.append(f"{pipeline_name}: cannot read log — {e}")
    return errors


def check_python_modules(python_bin: str, modules: list, label: str) -> list:
    """Verify that required Python modules are importable."""
    errors = []
    for mod in modules:
        try:
            result = subprocess.run(
                [python_bin, '-c', f'import {mod}'],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                errors.append(f"{label}: `{python_bin}` missing module `{mod}` — {result.stderr.strip()[:150]}")
        except Exception as e:
            errors.append(f"{label}: cannot check {mod} — {e}")
    return errors


def check_cron_script_python(path: str, label: str) -> list:
    """Verify that a cron shell script calls python3.12, not python3."""
    errors = []
    if not os.path.exists(path):
        errors.append(f"{label}: cron script MISSING at {path}")
        return errors
    with open(path) as f:
        content = f.read()
    # Check for bare 'python3 ' (not python3.12)
    import re as _re
    bare_python3 = _re.findall(r'(?<!\.)\bpython3\s(?![\d.])', content)
    if bare_python3:
        errors.append(f"{label}: uses bare `python3` (should be `python3.12`) at {path}")
    return errors


def run_health_checks() -> list:
    """Run all health checks. Returns list of error strings."""
    all_errors = []

    # 1. Pipeline log errors
    all_errors.extend(check_pipeline_errors(
        '/root/projects/prayer/logs/pipeline_cn.log', 'PRAYER_CN'))
    all_errors.extend(check_pipeline_errors(
        '/root/projects/prayer/logs/pipeline.log', 'PRAYER_EN'))
    all_errors.extend(check_pipeline_errors(
        '/root/projects/bible_devotionals/logs/*.log', 'BD'))
    all_errors.extend(check_pipeline_errors(
        '/root/projects/motivational-biblical/logs/*.log', 'BM'))

    # 2. Python module health
    all_errors.extend(check_python_modules(
        'python3.12', ['whisper'], 'BD captioning'))
    all_errors.extend(check_python_modules(
        'python3.12', ['edge_tts', 'faster_whisper'], 'CN modules'))
    all_errors.extend(check_python_modules(
        'python3.12', ['googleapiclient', 'requests'], 'YT upload modules'))

    # 3. Cron script python version
    all_errors.extend(check_cron_script_python(
        '/root/.hermes/scripts/prayer_daily_cn.sh', 'Prayer CN cron'))
    all_errors.extend(check_cron_script_python(
        '/root/.hermes/scripts/run_mb_cn.sh', 'BM CN cron'))
    all_errors.extend(check_cron_script_python(
        '/root/.hermes/scripts/bf_unified.sh', 'Unified backfill cron'))
    all_errors.extend(check_cron_script_python(
        '/root/.hermes/scripts/run_daily_bible.sh', 'BD daily cron'))

    return all_errors


# ── Self-patching ───────────────────────────────────────────────────

CRON_SCRIPTS = {
    # label: (shell_path, python_path, workdir)
    'Prayer CN cron': ('/root/.hermes/scripts/prayer_daily_cn.sh',
                        '/root/projects/prayer/run_daily_cn.py',
                        '/root/projects/prayer'),
    'BM CN cron': ('/root/.hermes/scripts/run_mb_cn.sh',
                    '/root/projects/motivational-biblical/run_daily_cn.py',
                    '/root/projects/motivational-biblical'),
    'Looper cron': ('/root/projects/pipeline_wiki/scripts/pipeline_wiki_looper_force.sh',
                     '/root/projects/pipeline_wiki/scripts/pipeline_wiki_looper.py',
                     '/root/projects/pipeline_wiki/scripts'),
    'Unified backfill cron': ('/root/.hermes/scripts/bf_unified.sh',
                               '/root/projects/pipeline_wiki/scripts/bf_gap_runner.py',
                               '/root/projects/pipeline_wiki/scripts'),
    'BD daily cron': ('/root/.hermes/scripts/run_daily_bible.sh',
                       '/root/projects/bible_devotionals/modules/bd_gathering.py',
                       '/root/projects/bible_devotionals'),
}

def _replace_in_file(path, old, new):
    """Replace a string in a file. Returns True if changed."""
    if not os.path.exists(path):
        return False
    content = open(path).read()
    if old not in content:
        return False
    open(path, 'w').write(content.replace(old, new))
    return True


def auto_fix_python3_scripts() -> list:
    """Find ALL cron/pipeline .sh scripts using bare 'python3' and auto-patch to 'python3.12'.
    Also ensures PATH fix so system python3 (3.12) wins over venv python3."""
    import re as _re
    fixed = []
    
    # 1. Scan registered cron scripts
    for label, (sh_path, py_path, wd) in CRON_SCRIPTS.items():
        if not os.path.exists(sh_path):
            continue
        content = open(sh_path).read()
        bare = _re.findall(r'(?<!\.)\bpython3\b(?!\.\d)', content)
        if bare:
            new_content = _re.sub(r'(?<!\.)\bpython3\b(?!\.\d)', 'python3.12', content)
            open(sh_path, 'w').write(new_content)
            fixed.append(f'🩹 {label}: patched {len(bare)} bare `python3` → `python3.12`')

    # 2. Scan ALL .sh files under /root/.hermes/scripts/ (safety net)
    scripts_dir = '/root/.hermes/scripts'
    if os.path.isdir(scripts_dir):
        for root, dirs, files in os.walk(scripts_dir):
            for fname in files:
                if not fname.endswith('.sh'):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    content = open(fpath).read()
                    bare = _re.findall(r'(?<!\.)\bpython3\b(?!\.\d)', content)
                    if bare:
                        new_content = _re.sub(r'(?<!\.)\bpython3\b(?!\.\d)', 'python3.12', content)
                        open(fpath, 'w').write(new_content)
                        fixed.append(f'🩹 Extra script: patched {len(bare)} bare `python3` in {fpath}')
                except Exception:
                    pass

    return fixed


def auto_create_missing_wrappers() -> list:
    """Create missing .sh wrappers for existing .py scripts referenced by cron.
    Wrappers use python3.12 explicitly AND set PATH to prefer system python."""
    created = []
    for label, (sh_path, py_path, wd) in CRON_SCRIPTS.items():
        if os.path.exists(sh_path):
            continue
        if not os.path.exists(py_path):
            continue
        wrapper = f"""#!/bin/bash
set -euo pipefail
export PATH="/usr/bin:$PATH"  # system python3.12 over venv python3.11
cd {wd} || exit 1
python3.12 {os.path.basename(py_path)} 2>&1
exit $?
"""
        os.makedirs(os.path.dirname(sh_path), exist_ok=True)
        open(sh_path, 'w').write(wrapper)
        os.chmod(sh_path, 0o755)
        created.append(f'🩹 {label}: auto-created missing wrapper {sh_path}')
    return created


def auto_clean_gap_queue() -> list:
    """Remove zombie entries from upload gap queue (missing video files)."""
    cleaned = []
    qpath = '/root/projects/pipeline_wiki/state/upload_gap_queue.json'
    if not os.path.exists(qpath):
        return cleaned
    try:
        q = json.loads(open(qpath).read())
        gaps = q.get('gaps', [])
        changed = False
        for g in gaps:
            if g.get('done'):
                continue
            vid = os.path.join(g.get('asset_dir', ''), 'final.mp4')
            if not os.path.exists(vid) or os.path.getsize(vid) < 100_000:
                g['done'] = True
                g['done_at'] = utcnow().isoformat().replace('+00:00', 'Z')
                g['removed_reason'] = 'auto-cleaned: video file missing (zombie)'
                cleaned.append(f'Day {g["day"]} {g["lang"]}')
                changed = True
        if changed:
            json.dump(q, open(qpath, 'w'), indent=2)
            cleaned_msg = f'🩹 Gap queue: auto-cleaned {len(cleaned)} zombie entries ({", ".join(cleaned)})'
            return [cleaned_msg]
    except Exception:
        pass
    return cleaned


def self_patch() -> list:
    """Auto-patch known failure patterns. Returns list of actions taken."""
    patches = []

    # 1. Fix bare python3 → python3.12 in cron scripts
    patches.extend(auto_fix_python3_scripts())

    # 2. Create missing .sh wrappers
    patches.extend(auto_create_missing_wrappers())

    # 3. Clean zombie gap queue entries
    patches.extend(auto_clean_gap_queue())

    return patches


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--section")
    parser.add_argument("--health-only", action="store_true", help="Run health checks only")
    args = parser.parse_args()

    # Health checks run ALWAYS (before YT fetch, which can fail)
    health_errors = run_health_checks()
    if health_errors:
        print("🏥 HEALTH ALERTS:")
        for e in health_errors:
            print(f"  ❌ {e}")
        print()

    # Self-patching: auto-fix known failure patterns
    patches = self_patch()
    if patches:
        print("🩹 SELF-PATCHES APPLIED:")
        for p in patches:
            print(f"  {p}")
        print()

    if args.health_only:
        if not health_errors:
            print("✅ All health checks passed.")
        return
    os.makedirs(STATE_DIR, exist_ok=True)
    now = utcnow()
    youtube = get_youtube() if HAS_YT else None
    sections = [args.section] if args.section else list(PLAYLISTS.keys())
    analyses = {}

    # Pre-fetch only requested sections
    yt_cache = {}
    if youtube:
        for sec in sections:
            pid = PLAYLISTS[sec]
            try:
                items = fetch_playlist_videos(youtube, pid)
                yt_cache[sec] = extract_yt_ids(items)
            except Exception as e:
                yt_cache[sec] = {"error": str(e)}

    # Update wiki summaries
    stale_sections = []
    for sec in sections:
        project, lang = sec.split("_", 1)
        local_rows = scan_local_state(project, lang)
        yt_videos = yt_cache.get(sec, [])
        if isinstance(yt_videos, dict) and "error" in yt_videos:
            analyses[sec] = {"error": yt_videos["error"]}
            continue
        analyses[sec] = analyze_section(project, lang, yt_videos, local_rows)
        block = build_wiki_section(sec, analyses[sec])
        path = SECTION_FILES.get(sec)
        if path:
            existing = ""
            if os.path.exists(path):
                existing = open(path).read()
            # strip old reality block if rerunning in same session
            existing = re.sub(r"\n---\s*\n## Reality Check.*", "", existing, flags=re.S)
            with open(path, "w") as f:
                f.write(existing.rstrip() + "\n" + block)

    # Update next_days.json
    next_days = {}
    for sec, data in analyses.items():
        if "error" in data:
            continue
        expected = 1
        for d in data["local_days"]:
            if d == expected:
                expected += 1
            elif d > expected:
                break
        next_days[sec] = {
            "next_day": expected,
            "status": "queued",
            "checked_at": now.isoformat().replace("+00:00", "Z"),
            "yt_count": data["yt_count"],
            "local_state_count": data["local_state_count"],
        }
    with open(os.path.join(STATE_DIR, "next_days.json"), "w") as f:
        json.dump(next_days, f, indent=2)

    # links.json
    links = {}
    for sec, data in analyses.items():
        if "error" in data or not data["local_days"]:
            continue
        links[sec] = {
            "highest_day": data["highest_local_day"],
            "status": "drift" if data["missing_state_days"] or data["phantom_uploads"] else "ok",
            "updated_at": now.isoformat().replace("+00:00", "Z"),
        }
    with open(os.path.join(STATE_DIR, "links.json"), "w") as f:
        json.dump(links, f, indent=2)

    # ── Human-readable summary (for Telegram delivery) ──────────────────
    print("\n" + "="*50)
    myt = now.astimezone(timezone(timedelta(hours=8)))
    print(f"📊 Pipeline Health — {myt.strftime('%Y-%m-%d %H:%M')} MYT")
    print("="*50)
    ok_count = 0
    for sec, lk in links.items():
        nd = next_days.get(sec, {})
        yt = nd.get('yt_count', '?')
        local = nd.get('local_state_count', '?')
        status = lk.get('status', 'unknown')
        if status == 'ok':
            icon = '✅'; ok_count += 1
        else:
            icon = '⚠️'
        diff = (yt - local) if isinstance(yt, int) and isinstance(local, int) else ''
        diff_str = f' ({diff:+d})' if diff else ''
        print(f"{icon} {sec}: Day {nd.get('next_day','?')} | YT={yt} local={local}{diff_str}")
    drift_count = len(links) - ok_count
    print(f"\n{'✅' if drift_count == 0 else '⚠️'} {ok_count}/{len(links)} aligned")
    if drift_count:
        print("Drift: " + ", ".join(sec for sec, lk in links.items() if lk['status'] != 'ok'))
    print("="*50 + "\n")

    # ── Machine-readable JSON ──────────────────────────────────────────
    report = {
        "checked_at": now.isoformat().replace("+00:00", "Z"),
        "sections": list(analyses.keys()),
        "next_days": next_days,
        "links": links,
    }
    print(json.dumps(report, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
