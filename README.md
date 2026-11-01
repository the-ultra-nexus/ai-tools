# ai-tools

个人 AI 工具集：skill、脚本、规范文档的 Git 仓库。**运行时主副本在 CC Switch**（`~/.cc-switch/skills/`，软链到 `~/.claude/skills/` 与 `~/.pi/agent/skills/`）；本仓库保存 Git 版本和未安装的 skill（如 `paseo-flow`）。改完跑 `./sync.sh` 从主副本反向备份，再提交。

## 目录

| 路径 | 内容 |
|---|---|
| `skills/flashcard/SKILL.md` | 闪卡 skill：编排层 + 制卡规范（流程、格式模板、泄底判定、自检） |
| `skills/flashcard/scripts/check-cards.py` | 卡片格式校验器，复刻 obsidian-spaced-repetition parser，纯标准库 |
| `skills/flashcard/scripts/tts-flashcard.sh` | 发音生成（edge-tts 微软 Christopher 美音，失败降级 `say`；输出目录由调用方传入） |
| `skills/deepseek-web-search/SKILL.md` | DeepSeek 搜索 skill：参数、查询操作符、结果解读、限流与计费 |
| `skills/deepseek-web-search/scripts/search.py` | `/v1/tools/search` 客户端，纯标准库，凭证读 `DEEPSEEK_API_KEY` |
| `skills/paseo-flow/SKILL.md` | 主脑编排的全自动多 agent 编码流 skill：主脑设计 → 两个原生 subagent（不同模型）并行调研 → 拆 task units → 规格红队审 unit → Paseo daemon 管 pi worker（worktree 隔离）执行 → 冷评审 subagent 只出 verdict+findings → 有界修复到收敛；含降档路由、agent 定义、paseo 调用模板与踩坑速查 |
| `skills/paseo-flow/agents/*.md` | 五个 Claude 原生 subagent 定义：调研 A/B 路、评审 A/B 路、规格红队（异构模型，`omitClaudeMd`，评审/红队只读） |
| `docs/tts-flashcard.md` | tts 脚本详情（实现、坑、实测记录） |
| `sync.sh` | 从 `~/.cc-switch/skills/` 反向备份已安装 skill 到 `skills/*`，并把 `skills/*/agents/` 同步到 `~/.claude/agents/<skill>/` |
| `check-frontmatter.sh` | 校验 `skills/*/SKILL.md` 与 `skills/*/agents/*.md` 的 YAML frontmatter（name/description 存在且可解析） |

## 同步

```bash
./check-frontmatter.sh   # 可选：先校验 frontmatter
./sync.sh
```

`sync.sh` 只处理本仓库已有的 skill：CC Switch 有同名目录时，用 `rsync -a --delete` 反向覆盖本仓库；没有的（如 `paseo-flow`）跳过并打印提示。传参数可备份新 skill：`./sync.sh <name>` 会自动建目录。

`skills/*/agents/` 会同步到 `~/.claude/agents/<skill>/`；已有目录热加载，新建目录后需重启一次 Claude Code。

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

1. 在 CC Switch 里导入或启用 skill，主副本落到 `~/.cc-switch/skills/<name>/`
2. 确认软链已出现在 `~/.claude/skills/` 或 `~/.pi/agent/skills/`
3. `./sync.sh <name>` 把它备份进本仓库，然后提交
