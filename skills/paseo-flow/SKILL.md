---
name: paseo-flow
description: '主脑编排的全自动多 agent 编码流（设计→拆分→执行→评审→收敛）：设计由主脑自己出，缺外部事实时用两个原生 subagent（paseo-researcher-a/b，不同模型）并行调研+交叉验证，主脑合成 TASK_SPEC 拆 task units，派发前用 paseo-plan-critic 审 unit 规格，Paseo daemon 管 pi worker（worktree 隔离）执行，paseo-reviewer-a 全量冷评审、paseo-reviewer-b 做安全维度定向复审与 High 逐条证伪，主脑裁决，程序门禁判定完成，有界修复，状态落盘可续跑，人合并。拿不准降档走短链。前置依赖：paseo CLI + daemon、pi 已登录、ocr 已装、claude CLI 已接 magpie 网关、本 skill 的 agents/ 已同步到 ~/.claude/agents/paseo-flow/。'
argument-hint: "<任务描述>"
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
- 连续两次短链零 findings 且一次通过 → 同规模任务继续走短链。

任务一开始就钉死 `TASK_DIR="$HOME/data/paseo-flow/<task-id>"`（放仓库外，避免污染工作区），并 `mkdir -p "$TASK_DIR"/{units,state,review}`；后文所有落盘都用 `$TASK_DIR` 绝对路径。§4 会 cd 进 worktree，相对路径会把文件写进别人的分支。

## 1. 设计阶段（主脑出方案，调研才外包）

**方案由主脑自己出**——初始信息、技术路线、取舍、接口形态全在本会话里成型，不外包设计：设计的价值就在全局上下文，交出去等于把它丢了。

只有「缺外部事实」时才起 subagent 调研：**一条消息里并行发两个 Agent 调用**，两路同题、各搜各的。

- `subagent_type: paseo-researcher-a`，prompt 写清：要哪些事实、什么格式、要几条来源、每条必须带链接，产出写到 `$TASK_DIR/research-a.md`。
- `subagent_type: paseo-researcher-b`，同一个问题，产出写到 `$TASK_DIR/research-b.md`。
- 两个定义模型不同、上下文独立，互不可见；主脑只读两份文件，不把全文吞进上下文。

约束：

- 逼 subagent 自己核实：跑 `--help`、读源码、点开 URL、多来源交叉；交回来的必须是「结论 + 出处」，没出处的事实一律记为未验证。
- 调研器没有 `Edit`/`Agent`，但有 `Write`——只许写 `$TASK_DIR/research-*.md`，别动仓库源码。
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
- **测试证据**：新增测试必须在实现前于基线代码上跑红一次（新测试文件可先复制到基线 worktree 跑）；worker 第一步回传红输出，主脑存到 `$TASK_DIR/units/<n>.red.txt`，§4 核对。没红过的测试不算证据
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

前置：

```bash
paseo status | grep -q 'localDaemon: running' || paseo daemon start
```

每个 unit（在目标 repo 根目录下）：

有依赖边的 unit 必须 `--base <上游 unit 分支>` 从上游分支开；默认的 branch-off 从 repo HEAD 开，会看不到上游改动。

```bash
cd <repo>
id=$(paseo run --quiet --provider pi --model magpie/group/worker \
  --new-workspace worktree --worktree-mode branch-off --new-branch <unit分支> \
  --title '<unit短名>' --no-wait '<unit 全文：目标+基线+契约+文件清单+验收命令+测试证据+依赖+必读+非目标>')
```

`paseo run` 的 prompt 就是初始任务，agent 立即开干（不像 ao 需要 send 推一把）。`--quiet` 的 stdout 只有 agent id，workspace 提示走 stderr，`id=$(...)` 安全。

跑完先查 id 非空，别拿空字符串去 inspect：

```bash
[ -n "$id" ] || { echo 'paseo run 没有返回 id'; exit 1; }
```

拿 worktree 路径（**别假设，先问 daemon**）：

```bash
WT=$(paseo inspect "$id" --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Cwd"])')
```

立刻把状态落到 `$TASK_DIR/state/<unit>.json`：`{"id","wt","base","branch","round","verdict"}`。每次 `wait`、`send`、评审回来都更新 round/verdict。会话被压缩或打断后照这个文件续跑，不靠回忆。

等完成（单轮熔断 15min）：

```bash
paseo wait "$id" --timeout 900
```

超时不等于失败：先 `paseo send "$id" --no-wait --prompt '汇报当前进度与卡点'`，再决定继续等或 `paseo stop "$id"`。同一 unit 只允许问一次进度。

验收：在 `$WT` 里跑该 unit 的验收命令。

```bash
cd "$WT" && <验收命令>
```

红了先分类，再决定回传：

- 实现错误 → 回传同一 agent 修（不用等评审）：
  `paseo send "$id" --no-wait --prompt '验收失败，stderr 如下：<...>。修复后重跑 <验收命令>。'`
- 环境错误 → 重试一次；仍失败冻结。
- 测试过期 / 契约缺失 → 不自动修，写汇报。

通过则提交：

```bash
git -C "$WT" add -A && git -C "$WT" commit -qm '<摘要> (by pi <id前8位>)'
```

提交后做越界检查，不通过就不进评审：

```bash
git -C "$WT" diff --name-only <基线>..HEAD
```

出现 unit 文件清单外的路径 → `paseo stop "$id"`，冻结，写进汇报。

踩坑速查：
- pi provider 不支持 `--mode`：它的 `listModes` 返回空数组（源码 `providers/pi/agent.js` 里 `return { models, modes: [] }`），传了会被 daemon 以 `Invalid mode ... Available modes: (none)` 拒绝。`--mode` 管的是 agent 的行为模式（plan/bypass 这类），跟 `--model` 是两条路：`--model` 由 paseo 拼进 `pi --mode rpc --model <model>` 的 argv，模型照传不误。
- `paseo run` 失败也会先建 workspace；重跑用 `--workspace <wks_id>` 复用，别重复建。
- workspace 找不到就 `paseo workspace ls --json`，按分支名匹配。
- GUI 关闭 ≠ daemon 退出；daemon 挂了只会是 `paseo status` 报不可达。
- repo 必须已有至少一个提交，否则 worktree 建不出来。

## 4. 评审阶段（冷评审 + 主脑裁决）

评审由独立 subagent 做，主脑不评自己写的 spec。

1）宿主跑确定性检查（这是门禁，由程序判定，不由任何 agent 自述）：

```bash
cd "$WT"
ocr delegate preview --format json --from <基线> --to HEAD
ocr delegate rule --format json <files...>
git -C "$WT" --no-pager diff --no-ext-diff --no-textconv --no-color <基线>..HEAD > "$TASK_DIR/<unit>.diff"
git -C "$WT" diff --name-only <基线>..HEAD          # 越界；触及已有测试文件 → 标记，评审必须核对断言没被削弱
<验收命令>                                           # 在 worktree 里重跑
<typecheck / lint，仓库有就一并跑>                    # 没有就跳过，别自创
```

任意一项红 → 不进评审：验收红按 §3 分类；越界或已有测试被改 → 冻结并写汇报。

2）冷评审 subagent（新上下文，只看 unit 全文和仓库里的 diff，不看 worker 自述）：

一条消息里起 A 路；B 路只在两种情况下起，每种各起一次（同一轮最多两次），两次调用上下文互不可见：

- `subagent_type: paseo-reviewer-a`：全量冷评审，覆盖正确性、契约、验收。
- `subagent_type: paseo-reviewer-b`：diff 跨 ≥3 文件或含安全/并发改动时做定向复审，只审安全/数据丢失/并发/已有测试被削弱四个维度，不重复 A 已覆盖的内容；A 报了 High 时逐条证伪，只有给出具体反证才降级——沉默不是否认。B 路 prompt 必须写明 `mode=dimension` 或 `mode=refute`；refute 把该 unit 所有 High 放进同一次调用，逐条给结论。
- prompt 包含：`worktree=<绝对路径>`、`基线=<sha>`、unit 全文、验收命令与最近一次输出，以及下面的输出格式。只给指针和原文，不写主脑的怀疑、倾向或上轮结论；证伪 prompt 例外，只附被质疑的那条 finding。
- 评审器自己跑 `git -C <worktree> diff --no-color <基线>..HEAD` 取 diff，不把 diff 塞进主脑上下文。

输出要求（写进 prompt）：

```text
verdict: accept | repair | escalate
{"severity":"High","path":"src/x.ts","line":42,"claim":"...","evidence":"...","fixed_when":"..."}
{"severity":"Medium","path":"src/y.ts","line":7,"claim":"...","evidence":"...","fixed_when":"..."}
```

severity 定义：High（明显 bug/安全/数据丢失）、Medium（错误处理缺口/性能）、Low（nit，不进修复）。只要 verdict 行和 JSON 行，不要围栏、不要前言、不要总结。

证伪模式只输出每条 finding 一行：`{"finding":"<原 claim 摘要>","result":"refuted|upheld","evidence":"..."}`，不给 verdict。

评审器没有 Write/Edit，Bash 只用于读 diff 和跑只读命令；评审后宿主仍要查一次 `git -C "$WT" status --porcelain`，有输出说明它动了工作区，丢弃本轮结论并重跑。

解析时按行过滤 `^verdict:` 和 `^{`；两样都找不到就判 `escalate`，别猜。

3）主脑只做裁决：

- `accept` 且确定性检查全绿 → 进 §5 收尾
- `repair` → findings 回传原 worker
- `escalate`（需求冲突 / 权限边界 / 架构取舍 / 连续失败）→ 冻结该 unit，写汇报
- 主脑不能丢弃 High：要么进修复，要么在汇报里逐条写不修的具体理由；Medium 可降级但必须留痕
- B 路报的 finding 与 A 路同级对待：High 必须进修复或写不修理由，Medium 留痕；B 路 verdict 不覆盖 A 路，findings 合并后由主脑裁决

B 路没跑、或没给出具体反证 → 该 High 原级保留，必须进修复或在汇报里写不修理由。

## 5. 收敛阶段

findings 回传**原 agent**（复用上下文，比新 worker 准）：

```bash
paseo send "$id" --no-wait --prompt '评审 verdict=repair。逐条修复以下 findings，不动清单外文件、不改已有测试，改完重跑 <验收命令> 并贴输出：<JSON findings>'
paseo wait "$id" --timeout 900
```

每轮修完先重跑 §4.1 的整套门禁（验收 / 越界 / `git status --porcelain` / 已有测试核对），全绿才允许复审；红的不进复审，按 §3 分类。

上限：

- 每条 finding ≤2 次修复
- 每个 unit ≤2 轮 review-fix
- 同一验收命令连续 2 次红 → 冻结
- 整链 ≤3h；连续 2 个 unit 触到上限 → 整链停，写 `ESCALATE`

到限仍有 High → `paseo stop "$id"`，冻结，剩余 findings 连同 worktree 路径写进汇报。
Medium 未清不阻塞合并，但必须写进汇报；Low 静默丢弃。

每轮评审结果存 `$TASK_DIR/review/<unit>-<round>.md`（verdict + findings + 门禁输出），复审和续跑都以文件为准。

修复后复审用 `SendMessage` 回到同一个 `paseo-reviewer-a`（Agent 调用返回的 agentId 要记下）：它保留上一轮 findings，能逐条核对 `fixed_when`。丢了 agentId 就新起一路，并把 `$TASK_DIR/review/` 里的上轮 findings 一起给它。

全部 unit 收敛后清理并汇报：

```bash
paseo delete <每个 id>                      # 只删 agent
paseo workspace archive <每个 wks_id>        # 才清 worktree
```

向用户汇报——每 unit 一行（agent id/分支/评审轮数/verdict/门禁结果/结果），冻结的单独说，合并时机留给用户（repo 本体从未被触碰）。

## 6. 收尾与沉淀

汇报后把本链的踩坑追加进 `$HOME/data/paseo-flow/lessons.md`：路由误判（降错档）、评审误报或漏报、worker 反复卡点。同类任务 §1 前先读最近一份。改本 skill 的规则要先 propose（写清证据与影响面），跑任务时不许顺手改流程。

## 速查触发词

- "这事交给 agent 做"（大任务）→ 全链
- "把 X 改了并评审"（小任务）→ 短链
- "并行做这几件事" → §2 拆完无依赖 unit 并行 run
- "只出方案不写代码" → §1 §2 后停，输出 TASK_SPEC 落档即收
