---
name: ao-flow
description: '无人值守多 agent 编码流：Orchestrator.inc daemon 管 pi worker（worktree 隔离），宿主 agent 代跑 ocr delegate 评审并回传修复，直到收敛。适用于"把任务交给 pi 做、完事评审、高危问题让它自己修"的完整委托场景。前置依赖：ao CLI（~/.local/bin/ao）、pi 已登录、ocr 已装（@alibaba-group/open-code-review）。daemon 未跑时先启动。'
argument-hint: "<任务描述或任务列表> [--project <id>] [--model <pi模型>] [--max-rounds N]"
---

# ao-flow：pi 执行 + delegate 评审 + 回传修复的无人值守闭环

驱动者是这个会话本身（Claude）。用户只发一次指令，全程零参与；用户随时按 Esc 或直接打字打断。本 skill 是执行协议，照步骤走，不要反问用户。

## 0. 前置检查（每次先跑）

```bash
ao status | head -3        # 非 ready 则启动：
nohup '/Applications/Agent Orchestrator.app/Contents/Resources/daemon/ao' daemon > ~/.ao/daemon-standalone.log 2>&1 &
# 启动后 sleep 6 再 ao status 确认 ready
```

参数默认值（用户没说就用这些）：

| 参数 | 默认 | 说明 |
|---|---|---|
| project | 已注册项目的，从 cwd 推断；否则问一次用户 | `ao project ls` 查 |
| model | `group/free` | magpie 免费池；用户点名则用 `commandcode-plan/xai/grok-4.7` 等 |
| max-rounds | 2 | 评审-修复循环上限，超过即冻结升级用户 |
| timeout | 单轮 15min | worker 卡住的熔断线 |

## 1. 派发（每任务一个 session）

```bash
ao spawn --project <proj> --harness pi --model <model> --name '<任务短名>' \
  --output artifact --prompt '<完整任务描述：目标+涉及文件+验收命令+禁区>'
```

- prompt 必须含**验收命令**（如 `node test.js` / `npm test`），没有可判定验收的任务先补一个再派。
- 多任务：逐个 spawn（session 名不重复），互不依赖就并行等。
- 报错 `DEFAULT_BRANCH_UNRESOLVED`：repo 无 remote。修复：`cd <repo> && git remote add origin . && git update-ref refs/remotes/origin/<主分支> refs/heads/<主分支>`，重试 spawn。

**spawn 后 worker 不会自动开干**，推一把：

```bash
ao send --session <sid> --message '开始执行上述任务。'
```

## 2. 等待完成（轮询，可被 Esc 打断）

```bash
until [ "$(ao session get <sid> 2>/dev/null | grep -c 'status: idle')" = "1" ]; do sleep 5; done
```

带熔断（推荐写法，Bash 工具 timeout 设 900000）：

```bash
n=0; until [ "$(ao session get <sid> 2>/dev/null | grep -c 'status: idle')" = "1" ]; do
  sleep 10; n=$((n+90)); [ $n -ge 900 ] && break
done
```

超时未完成：`ao send --session <sid> --message '汇报当前进度和阻塞点'`，按汇报决定继续等或 kill 重派。

## 3. 找 worktree、验产物、提交

每个 session 独立 worktree（**别假设路径，先找**）：

```bash
WT=$(find ~/.ao/data/worktrees/<proj> -name '<主文件名>' | head -1 | xargs dirname)
# 或从 ao session get <sid> 的 branch 字段推
cd "$WT" && <验收命令>            # 红了直接进第 5 步把报错回传
git add -A && git commit -qm 'feat: <改动摘要> (by pi <sid>)'
```

验收失败 = 不用等评审，直接把 stderr 回传 worker 修，回到第 2 步。

## 4. 评审（宿主 agent 代跑 ocr delegate）

```bash
cd "$WT"
ocr delegate preview --format json --from HEAD~1 --to HEAD   # 或 --commit <hash>
ocr delegate rule --format json <file1> <file2> ...
git --no-pager diff --no-ext-diff --no-textconv --no-color HEAD~1..HEAD -- "<path>"
```

注意：已 commit 的产物必须用 range/commit 模式，workspace 模式返回空。

然后**自己完成评审推理**（这就是 delegate 模式）：对每个 reviewable 文件，对照 rule 组 checklist（死代码/硬编码/严格相等/空值检查/异步错误处理/安全项等）逐条过 diff 的新增行。输出结构化 findings：

| 字段 | 值 |
|---|---|
| path / line | 文件 + 新文件行号 |
| severity | High（明显 bug/安全/数据丢失）/ Medium（性能/错误处理缺口）/ Low（nit，静默丢弃） |
| fix | 具体修复建议（可执行的，不是"建议改进"） |

覆盖强制：preview 列出的每个 `(path, status)` 必须标记 reviewed 或 skipped（带原因），不许静默漏文件。

## 5. 回传修复（发给原 session，不开新 worker）

```bash
ao send --session <sid> --message '代码评审发现 N 个问题：
1. [High] <path>:<line> <问题> —— <fix>
2. [Medium] ...
请逐条修复，不要改动无关代码。改完跑 <验收命令> 确认通过。'
```

回到第 2 步等完成 → 第 3 步提交 → 第 4 步二审。**High/Medium 全清或到 max-rounds 上限**即收敛；到上限仍有 High 未解 → 冻结，向用户汇报剩余 findings 和现场位置。

## 6. 收尾

```bash
ao session kill <sid>
```

汇报格式：每任务一行（session、分支、几轮评审、结果），失败/冻结的单独说明。全链产物留在 worktree（用户 repo 本体始终未被触碰，合并与否用户自己定）。

## 速查：一句话触发词

- "把 X 交给 pi 做并评审修复" → 本 skill 全程
- 只审不修：跳到第 4 步，findings 汇报给用户
- 并行 N 任务：第 1 步 spawn N 个，第 2 步轮询全部，其余流程不变
