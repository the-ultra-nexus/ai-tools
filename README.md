# ai-tools

个人 AI 工具集：skill、脚本、规范文档的单一来源。本仓库是权威版本，改完跑 `./sync.sh` 同步到 magpie library；magpie 把 library 里的 skill 软链进各 agent（`~/.claude/skills`、`~/.codex/skills`、`~/.config/deveco/skills`），所以同步完立即生效，不需要重装。

## 目录

| 路径 | 内容 |
|---|---|
| `skills/flashcard/SKILL.md` | 闪卡 skill：编排层 + 制卡规范（流程、格式模板、泄底判定、自检） |
| `skills/flashcard/scripts/check-cards.py` | 卡片格式校验器，复刻 obsidian-spaced-repetition parser，纯标准库 |
| `skills/flashcard/scripts/tts-flashcard.sh` | 发音生成（edge-tts 微软 Christopher 美音，失败降级 `say`；输出目录由调用方传入） |
| `skills/deepseek-web-search/SKILL.md` | DeepSeek 搜索 skill：参数、查询操作符、结果解读、限流与计费 |
| `skills/deepseek-web-search/scripts/search.py` | `/v1/tools/search` 客户端，纯标准库，凭证读 `DEEPSEEK_API_KEY` |
| `skills/ao-flow/SKILL.md` | 主脑编排的全自动多 agent 编码流 skill（v2 全链）：Workflow tool 起多模型并行设计+交叉验证 → 主脑合成拆 task units → AO daemon 管 pi worker 执行 → ocr delegate 评审（含对抗二审）→ findings 回传修复到收敛；含路由（大任务全链/小任务短链/纯咨询只设计）、pi 调用模板与踩坑速查 |
| `docs/tts-flashcard.md` | tts 脚本详情（实现、坑、实测记录） |
| `sync.sh` | 同步 `skills/*` 到 `~/.config/magpie/library/skills/` |
| `check-frontmatter.sh` | 校验 `skills/*/SKILL.md` 的 YAML frontmatter（name/description 存在且可解析） |

## 同步

```bash
./check-frontmatter.sh   # 可选：先校验 frontmatter
./sync.sh
```

用 `rsync -a --delete`：仓库里删掉的文件也会从 library 一并删除。

`check-frontmatter.sh` 防的是这类事故：`description` 未加引号且含 `冒号+空格`（如 `site:/lang:/after:`）时，YAML 会报
`Nested mappings are not allowed in compact mappings`，pi 加载 skill 时直接把整个文件丢弃（启动时显示 `[Skill conflicts]`）。
解决方法是给值加单引号：`description: '... site:/after: ...'`。
> 注：无 PyYAML 时该校验退化为只检查字段存在，装 `pyyaml` 后可真正解析。

## 外部依赖（不在本仓库）

- 卡片目录：由各 agent 的全局提示词提供（Claude 的 `~/.claude/CLAUDE.md` 里有 `#闪卡` 段），skill 内不写死路径
  - 该目录下另有两份数据侧规范：`记忆卡片方法论.md`（理论层）、`SR插件制卡最佳实践.md`（插件机制层）
- `python3`：校验器，无第三方包
- `uv` + `edge-tts`（联网拉包）：生成 mp3；macOS 自带 `say` / `afconvert` 兜底；`sips` 压缩图片

## 新增 skill

1. 建 `skills/<name>/`，放 `SKILL.md`（frontmatter 带 `name`、`description`）
2. `./sync.sh`
3. magpie App → Library → 以文件夹导入 `skills/<name>`，选要应用的 agent
