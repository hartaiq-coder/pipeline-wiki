#!/usr/bin/env python3
"""
pipeline_wiki_api.py
Read-only accessor for /root/projects/pipeline_wiki/ state files.
Scripts should call this instead of hardcoding IDs / re-discovering state.
"""
import json, os, re
from pathlib import Path

WIKI_DIR = Path('/root/projects/pipeline_wiki')
STATE_DIR = WIKI_DIR / 'state'

SECTION_FILES = {
    'BD_EN': WIKI_DIR / 'BD_EN.md',
    'BD_CN': WIKI_DIR / 'BD_CN.md',
    'BM_EN': WIKI_DIR / 'BM_EN.md',
    'BM_CN': WIKI_DIR / 'BM_CN.md',
    'PRAYER_EN': WIKI_DIR / 'PRAYER_EN.md',
    'PRAYER_CN': WIKI_DIR / 'PRAYER_CN.md',
    'SHARED_INFRA': WIKI_DIR / 'SHARED_INFRA.md',
}

def get_channel_id():
    """Return YouTube channel ID from wiki (primary: Caddy Khaw)."""
    try:
        txt = (WIKI_DIR / 'MASTER.md').read_text()
        m = re.search(r'(UCPmKHR0GAcqv4ylvvKpeuJw)', txt)
        if m:
            return m.group(1)
    except Exception:
        pass
    return 'UCPmKHR0GAcqv4ylvvKpeuJw'

def _normalize_section(s):
    return re.sub(r'[^A-Z0-9]', '', s.upper())


def get_playlist(lang, section=None):
    """Return upload playlist ID for a language from wiki state."""
    lang_up = lang.upper()

    if section:
        sec_norm = _normalize_section(section)
        shared = WIKI_DIR / 'SHARED_INFRA.md'
        if shared.exists():
            txt = shared.read_text()
            for line in txt.splitlines():
                if not line.startswith('|'):
                    continue
                parts = [p.strip() for p in line.strip('|').split('|')]
                if len(parts) >= 3:
                    row_sec = _normalize_section(parts[0])
                    row_lang = parts[1].strip().upper()
                    # Match either exact normalized section or section prefix + language suffix
                    sec_match = row_sec == sec_norm or (sec_norm.startswith(row_sec) and sec_norm.endswith(lang_up))
                    if sec_match and row_lang == lang_up:
                        candidate = parts[2]
                        if re.match(r'^PL[A-Za-z0-9_-]+$', candidate):
                            return candidate

    # Primary: SHARED_INFRA has the canonical mapping table
    shared = WIKI_DIR / 'SHARED_INFRA.md'
    if shared.exists():
        txt = shared.read_text()
        # Match rows like: | BD | EN | PL... |
        for line in txt.splitlines():
            if not line.startswith('|'):
                continue
            parts = [p.strip() for p in line.strip('|').split('|')]
            if len(parts) >= 3 and parts[1] == lang_up:
                candidate = parts[2]
                if re.match(r'^PL[A-Za-z0-9_-]+$', candidate):
                    return candidate

    # Secondary: section-specific overrides
    for section in ['BD_EN', 'BD_CN', 'BM_EN', 'BM_CN', 'PRAYER_EN', 'PRAYER_CN']:
        p = SECTION_FILES.get(section)
        if not p or not p.exists():
            continue
        if not section.endswith(lang_up):
            continue
        txt = p.read_text()
        # Look for actual playlist ID tokens in the text
        m = re.search(r'`?(PL[A-Za-z0-9_-]{10,})`?', txt)
        if m:
            return m.group(1)

    # fallback hardcoded
    defaults = {
        'EN': 'PLgsAd6HNQy7nuCC7d05oBM8x1Vt_iEGnF',
        'CN': 'PLgsAd6HNQy7lj_ur2Gcv2tHoj3tODVZ2Y',
    }
    return defaults.get(lang_up)
