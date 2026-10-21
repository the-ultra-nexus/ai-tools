#!/bin/bash
# 把本仓库 skills/ 下每个 skill 同步到 magpie library（各 agent 的软链随即生效）
# 并把 skill 内的 agents/ 同步到 Claude Code 的用户级 agents 目录
set -eu
REPO="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.config/magpie/library/skills"
for src in "$REPO"/skills/*/; do
  name="$(basename "$src")"
  rsync -a --delete "$src" "$DEST/$name/"
done

# Claude Code 递归扫描 ~/.claude/agents/，按 skill 名分目录避免与其他 agent 冲突
AGENTS_DEST="$HOME/.claude/agents"
for src in "$REPO"/skills/*/agents/; do
  [ -d "$src" ] || continue
  name="$(basename "$(dirname "$src")")"
  mkdir -p "$AGENTS_DEST/$name"
  rsync -a --delete "$src" "$AGENTS_DEST/$name/"
done
