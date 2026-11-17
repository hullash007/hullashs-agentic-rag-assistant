#!/bin/sh
# Operate a prebuilt local image only. No ports, volumes, secrets or network.
set -eu
[ "$#" -eq 1 ] || { echo 'usage: sh packaging/smoke_image.sh LOCAL_IMAGE_REFERENCE' >&2; exit 2; }
case "$1" in -*) echo 'invalid image reference' >&2; exit 2;; esac
exec docker run --pull=never --rm --network=none --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=32m --pids-limit=32 --memory=512m --cpus=1 \
  --cap-drop=ALL --security-opt=no-new-privileges \
  "$1" /opt/venvs/app/bin/python /app/packaging/container_smoke.py
