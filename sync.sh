#!/bin/bash
# 把本仓库 skills/ 下每个 skill 同步到 magpie library（各 agent 的软链随即生效）
set -eu
REPO="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.config/magpie/library/skills"
for src in "$REPO"/skills/*/; do
  name="$(basename "$src")"
  rsync -a --delete "$src" "$DEST/$name/"
done
