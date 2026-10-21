---
name: paseo-flow
description: '主脑编排的全自动多 agent 编码流（设计→拆分→执行→评审→收敛）：设计用 Claude 原生 subagent 并行+交叉验证，主脑合成 TASK_SPEC 拆 task units，Paseo daemon 管 pi worker（worktree 隔离）执行，宿主代跑 ocr delegate 评审并回传修复。大任务走全链，小任务自动跳到执行链。适用于"这事交给 agent 群做，我不参与，随时可打断"的完整委托。前置依赖：paseo CLI + daemon、pi 已登录、ocr 已装。'
argument-hint: "<任务描述>"
---

# paseo-flow：主脑编排的多 agent 全链编码流

驱动者是本会话（Claude 主脑）。用户一次指令，全程零参与、零反问；用户随时 Esc/打字打断。本 skill 是路由+协议：按任务规模选链，各阶段照章执行，产物落盘可审计。

## 角色分配（按模型输出上限定岗）

| 角色 | 模型 | 干什么 | 为什么是它 |
|---|---|---|---|
| 主脑 | 本会话 | 路由、合成、拆 unit、评审推理、收敛决策 | 唯一有全局上下文，不外包 |
| 设计 lens / 交叉验证 | Claude 原生 subagent（Agent tool） | 并行调研、独立起草、逐条 refute | 长输出稳定、自带隔离上下文、能真跑 `--help`/读源码 |
| 执行 worker | `paseo run --provider pi --model magpie/group/worker` | worktree 内写代码、跑验收、修 findings | 输出上限 384k，独占 worktree |
| 对抗二审（默认） | `pi --model magpie/group/reviewer1` | 只看 High 的短裁决 | 输出上限 32k，逼它短，天然适合「只报 High」 |
| 深度二审（大 diff） | `pi --model magpie/group/reviewer2` | 跨多文件/安全/并发 diff 复审 | 输出上限 131k，能铺开讲 |
| 单点咨询 | `pi --model magpie/group/worker` | 技术选型问一句、方案抽查 | 短问短答不挑模型，直接复用执行角色，少记一个名字 |

pi 调用模板（咨询/二审，不进 worktree、不落 session）：

```bash
pi -p -nc --no-tools --no-session --model 'magpie/group/reviewer1' '<prompt>'
```

## 0. 路由（第一件事，判断走哪条链）

| 信号 | 链路 |
|---|---|
| 单文件/验收命令明确/方案无争议 | **短链**：直接 §3 执行 → §4 评审 → §5 收敛 |
| 多模块/方案未定/技术选型/重构级 | **全链**：§1 设计 → §2 拆分 → §3 → §4 → §5 |
| 纯咨询（只想要方案不要代码） | 只走 §1 §2，输出 TASK_SPEC 落档即收 |

拿不准就按全链走——设计阶段多余的成本远小于错误方案返工。

## 1. 设计阶段（Claude 原生 subagent 并行 + 交叉验证）

用 **Agent tool** 起多个原生 subagent 并行设计（不要用 pi 子进程做长输出——实测会超时返空；原生 subagent 稳定且每个自带隔离上下文）。编排形状：

1. **N 路 lens 并行调研**：单条消息里发 N 个 Agent 调用（同 run 并行），每个 subagent 一个独立视角（如官方生态路线/通用框架路线/评审验证路线），prompt 自带完整背景（subagent 间不共享上下文）。subagent 有全工具权限：允许并鼓励它们实际跑 `--help`、读源码、联网查证。
2. **主脑汇总调研**：分歧点显式标注（某结论 2:1 就是决策信息），不强行统一。
3. **N 路独立起草**：再起 N 个 subagent 各出一版设计，互相看得到汇总调研、看不到对方草案。
4. **交叉验证（关键，不可省）**：再起 1-2 个 subagent 当苛刻评审，对草案的**技术主张逐条 refute**——命令行参数是否真实存在（跑 `--help` 验证）、语义是否写反、流程是否断链。不信草案原文。
5. **主脑合成**：结构取最优草案，事实细节以验证结论钉死；分歧保留进 research.md。

subagent 的最终文本就是返回值，要求它们直接输出数据/结构化 markdown，不写给人看的客套。要一句第三方意见时用 `group/orchestrator`，别开 paseo agent。

产出落盘：`sessions/<task-id>/research.md`（含分歧点）+ 设计草案存档。

## 2. 拆分阶段（主脑独占，不开子进程）

合成结果拆成 **task units**，每个 unit 一个文件 `sessions/<task-id>/units/<n>-<slug>.md`，必含：

- **目标**：一句话可验收的结果
- **文件清单**：只许动这些
- **验收命令**：命令行可判定（`node test.js` / `npm test`），没有验收命令的 unit 不许派发
- **依赖边**：依赖哪个 unit；无依赖的并行派，有依赖的串行等

拆分原则：tracer-bullet（一条票一个端到端可验证的弹道），宁粗勿细——3 个大 unit 好过 9 个碎 unit。并行 worker ≤ 3。

## 3. 执行阶段（Paseo daemon + pi workers）

前置：

```bash
paseo status | grep -q 'localDaemon: running' || paseo daemon start
```

每个 unit（在目标 repo 根目录下）：

```bash
cd <repo>
id=$(paseo run --quiet --provider pi --model magpie/group/worker \
  --new-workspace worktree --worktree-mode branch-off --new-branch <unit分支> \
  --title '<unit短名>' --no-wait '<unit 全文：目标+文件+验收命令+禁区>')
```

`paseo run` 的 prompt 就是初始任务，agent 立即开干（不像 ao 需要 send 推一把）。`--quiet` 的 stdout 只有 agent id，workspace 提示走 stderr，`id=$(...)` 安全。

拿 worktree 路径（**别假设，先问 daemon**）：

```bash
WT=$(paseo inspect "$id" --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Cwd"])')
```

等完成（单轮熔断 15min）：

```bash
paseo wait "$id" --timeout 900
```

超时不等于失败：先 `paseo send "$id" --no-wait --prompt '汇报当前进度与卡点'`，再决定继续等或 `paseo stop "$id"`。

验收：在 `$WT` 里跑该 unit 的验收命令，红了直接把 stderr 回传同一 agent 修（不用等评审）：

```bash
paseo send "$id" --no-wait --prompt '验收失败，stderr 如下：<...>。修复后重跑 <验收命令>。'
paseo wait "$id" --timeout 900
```

通过则：

```bash
git -C "$WT" add -A && git -C "$WT" commit -qm '<摘要> (by pi <id前8位>)'
```

踩坑速查：
- pi provider 不支持 `--mode`：它的 `listModes` 返回空数组（源码 `providers/pi/agent.js` 里 `return { models, modes: [] }`），传了会被 daemon 以 `Invalid mode ... Available modes: (none)` 拒绝。`--mode` 管的是 agent 的行为模式（plan/bypass 这类），跟 `--model` 是两条路：`--model` 由 paseo 拼进 `pi --mode rpc --model <model>` 的 argv，模型照传不误。
- `paseo run` 失败也会先建 workspace；重跑用 `--workspace <wks_id>` 复用，别重复建。
- workspace 找不到就 `paseo workspace ls --json`，按分支名匹配。
- GUI 关闭 ≠ daemon 退出；daemon 挂了只会是 `paseo status` 报不可达。
- repo 必须已有至少一个提交，否则 worktree 建不出来。

## 4. 评审阶段（宿主代跑 ocr delegate + 对抗二审）

```bash
cd "$WT"
ocr delegate preview --format json --from HEAD~1 --to HEAD   # 已 commit 必须用 range/commit 模式
ocr delegate rule --format json <files...>
git --no-pager diff --no-ext-diff --no-textconv --no-color HEAD~1..HEAD -- "<path>"
```

**评审推理由本会话完成**：对照 rule 组 checklist 逐条过 diff 新增行，输出结构化 findings（path/line/severity/fix）。severity：High（明显 bug/安全/数据丢失）、Medium（错误处理缺口/性能）、Low（nit，静默丢弃）。覆盖强制：preview 每个 `(path,status)` 标记 reviewed/skipped（带原因）。

**对抗二审（大任务启用）**：High 涉及安全/并发/核心逻辑时，另起异构模型看同一 diff 再评一遍——默认 `reviewer1` 只要 High，diff 跨多文件或要展开推理时换 `reviewer2`：

```bash
pi -p -nc --no-tools --no-session --model 'magpie/group/reviewer1' \
  '只报 High 级问题，逐条给 path:line 与修复建议，无则回复 NONE。diff 如下：<diff>'
```

两路都报的才进修复，单路报的降级 Medium。

## 5. 收敛阶段

findings 回传**原 agent**（复用上下文，比新 worker 准）：

```bash
paseo send "$id" --no-wait --prompt '代码评审发现 N 个问题：1. [High] <path>:<line> <问题>——<fix> ... 请逐条修复，不动无关代码，改完跑 <验收命令>。'
paseo wait "$id" --timeout 900
```

循环 §3 等待→提交→§4 二审，直到 High/Medium 全清或 **max-rounds=2**；到顶仍有 High → 冻结该 unit，`paseo stop "$id"`，剩余 findings 连同 worktree 路径写进汇报。

全部 unit 收敛后清理并汇报：

```bash
paseo delete <每个 id>                      # 只删 agent
paseo workspace archive <每个 wks_id>        # 才清 worktree
```

向用户汇报——每 unit 一行（agent id/分支/评审轮数/结果），冻结的单独说，合并时机留给用户（repo 本体从未被触碰）。

## 速查触发词

- "这事交给 agent 做"（大任务）→ 全链
- "把 X 改了并评审"（小任务）→ 短链
- "多模型设计 X" → §1 §2 后停，落档汇报
- "并行做这几件事" → §2 拆完无依赖 unit 并行 run
