---
name: ao-flow
description: '主脑编排的全自动多 agent 编码流（设计→拆分→执行→评审→收敛）：用 Workflow tool 起多模型并行设计方案并交叉验证，主脑合成 TASK_SPEC 拆分任务，AO daemon 管 pi worker（worktree 隔离）执行，宿主 agent 代跑 ocr delegate 评审并回传修复。大任务走全链，小任务自动跳到执行链。适用于"这事交给 agent 群做，我不参与，随时可打断"的完整委托。前置依赖：ao CLI、pi 已登录、ocr 已装。'
argument-hint: "<任务描述>"
---

# ao-flow v2：主脑编排的多 agent 全链编码流

驱动者是本会话（Claude 主脑）。用户一次指令，全程零参与、零反问；用户随时 Esc/打字打断。本 skill 是路由+协议：按任务规模选链，各阶段照章执行，产物落盘可审计。

## 0. 路由（第一件事，判断走哪条链）

| 信号 | 链路 |
|---|---|
| 单文件/验收命令明确/方案无争议 | **短链**：直接 §3 执行 → §4 评审 → §5 收敛 |
| 多模块/方案未定/技术选型/重构级 | **全链**：§1 设计 → §2 拆分 → §3 → §4 → §5 |
| 纯咨询（只想要方案不要代码） | 只走 §1 §2，输出 TASK_SPEC 落档即收 |

拿不准就按全链走——设计阶段多余的成本远小于错误方案返工。

## 1. 设计阶段（多模型并行 + 交叉验证）

用 **Workflow tool** 起后台编排（用户带 ultracode 关键词或直接说"多模型设计"时必须走这段）。pi 子进程调用模板（本机实测）：

```bash
cd <repo> && pi -p -nc --no-tools --no-session --model '<model-id>' '<escaped-prompt>'
```

可用模型池（magpie，免费异构）：`commandcode-plan/meta/muse-spark-1.3`、`commandcode-plan/xai/grok-4.7`、`group/glm`、`group/free`。

编排形状（workflow-authoring 的 pipeline/judge panel 模式）：

1. **N 路 lens 并行调研**：每个模型一个独立视角（如官方生态路线/通用框架路线/评审验证路线），prompt 自带完整背景（子进程间不共享上下文）。
2. **各模型独立起草**：互相能看到调研结论、看不到对方草案。
3. **交叉验证（关键，不可省）**：换一个模型对草案的**技术主张逐条 refute**——命令行参数是否真实存在、语义是否写反、流程是否断链。验证者应实际跑 `--help` 查证，不信草案原文。
4. **主脑合成**：结构取最优草案，事实细节以验证结论钉死；三方分歧点显式保留，不强行统一。

**pi 输出是纯文本不是 JSON**：主脑侧用正则 `/\{[\s\S]*\}/` 提取首个 JSON 对象容错解析；长 prompt 下 pi 可能超时返回空——agent 结果要 `.filter(Boolean)`，空的那路跳过或重试一次。

产出落盘：`sessions/<task-id>/research.md`（含分歧点）+ 设计草案存档。

## 2. 拆分阶段（主脑独占，不开子进程）

合成结果拆成 **task units**，每个 unit 一个文件 `sessions/<task-id>/units/<n>-<slug>.md`，必含：

- **目标**：一句话可验收的结果
- **文件清单**：只许动这些
- **验收命令**：命令行可判定（`node test.js` / `npm test`），没有验收命令的 unit 不许派发
- **依赖边**：依赖哪个 unit；无依赖的并行派，有依赖的串行等

拆分原则：tracer-bullet（一条票一个端到端可验证的弹道），宁粗勿细——3 个大 unit 好过 9 个碎 unit。v1 并行 worker ≤ 3。

## 3. 执行阶段（AO daemon + pi workers）

前置：`ao status` 非 ready 则 `nohup '/Applications/Agent Orchestrator.app/Contents/Resources/daemon/ao' daemon > ~/.ao/daemon-standalone.log 2>&1 &`，sleep 6 确认。

每个 unit：

```bash
ao spawn --project <proj> --harness pi --model group/free --name '<unit短名>' \
  --output artifact --prompt '<unit 全文：目标+文件+验收命令+禁区>'
ao send --session <sid> --message '开始执行上述任务。'    # spawn 后 worker 不自动开干，必须推一把
```

踩坑速查：
- `DEFAULT_BRANCH_UNRESOLVED`：repo 无 remote → `git remote add origin . && git update-ref refs/remotes/origin/<主分支> refs/heads/<主分支>`，重试。
- worktree 路径**别假设，先找**：`find ~/.ao/data/worktrees/<proj> -name '<主文件>' | head -1`。
- 等完成带熔断（单轮 15min）：`until [ "$(ao session get <sid> | grep -c 'status: idle')" = "1" ]; do sleep 10; done`，超时先 `ao send` 让 worker 汇报进度再决定等/杀。
- 验收：worktree 里跑验收命令，红了直接把 stderr 回传该 session 修（不用等评审）。
- 通过则 `git add -A && git commit -qm '<摘要> (by pi <sid>)'`。

## 4. 评审阶段（宿主代跑 ocr delegate + 可选对抗二审）

```bash
cd "$WT"
ocr delegate preview --format json --from HEAD~1 --to HEAD   # 已 commit 必须用 range/commit 模式
ocr delegate rule --format json <files...>
git --no-pager diff --no-ext-diff --no-textconv --no-color HEAD~1..HEAD -- "<path>"
```

**评审推理由本会话完成**：对照 rule 组 checklist 逐条过 diff 新增行，输出结构化 findings（path/line/severity/fix）。severity：High（明显 bug/安全/数据丢失）、Medium（错误处理缺口/性能）、Low（nit，静默丢弃）。覆盖强制：preview 每个 `(path,status)` 标记 reviewed/skipped（带原因）。

**对抗二审（大任务启用）**：High 涉及安全/并发/核心逻辑时，另起一个异构模型看同一 diff 再评一遍（`pi -p -nc --no-tools --no-session --model 'commandcode-plan/xai/grok-4.7' '审查此 diff：<diff 内容>，只报 High'`），两路都报的才进修复，单路报的降级 Medium。

## 5. 收敛阶段

findings 回传**原 session**（复用上下文，比新 worker 准）：

```bash
ao send --session <sid> --message '代码评审发现 N 个问题：1. [High] <path>:<line> <问题>——<fix> ... 请逐条修复，不动无关代码，改完跑 <验收命令>。'
```

循环 §3 等待→提交→§4 二审，直到 High/Medium 全清或 **max-rounds=2**；到顶仍有 High → 冻结该 unit，`ao session kill`，剩余 findings 连同 worktree 路径写进汇报。

全部 unit 收敛后：`ao session kill <每个 sid>`，向用户汇报——每 unit 一行（session/分支/评审轮数/结果），冻结的单独说，合并时机留给用户（repo 本体从未被触碰）。

## 速查触发词

- "这事交给 agent 做"（大任务）→ 全链
- "把 X 改了并评审"（小任务）→ 短链
- "多模型设计 X" → §1 §2 后停，落档汇报
- "并行做这几件事" → §2 拆完无依赖 unit 并行 spawn
