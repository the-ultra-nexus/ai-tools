---
name: paseo-flow
argument-hint: "<任务描述>"
description: '主脑编排的全自动多 agent 编码流：主脑出设计，缺外部事实时双路 subagent 并行调研交叉验证，主脑拆 task units、红队审规格，pi worker 在 worktree 隔离执行，A 路冷评审 + B 路定向复审与 High 证伪，主脑裁决，程序门禁判定完成，有界修复，状态落盘可续跑，人合并；拿不准降档走短链。触发词：交给 agent 做、并行做这几件事、把 X 改了并评审、只出方案不写代码。前置：paseo CLI+daemon、pi 已登录、ocr、claude CLI 已接 magpie 网关、本 skill 的 agents/ 已同步到 ~/.claude/agents/paseo-flow/。'
---

# paseo-flow：主脑编排的多 agent 全链编码流

驱动者是本会话（Claude 主脑）。用户一次指令，全程零参与、零反问；随时 Esc/打字打断。本 skill 是路由 + 协议：按任务规模选链，各阶段照章执行，产物落盘可审计。

## 角色分配

| 角色 | 模型 | 干什么 |
|---|---|---|
| 主脑 | 本会话 | 路由、设计、拆 unit、裁决 verdict、收敛决策 |
| 调研 subagent | `paseo-researcher-a` / `-b`（定义内写死 `group/reviewer1` / `reviewer2`） | 缺外部事实时两路并行调研、跑 `--help`、读源码、refute 结论 |
| 规格红队 | `paseo-plan-critic`（`group/reviewer2`） | 全链派发前审 unit 规格，不审代码 |
| 执行 worker | `paseo run --provider pi --model magpie/group/worker` | worktree 内实现、跑验收、修 findings |
| 评审 subagent | `paseo-reviewer-a` / `-b`（定义内写死 `group/reviewer1` / `reviewer2`） | A 路全量冷评审；B 路只做安全/数据丢失/并发/测试削弱维度复审，或对单条 High 证伪 |

pi 只跑 §3 的 worker（由 paseo daemon 拉起）；调研与评审走 Claude 原生 subagent，模型写在各 agent 定义的 `model:` 里。

agent 定义在 `skills/paseo-flow/agents/`，`./sync.sh` 会同步到 `~/.claude/agents/paseo-flow/`。五个定义都设了 `omitClaudeMd: true`；评审器是 `Read, Grep, Glob, Bash`，规格红队是 `Read, Grep, Glob`，调研器没有 `Edit` 和 `Agent`。

**无会话/脚本场景的后备**（cron、`claude -p` 里再套一层、或 agent 定义不可用时）：

```bash
git --no-pager diff --no-color <基线>..HEAD | claude -p --bare --tools 'Read,Grep,Glob' \
  --no-session-persistence --model 'group/reviewer1' '<prompt>'
```

- `--bare` 跳过 CLAUDE.md/hooks/MCP/插件：同一问实测 60s+ → 3~4s。原生 subagent 没有等价的 bare 开关，只能靠 `omitClaudeMd` 少加载 CLAUDE.md。
- stderr 会打一行 `[claude-code:unrecognized_model] {"model":"group/reviewer1",...}`——magpie 别名不在 CLI 的模型表里，属无害噪声。原生 subagent 也会打同一行。
- 别名能进 agent 定义且真的路由（`modelUsage.canonicalModel` 实测为 `group/reviewer1`）。但组织 `availableModels` 允许列表若拦下这个值，会静默换成别的模型；换网关后先核对一次实际模型。

## 0. 路由

| 信号 | 链路 |
|---|---|
| 单文件 / 验收命令明确 / 方案无争议 | **短链**：§3 执行 → §4 评审 → §5 收敛 |
| 多模块 / 方案未定 / 技术选型 / 重构级 | **全链**：§1 设计 → §2 拆分 → §3 → §4 → §5 |

**拿不准就降一档走短链**，在汇报里写一句「按短链走，理由 X」。

- 短链同样落一份最小 unit 到 `$TASK_DIR/units/0-<slug>.md`（目标 / 基线 / 文件清单 / 验收命令），否则 §4 的评审没有契约可对照；§1 §2 其余项可省。
- 短链出现 High、越界，或同一验收命令连续两次红 → 下一轮升全链。
- 同一任务里短链零 findings 且一次通过 → 本任务后续同规模继续走短链；**跨任务不累计**（会话间无状态，别假装记得）。

## 0.1 前置自检与任务建档

```bash
command -v paseo pi ocr claude jq >/dev/null || { echo 'CLI 缺件'; exit 1; }
diff -rq "$HOME/projects/opensource/ai-tools/skills/paseo-flow/agents" "$HOME/.claude/agents/paseo-flow" \
  || (cd "$HOME/projects/opensource/ai-tools" && ./sync.sh)   # agent 定义改动下个会话才生效
paseo status | grep -q 'localDaemon: running' || paseo daemon start --timeout 30
```

daemon 30s 起不来就停下写汇报，别带病开链。

任务一开始就钉死（task-id 用 `YYYYMMDD-<slug>`，分支名固定 `pf/<task-id>/<n>-<slug>`）：

```bash
TASK_ID="$(date +%Y%m%d)-<slug>"
TASK_DIR="$HOME/data/paseo-flow/$TASK_ID"     # 放仓库外，避免污染工作区
BASE_SHA=$(git -C <repo> rev-parse HEAD)      # 独立 unit 的统一基线
mkdir -p "$TASK_DIR"/{units,state,review}
printf '{"chain_start":%s}\n' "$(date +%s)" > "$TASK_DIR/state/chain.json"   # 整链 3h 起点落盘，断链后照此续算
```

后文所有落盘都用 `$TASK_DIR` 绝对路径。§4 会 cd 进 worktree，相对路径会把文件写进别人的分支。

## 0.2 续跑（以 state 文件为准，不信回忆）

会话被压缩或打断后，读 `$TASK_DIR/state/<unit>.json` 逐个恢复；整链预算起点在 `$TASK_DIR/state/chain.json`（`jq -r .chain_start`），断链后照它续算，不重置：

| stage | 恢复动作 |
|---|---|
| research / design / split | 重读 design.md、units/、research*.md，缺哪步补哪步 |
| run | `paseo inspect <id>` 还活着 → 继续 wait；查不到 → 按 unit 文件重派 |
| gate / review | `git -C <wt> rev-parse HEAD` 等于 state 的 `head` → 直接进 §4；不等（有未提交改动）→ 先让 worker 提交再进 §4 |
| repair | round 加一，按 §5 继续 |

id 为空或 agent 已不存在，一律按「重派」处理，重派前把该 unit 的 `round`/`repairs` 清零。

## 1. 设计阶段（主脑出方案，调研才外包）

**方案由主脑自己出**——初始信息、技术路线、取舍、接口形态全在本会话里成型，不外包设计：设计的价值就在全局上下文，交出去等于把它丢了。

只有「缺外部事实」时才起 subagent 调研：**一条消息里并行发两个 Agent 调用**，两路同题、各搜各的。

- `subagent_type: paseo-researcher-a`，prompt 写清：要哪些事实、什么格式、要几条来源、每条必须带链接，产出写到 `$TASK_DIR/research-a.md`。
- `subagent_type: paseo-researcher-b`，同一个问题，产出写到 `$TASK_DIR/research-b.md`。
- 两个定义模型不同、上下文独立，互不可见；主脑只读两份文件，不把全文吞进上下文。

约束：

- 逼 subagent 自己核实：跑 `--help`、读源码、点开 URL、多来源交叉；交回来的必须是「结论 + 出处」，没出处的事实一律记为未验证。
- 调研器没有 `Edit`/`Agent`，但有 `Write`——只许写 `$TASK_DIR/research-*.md`，别动仓库源码。
- 两路回来主脑抽查一次 `git -C <repo> status --porcelain`：出现计划外改动 → 该路结论整体降权，写进汇报（它有 Write，防的就是这个）。
- **不要让 pi 做调研或长输出**（实测超时返空）；pi 只归 §3 的 worker。
- 两路回来由主脑汇总：一致的钉成事实，分歧保留进 `research.md`——分歧本身就是决策信息，不强行统一。交叉验证也在主脑这层做：逐条问「出自哪、哪个版本、现在还成立吗」。

产出落盘：`$TASK_DIR/research-a.md`、`research-b.md`，汇总写 `$TASK_DIR/research.md`（含分歧点与未验证项）；设计本身写 `$TASK_DIR/design.md`（目标、取舍、接口形态、非目标），后面红队和 worker 都拿它当指针。

## 2. 拆分阶段（主脑独占，不外包）

合成结果拆成 **task units**，每个 unit 一个文件 `$TASK_DIR/units/<n>-<slug>.md`，必含：

- **目标**：一句话可验收的结果
- **基线**：起始 commit
- **契约**：导出签名、数据结构、错误语义；并行 unit 的接口以这里为准
- **文件清单**：只许动这些；§3 用 `git diff --name-only` 对照，越界即停
- **禁改**：已有测试、锁文件、CI 配置、迁移脚本一律不动；新增测试文件可以写。契约确需扩大范围时，必须在 unit 里显式列出
- **验收命令**：命令行可判定（`node test.js` / `npm test`），没有验收命令的 unit 不许派发
- **测试证据**：新增测试必须在实现前于基线代码上跑红一次（宿主复验见 §3）；worker 第一步回传红输出，主脑存到 `$TASK_DIR/units/<n>.red.txt`。没红过的测试不算证据
- **依赖边**：依赖哪个 unit；无依赖的并行派，有依赖的串行等
- **必读**：design.md、research.md、现有实现路径；只给指针，不复制全文
- **非目标**：明确不做什么，防止顺手重构

拆分原则：tracer-bullet（一条票一个端到端可验证的弹道），宁粗勿细——3 个大 unit 好过 9 个碎 unit。并行 worker ≤ 3，改同一文件的工作不并行。整链 unit 数 ≤6；总 review-fix 轮次 ≤2×unit 数；超限写 `ESCALATE` 停，不硬跑。

unit 全部写完后，全链在派发前跑一次规格红队（短链跳过）：

- `subagent_type: paseo-plan-critic`
- prompt 只给指针：`units_dir=$TASK_DIR/units`、`design=$TASK_DIR/design.md`、`repo=<绝对路径>`；主脑不复制全文。
- 输出 `verdict: pass | revise`，findings 每条带 `unit` 字段。
- High（验收命令测不出目标 / 契约矛盾 / 依赖成环 / 并行 unit 改同一文件）必须改完 unit 才能进 §3；Medium 记进汇报，不阻塞。
- 红队报的 High，主脑要么改 unit，要么在汇报里写不修的具体理由；不许静默放过。
- 红队只审规格，不审代码；它说 pass 也不代表实现是对的，§4 照跑。

## 3. 执行阶段（Paseo daemon + pi workers）

daemon 已在 §0.1 检查。每个 unit（在目标 repo 根目录下）：

unit 全文已在 `$TASK_DIR/units/<n>-<slug>.md`，派发读文件，不手打长 prompt（JSON、引号、反斜杠的 shell 转义不值得赌）：

```bash
cd <repo>
id=$(paseo run --quiet --provider pi --model magpie/group/worker \
  --new-workspace worktree --worktree-mode branch-off \
  --new-branch pf/<task-id>/<n>-<slug> --base <基线ref> \
  --title '<unit短名>' --no-wait "$(cat "$TASK_DIR/units/<n>-<slug>.md")")
```

- `--base` 一律显式给：有依赖边的 unit 用上游 unit 分支名（`--base pf/<task-id>/<上游n>-<slug>`），独立 unit 用 `BASE_SHA`。默认 branch-off 从 repo 当前 HEAD 开，主脑同会话动过 repo 就会跑偏。
- `paseo run` 的 prompt 就是初始任务，agent 立即开干（不像 ao 需要 send 推一把）。`--quiet` 的 stdout 只有 agent id，workspace 提示走 stderr，`id=$(...)` 安全。

跑完先查 id 非空，别拿空字符串去 inspect：

```bash
[ -n "$id" ] || { echo 'paseo run 没有返回 id'; exit 1; }
```

拿 worktree 路径与 workspace id（**别假设，先问 daemon**）：

```bash
WT=$(paseo inspect "$id" --json | jq -r '.Cwd')
WKS=$(paseo workspace ls --json | jq -r --arg wt "$WT" '.data[]|select(.cwd==$wt)|.workspaceId' | head -1)
```

立刻把状态落到 `$TASK_DIR/state/<unit>.json`：

```json
{"id","wks","wt","base","branch","head","stage","round","verdict","repairs","reviewer_a","started_at"}
```

- `head`＝该 unit 已提交的最新 sha（尚未提交时为 null）；`stage`＝run|gate|review|repair|done|frozen；`repairs`＝已用修复次数；`reviewer_a`＝A 路评审 subagent 的 agentId；`started_at`＝该 unit 开始的 epoch 秒。
- `WKS` 拿空不算错：agent 在跑时 workspace 一定在，清理前再查一次即可（§5 有反查兜底）。
- 每次 `wait`、`send`、评审回来、修复回来都更新对应字段。

等完成（单轮熔断 15min）：

```bash
paseo wait "$id" --timeout 900
```

超时不等于失败：先 `paseo send "$id" --no-wait --prompt '汇报当前进度与卡点'`，再决定继续等或 `paseo stop "$id"`。同一 unit 只允许问一次进度。

验收：在 `$WT` 里跑该 unit 的验收命令。

**新测试的 fail-to-pass 由宿主复验，不采信 worker 自述**：worker 回传红输出存 `$TASK_DIR/units/<n>.red.txt` 后，宿主把新增测试文件复制到基线跑一次——`git -C <repo> worktree add <临时目录> <基线ref>`，拷进去跑，红了才算证据；基线上跑不红 → 该测试不算证据，写进汇报。临时 worktree 用完 `git -C <repo> worktree remove <临时目录>`。

红了先分类，再决定回传：

- 实现错误 → 回传同一 agent 修（不用等评审）：把「验收失败的 stderr + 修复后重跑的验收命令」写进 `$TASK_DIR/units/<n>-fix.txt`，`paseo send "$id" --no-wait --prompt-file` 发它。
- 环境错误 → 重试一次；仍失败冻结。
- 测试过期 / 契约缺失 → 不自动修，写汇报。

**先查越界，通过再提交**（顺序反了会把越界改动钉进提交历史）：

```bash
git -C "$WT" add -A
git -C "$WT" diff --cached --no-renames --name-status
```

出现 unit 文件清单外的路径 → `paseo stop "$id"`，置 `stage:frozen`，写进汇报。`--no-renames` 不能省：默认 `--name-only` 对 rename 只报新名，旧名越界会漏看。

通过则提交，head 记进 state（`stage:gate`）：

```bash
git -C "$WT" commit -qm '<摘要> (by pi <id前8位>)'
```

踩坑速查：
- pi provider 不支持 `--mode`：它的 `listModes` 返回空数组（源码 `providers/pi/agent.js` 里 `return { models, modes: [] }`），传了会被 daemon 以 `Invalid mode ... Available modes: (none)` 拒绝。`--mode` 管的是 agent 的行为模式（plan/bypass 这类），跟 `--model` 是两条路：`--model` 由 paseo 拼进 `pi --mode rpc --model <model>` 的 argv，模型照传不误。
- `paseo run` 失败也会先建 workspace；重跑用 `--workspace <wks_id>` 复用，别重复建。
- workspace 找不到就 `paseo workspace ls --json`，按分支名或 cwd 匹配。
- GUI 关闭 ≠ daemon 退出；daemon 挂了只会是 `paseo status` 报不可达。
- repo 必须已有至少一个提交，否则 worktree 建不出来。

## 4. 评审阶段（冷评审 + 主脑裁决）

评审由独立 subagent 做，主脑不评自己写的 spec。

1）宿主跑确定性检查（这是门禁，由程序判定，不由任何 agent 自述）：

```bash
cd "$WT"
[ -z "$(git -C "$WT" status --porcelain)" ] || { echo '工作区有未提交改动'; exit 1; }
ocr delegate preview --format json --from <基线> --to HEAD > "$TASK_DIR/<unit>.preview.json"
RFILES=$(jq -r '.reviewable_files[].path' "$TASK_DIR/<unit>.preview.json")
[ -n "$RFILES" ] && ocr delegate rule --format json $RFILES > "$TASK_DIR/<unit>.rules.json" \
  || echo '{"groups":[]}' > "$TASK_DIR/<unit>.rules.json"
git -C "$WT" --no-pager diff --no-ext-diff --no-textconv --no-color --no-renames <基线>..HEAD > "$TASK_DIR/<unit>.diff"
git -C "$WT" diff --no-renames --name-only <基线>..HEAD   # 越界；触及已有测试文件 → 标记，评审必须核对断言没被削弱
<验收命令>                                    # 在 worktree 里重跑
<typecheck / lint，仓库有就一并跑>             # 没有就跳过，别自创
```

任意一项红 → 不进评审：验收红按 §3 分类；越界或已有测试被改 → 冻结并写汇报。

- preview 为 unit 文件清单里每个文件给出归属：在 `reviewable_files`，或在 `excluded_files` 且带明确 `exclude_reason`（`unsupported_ext`、排除规则等）。两边都没有 → 冻结写汇报，不要让评审器自己补范围。
- `reviewable_count` 为 0 时先看 unit 是不是纯文档：纯文档没有可评审代码，照常进评审（`rules.json` 为空组）；unit 含代码却全被排除 → 冻结。
- preview 与 rule 的输出落盘为 `$TASK_DIR/<unit>.preview.json` / `.rules.json`，只在宿主跑这一次，不重跑，也不交给 agent 自己选文件；下一步 subagent 只收文件路径。

2）冷评审 subagent（新上下文，只看 unit 文件和仓库里的 diff，不看 worker 自述）：

一条消息里起 A 路；B 路只在两种情况下起，每种各起一次（同一轮最多两次），两次调用上下文互不可见：

- `subagent_type: paseo-reviewer-a`：全量冷评审，覆盖正确性、契约、验收。
- `subagent_type: paseo-reviewer-b`：diff 跨 ≥3 文件或含安全/并发改动时做定向复审，只审安全/数据丢失/并发/已有测试被削弱四个维度，不重复 A 已覆盖的内容；A 报了 High 时逐条证伪，只有给出具体反证才降级——沉默不是否认。B 路 prompt 必须写明 `mode=dimension` 或 `mode=refute`；refute 把该 unit 所有 High 放进同一次调用，逐条给结论。
- prompt 包含：`worktree=<绝对路径>`、`基线=<sha>`、unit 文件路径、`preview=<.preview.json 路径>`、`rules=<.rules.json 路径>`（B 路不带这两项）、验收命令与最近一次输出，以及下面的输出格式。只给指针和原文，不写主脑的怀疑、倾向或上轮结论；证伪 prompt 例外，只附被质疑的那条 finding。
- B 路不带 `preview`/`rules`：它只做四维复审或逐条证伪，全量规则清单对它没有用。
- 评审器自己跑 `git -C <worktree> diff --no-color <基线>..HEAD` 取 diff，不把 diff 塞进主脑上下文。

输出要求（写进 prompt）：

```text
verdict: accept | repair | escalate
{"severity":"High","path":"src/x.ts","line":42,"claim":"...","evidence":"...","fixed_when":"..."}
{"severity":"Medium","path":"src/y.ts","line":7,"claim":"...","evidence":"...","fixed_when":"..."}
```

severity 定义：High（明显 bug/安全/数据丢失）、Medium（错误处理缺口/性能）、Low（nit，不进修复）。只要 verdict 行和 JSON 行，不要围栏、不要前言、不要总结。

证伪模式只输出每条 finding 一行：`{"finding":"<原 claim 摘要>","result":"refuted|upheld","evidence":"..."}`，不给 verdict。

评审器没有 Write/Edit，Bash 只用于读 diff 和跑只读命令；但它有全量 Bash，评审回来宿主必须核对：`git -C "$WT" status --porcelain` 为空、`git -C "$WT" rev-parse HEAD` 等于 state 的 `head`（评审器也会自报 `head:` 行，以宿主核对为准）。对不上 → 丢弃本轮结论并重跑。

解析时按行过滤 `^verdict:`、`^head:` 和 `^{`；verdict 行和 JSON 行两样都找不到先原样重跑一次（多半是闲话或格式漂移），仍没有才判 `escalate`，别猜。

3）主脑只做裁决：

- `accept` 且确定性检查全绿 → 进 §5 收尾
- `repair` → findings 回传原 worker
- `escalate`（需求冲突 / 权限边界 / 架构取舍 / 连续失败）→ 冻结该 unit，写汇报
- 主脑不能丢弃 High：要么进修复，要么在汇报里逐条写不修的具体理由；Medium 可降级但必须留痕
- B 路报的 finding 与 A 路同级对待：High 必须进修复或写不修理由，Medium 留痕；B 路 verdict 不覆盖 A 路，findings 合并后由主脑裁决

B 路没跑、或没给出具体反证 → 该 High 原级保留，必须进修复或在汇报里写不修理由。

## 5. 收敛阶段

findings 回传**原 agent**（复用上下文，比新 worker 准）；回传内容写成文件再发，不把 JSON 内联进命令行：

```bash
# 主脑把回传消息写进 $TASK_DIR/review/<unit>-<round>-repair.md，内容：
# 「评审 verdict=repair。逐条修复以下 findings，不动清单外文件、不改已有测试；
#   改完重跑 <验收命令>、git add -A 提交（提交信息注明 round N）、贴验收输出。」
# 后接 findings 全文
paseo send "$id" --no-wait --prompt-file "$TASK_DIR/review/<unit>-<round>-repair.md"
paseo wait "$id" --timeout 900
```

每轮修完先重跑 §4.1 整套门禁，外加两条：

- `git -C "$WT" status --porcelain` 必须为空（worker 忘了提交 → 打回提交，不计入修复次数）
- `git -C "$WT" rev-parse HEAD` 必须不等于上一轮 `head`（HEAD 没动 → 打回）

全绿才允许复审；复审 diff 恒为 基线..最新 head。门禁通过后更新 state 的 `head` 与 `stage`。

上限：

- 每条 finding ≤2 次修复
- 每个 unit ≤2 轮 review-fix
- 同一验收命令连续 2 次红 → 冻结
- 整链 ≤3h（起点＝`$TASK_DIR/state/chain.json` 的 `chain_start`，续跑不重置）；连续 2 个 unit 触到上限 → 整链停，写 `ESCALATE`

到限仍有 High → `paseo stop "$id"`，置 `stage:frozen`，剩余 findings 连同 worktree 路径写进汇报。
Medium 未清不阻塞合并，但必须写进汇报；Low 静默丢弃。

每轮评审结果存 `$TASK_DIR/review/<unit>-<round>.md`（verdict + findings + 门禁输出），复审和续跑都以文件为准。

修复后复审用 `SendMessage` 回到同一个 `paseo-reviewer-a`（agentId 记在 state 的 `reviewer_a`）：它保留上一轮 findings，能逐条核对 `fixed_when`。丢了 agentId 就新起一路，并把 `$TASK_DIR/review/` 里的上轮 findings 文件路径一起给它。

全部 unit 收敛后，unit 间有共享契约（跨 unit 接口、数据结构）就做一次集成验收：挑一个 unit 的 worktree，把其余 unit 分支 merge 进去，跑全部验收命令；红了按 §3 分类回传对应 unit，只记事实不扩大战线。无共享契约就跳过。

清理并汇报：

```bash
paseo workspace archive <每个收敛 unit 的 wks>
```

- **冻结的 unit 不 archive**：archive 是 `git worktree remove --force` + 删目录，会销毁留给用户排查的现场；冻结 unit 的 worktree 路径写进汇报，由用户处置。
- `paseo delete` 不用跑：archive 已把该 workspace 的 agent 一并归档。`wks` 丢了就 `paseo workspace ls --json` 按 `wt` 反查。

向用户汇报——每 unit 一行（agent id/分支/评审轮数/verdict/门禁结果/结果），冻结的单独说，合并时机留给用户（repo 本体从未被触碰）。

## 6. 收尾与沉淀

汇报后把本链踩坑 `mem_save` 进 engram：title 以 `paseo-flow lesson:` 开头，type=discovery（误判类）或 bugfix（流程缺陷类），内容含路由误判（降错档）、评审误报漏报、worker 反复卡点，各带证据与对应 unit。下个同类任务 §1 前按这个前缀 `mem_search` 一遍再开工。改本 skill 的规则要先 propose（写清证据与影响面），跑任务时不许顺手改流程。
