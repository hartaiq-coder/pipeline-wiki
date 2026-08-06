#!/bin/bash
set -euo pipefail
# Pipeline Wiki Looper — reality check + health checks daily
# Cron: 30 4 * * *
cd /root/projects/pipeline_wiki/scripts || exit 1
python3.12 pipeline_wiki_looper.py 2>&1
exit $?
