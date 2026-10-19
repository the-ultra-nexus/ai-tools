---
name: flashcard
description: 给 Obsidian 闪卡（A-闪卡 目录）制卡、改卡、校验。用户要"做闪卡/制卡/加卡片/改卡/查卡片格式/生成发音/给单词做卡"时用。覆盖英语词汇、数学定义、编程概念等任何学科，含发音卡、搜图压缩、parser 校验。
argument-hint: "[源笔记路径 | 单词/主题 | 校验 <文件>]"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, WebSearch, WebFetch, AskUserQuestion
---

# 闪卡制卡

**唯一规范入口**：`~/.config/magpie/library/skills/flashcard/AGENTS.md`

**第一步永远是这个**——先完整读它，再动手：

```
Read ~/.config/magpie/library/skills/flashcard/AGENTS.md
```

本文件只讲**怎么执行**（编排、命令、校验）。格式细节、泄底判定、卡型选择**一律以 AGENTS.md 为准**，不要凭本文件的印象写卡。需要深入时再读 `~/obsidian-notes/work-notes/A-闪卡/记忆卡片方法论.md`（理论层）和同目录的 `SR插件制卡最佳实践.md`（插件机制层）。

## 参数分派

| 参数形态 | 动作 |
|---|---|
| 无参数 | 问用户「制什么卡」，或从当前会话上下文推断 |
| 源笔记路径 / 主题 | 走下方「制卡流程」 |
| `校验 <文件>` | 只跑「校验」一节，不改文件 |
| 一个单词/短语 | 按发音卡 + 4 维度制卡（见 AGENTS.md） |

## 制卡流程

### 1. 定源与选材

- **必须挂出处**：读源笔记确认知识点来源，卡背面挂 wikilink。拿不到出处就问用户，别编。出处只挂来源本身，不加词典名（如 OALD）。
- **选材判据**（AGENTS.md「选材」）：只做「见过但不会用」的；完全陌生先理解、完全掌握不做。
- 单点 ≤ 6 张。

### 2. 落文件

目标目录固定：`~/obsidian-notes/work-notes/A-闪卡/`

- 已存在 `<主题>.md` → 追加卡片（**别重建文件**，会丢已有进度）
- 不存在 → 新建，frontmatter 带 `tags:` 和 `source:`

### 3. 写卡

严格抄 AGENTS.md 的「格式模板」。最容易踩的三条（都会**静默失败**，不报错）：

1. 正面用**正文行**，不是 `###` 标题
2. 正面正文行**下一行直接**写 `?`，中间**不能有空行**
3. `#flashcards/<学科>/<子主题>` **独立成行、前后留空行**

### 4. 英语卡：发音 + 图片

```bash
# 发音（微软 Christopher 美音，失败自动降级 say）
~/.config/magpie/library/skills/flashcard/scripts/tts-flashcard.sh "<英文短语>" "<文件名>"
# 输出 T-附件/audio/<文件名>.mp3

# 图片：先落 /tmp，压缩后再进库
sips -Z 1200 "/tmp/<下载的图>" --out "$HOME/obsidian-notes/work-notes/T-附件/images/<word>.jpg"
```

- 图片联网搜免费图（优先 Unsplash），选与词义相关的
- **硬要求**：最长边 1200px、单张 ≤500KB、统一 `.jpg`；超了降 `-Z 900`
- 一个词一张**独立发音卡**（正面图片 → 背面 IPA + 发音链接 + 音频），别把发音塞进 Cloze 卡

#### 发音链接（背面每个英文词/词组都挂）

```markdown
[artificial](https://youglish.com/pronounce/artificial/english)
[artificial intelligence](https://youglish.com/pronounce/artificial%20intelligence/english)
```

- 单词 `.../pronounce/<word>/english`；词组空格换 `%20`
- 链接文字 = 词本身（不要 `[youglish]` 这类泛称）
- **不用中文谐音**（会固化错误口型）；youglish 给真语料，可核对可矫正
- **不加** `🔊` 图标、独立 `发音参考：` 行（音频嵌入自带播放按钮；链接已贴词上）
- **Cloze 行的词不挂链接**（Cloze 两面共享文本，挂了正面报答案）
- 不挂：拼写片段（`-gence`）、音频文件名、出处笔记名

### 5. 校验（必跑）

```bash
python3 ~/.config/magpie/library/skills/flashcard/scripts/check-cards.py \
  "$HOME/obsidian-notes/work-notes/A-闪卡/<文件>.md"
```

> magpie 默认把 skill **软链**进各 agent 的 skills 目录，所以 `~/.claude/skills/flashcard/scripts/check-cards.py` 同样可用（同一份文件）。改了链接方式（`magpie library skill how copy`）也成立，因为 `scripts/` 跟着一起走。

它按插件 `main.js` 的真实逻辑复刻 parser，检查：卡数、正反面切分、正面是否混入 heading、`#flashcards` 标签是否被吃进卡片正文、SR 注释数。

**任何一项不过 = 回去改卡**，别交付。改完再跑一次。

## 改卡

进度在 `<!--SR:-->` 注释里（`dataStore: NOTES`）。改正面会丢进度（逐行精确比对，不是 hash），**丢了无所谓**。

```bash
grep -c "SR:" 文件.md    # 改前改后各跑一次，一致=进度没丢
```

## 交付前自检

过 AGENTS.md 的「自检清单」（9 条）。另加两条本命令特有的：

- [ ] `check-cards.py` 全绿？
- [ ] 改了正面导致丢进度的话，跟用户说一声？
- [ ] 背面每个英文词/词组都挂了 youglish 链接？（中文释义、拼写片段、音频文件名不挂）

## 边界

- **只在用户要求时**往 `A-闪卡/` 写文件
- 别改 `AGENTS.md` / 方法论 / 最佳实践三份规范，除非用户明确要求
- `AGENTS.md` 与 `tts-flashcard.sh` 随 `~/projects/opensource/ai-tools` 仓库管理：改仓库里的 `skills/flashcard/`，提交后跑 `sync.sh` 同步到 magpie library
