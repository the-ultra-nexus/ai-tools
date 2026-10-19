# tts-flashcard.sh

闪卡发音生成器。给 Obsidian 闪卡生成真人感英文发音音频。

## 用途

按需手动运行，为闪卡单词/短语生成音频文件，挂到卡片背面。

脚本随 `~/projects/opensource/ai-tools` 仓库管理，本文件是它的详情文档；改完提交并跑 `sync.sh` 同步到 magpie library。

```bash
~/.config/magpie/library/skills/flashcard/scripts/tts-flashcard.sh "<英文短语>" "<文件名>" "<输出目录>"
# 如: ~/.config/magpie/library/skills/flashcard/scripts/tts-flashcard.sh "artificial" "artificial" "<卡片目录>/../T-附件/audio"
```

输出：`<输出目录>/<文件名>.mp3`（由调用方传入，脚本不写死路径）

降级输出：`<文件名>.m4a`（edge-tts 联网失败时自动切换）

在 Obsidian md 里引用：`![[<文件名>.mp3]]`（wikilink 按文件名跨库解析，无需写全路径）

## 实现

- 语音：`en-US-ChristopherNeural`（微软 Christopher 美音，男声）
- **走 `uv run --with edge-tts`，不 pip install**。两个原因：
  1. 系统 Python 3.9 装包到 site-packages 权限受限（Permission denied）
  2. 旧版 edge-tts 7.2.8 token 过期返 403；`uv run --with` 每次拉最新版，实测 7.3.1 可用
- 降级链：`edge-tts` 失败 → `say -v Samantha` + `afconvert -f m4af -d aac`（macOS 系统自带）
- 中间产物 `/tmp/<name>.aiff` 用完 `mv` 到 `~/.Trash/`（遵守全局规范不用 rm）

## 无 launchd 托管

非常驻脚本，按需手动运行。**改完不用重启服务。**

## 日志

不在脚本内写日志文件。结果靠 stdout 一行输出（`<文件名>.mp3 OK` / `.m4a (降级 Samantha)`）。
批量生成时由调用方自行重定向。

## 坑

1. **必须传三个参数**（短语、文件名、输出目录），`set -u` 下缺参数会直接报错退出（预期的，防止生成出空文件或落到错误目录）
2. **文件名不带扩展名**。若传入 `artificial.mp3`，会产出 `artificial.mp3.mp3`
3. **文件名建议用小写 + 下划线**（如 `artificial_general_intelligence`），和 Obsidian 内引用保持一致
4. **edge-tts 依赖网络**。首次 `uv run --with` 有拉包冷启动（数秒），之后仍是按需拉取
5. 首次运行 `uv` 需联网，离线环境会直接走 `say` 降级。降级音质明显差于 Christopher，仅作兜底
6. 中文文本不要丢给此脚本（Christopher 是英文语音，中文会读出英文逐字或静音失败）

## 实测记录

2026-10-14：
- `uv run --with edge-tts` → 11-28KB 有效 MP3（48kbps / 24kHz / Mono）✅
- Christopher 语音确认存在：`en-US-ChristopherNeural | en-US | Male` ✅
- 降级链未实测出声，但 `say` / `afconvert` 均系统自带
