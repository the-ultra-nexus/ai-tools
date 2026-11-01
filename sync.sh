#!/bin/bash
# 从 CC Switch 主副本反向备份 skill 到本仓库
# 再把仓库里的 agents/ 同步到 Claude Code 的用户级 agents 目录
set -eu
REPO="$(cd "$(dirname "$0")" && pwd)"
SRC="$HOME/.cc-switch/skills"

if [ "$#" -gt 0 ]; then
  targets=("$@")
else
  targets=()
  for dst in "$REPO"/skills/*/; do
    targets+=("$(basename "$dst")")
  done
fi

for name in "${targets[@]}"; do
  if [ ! -d "$SRC/$name" ]; then
    echo "skip $name: not installed in $SRC"
    continue
  fi
  mkdir -p "$REPO/skills/$name"
  rsync -a --no-perms --delete --exclude=.DS_Store "$SRC/$name/" "$REPO/skills/$name/"
done

# Claude Code 递归扫描 ~/.claude/agents/，按 skill 名分目录避免与其他 agent 冲突
AGENTS_DEST="$HOME/.claude/agents"
for src in "$REPO"/skills/*/agents/; do
  [ -d "$src" ] || continue
  name="$(basename "$(dirname "$src")")"
  mkdir -p "$AGENTS_DEST/$name"
  rsync -a --delete --exclude=.DS_Store "$src" "$AGENTS_DEST/$name/"
done
