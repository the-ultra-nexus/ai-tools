# ai-tools

个人 AI 工具集：skill、脚本、规范文档的单一来源。本仓库是权威版本，改完跑 `./sync.sh` 同步到 magpie library；magpie 把 library 里的 skill 软链进各 agent（`~/.claude/skills`、`~/.codex/skills`、`~/.config/deveco/skills`），所以同步完立即生效，不需要重装。

## 目录

| 路径 | 内容 |
|---|---|
| `skills/flashcard/SKILL.md` | 闪卡 skill 入口（各 agent 加载的编排层） |
| `skills/flashcard/AGENTS.md` | 制卡规范总入口（流程、格式模板、泄底判定、自检） |
| `skills/flashcard/scripts/check-cards.py` | 卡片格式校验器，复刻 obsidian-spaced-repetition parser，纯标准库 |
| `skills/flashcard/scripts/tts-flashcard.sh` | 发音生成（edge-tts 微软 Christopher 美音，失败降级 `say`） |
| `docs/tts-flashcard.md` | tts 脚本详情（实现、坑、实测记录） |
| `sync.sh` | 同步 `skills/*` 到 `~/.config/magpie/library/skills/` |

## 同步

```bash
./sync.sh
```

用 `rsync -a --delete`：仓库里删掉的文件也会从 library 一并删除。

## 外部依赖（不在本仓库）

- Obsidian vault：`~/obsidian-notes/work-notes/A-闪卡/`（卡片落点）
  - 另外两份规范留在 vault：`记忆卡片方法论.md`（理论层）、`SR插件制卡最佳实践.md`（插件机制层）
- `python3`：校验器，无第三方包
- `uv` + `edge-tts`（联网拉包）：生成 mp3；macOS 自带 `say` / `afconvert` 兜底；`sips` 压缩图片

## 新增 skill

1. 建 `skills/<name>/`，放 `SKILL.md`（frontmatter 带 `name`、`description`）
2. `./sync.sh`
3. magpie App → Library → 以文件夹导入 `skills/<name>`，选要应用的 agent
