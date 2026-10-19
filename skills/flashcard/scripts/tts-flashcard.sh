#!/bin/bash
# 闪卡发音生成器 — 微软 Christopher 美音 (en-US-ChristopherNeural)
# 用法: tts-flashcard.sh <英文短语> <文件名(不带扩展)> <输出目录>
# 如:   tts-flashcard.sh "artificial" "artificial" "/path/to/T-附件/audio"
# 输出: <输出目录>/<文件名>.mp3；失败降级 say -v Samantha + afconvert -> .m4a
set -u

PHRASE="$1"
NAME="$2"
OUT_DIR="${3:?用法: tts-flashcard.sh <英文短语> <文件名> <输出目录>}"

mkdir -p "$OUT_DIR"

# edge-tts 走 uv 隔离运行：不 pip install(系统 Python 版本低/权限受限)，
# uv run --with 每次拉最新版(旧版 token 过期返 403)
uv run --quiet --with edge-tts edge-tts \
  --voice en-US-ChristopherNeural \
  --text "$PHRASE" \
  --write-media "$OUT_DIR/$NAME.mp3" 2>/dev/null

if [ ! -f "$OUT_DIR/$NAME.mp3" ]; then
  # 降级：系统 Samantha 音 + afconvert 转 m4a
  TMP="/tmp/$NAME.aiff"
  say -v Samantha -o "$TMP" "$PHRASE" && \
    afconvert -f m4af -d aac "$TMP" "$OUT_DIR/$NAME.m4a" && \
    mv "$TMP" "$HOME/.Trash/" 2>/dev/null
  echo "$NAME.m4a (降级 Samantha)"
else
  echo "$NAME.mp3 OK"
fi
