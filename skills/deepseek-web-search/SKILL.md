---
name: deepseek-web-search
description: DeepSeek 联网搜索 API（/v1/tools/search），返回带 rerank_score、authority、date 加权的网页结果，支持 site:/lang:/after: 等查询操作符。需要联网事实、时效信息、出处求证时使用。凭证为环境变量 DEEPSEEK_API_KEY。收费 API（$0.75/千次成功请求，仅 HTTP 200 且结果非空才计费），账户级 100 QPS 限流。
argument-hint: "<查询词> [-c N] [--need-content] [--ori-question <原始问题>]"
---

# DeepSeek Web Search

官方文档：https://api-docs.deepseek.com/guides/search

## 1. 用法

```bash
python3 scripts/search.py "查询词" [-c 10] [--need-content] [--ori-question "..."]
```

文中的 `scripts/search.py` 均指本文件同目录下的 `scripts/search.py`。

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `query` | ✅ | — | 1~128 字符，不能全空白，支持操作符 |
| `--count` / `-c` | | `10` | 1~50 |
| `--need-content` | | off | 返回网页正文到 `content`，关闭时 `content` 恒为空 |
| `--ori-question` | | — | 触发搜索的原始问题（1~128 字符），帮服务理解意图 |

脚本用纯标准库，无第三方依赖。stdout 只出结果，stderr 出错误，退出码 0/1。

## 2. 查询操作符

query 原样转发给搜索引擎，操作符可组合：

| 操作符 | 示例 | 作用 |
|---|---|---|
| `site:` | `DeepSeek site:github.com` | 限定站点；多站点用 `site:a OR site:b` |
| `-site:` | `-site:example.com` | 排除站点，多个用空格分隔 |
| `-` | `-advertisement` | 排除含该词的页面 |
| `-"..."` | `-"release notes"` | 排除含该短语的页面 |
| `"..."` | `"exact phrase"` | 精确短语匹配 |
| `lang:` | `lang:zh,en` | 限定语言，逗号分隔 |
| `after:` | `after:2025` / `after:2025-01-01` | 限定发布时间下限 |
| `before:` | `before:2026-06-01` | 限定发布时间上限 |

## 3. 结果解读

每条结果含 `title`、`url`、`snippet`、`summary`、`content`、`site_name`、`date`、`authority`、`rerank_score`。

- `rerank_score`（0~3）：综合相关性、权威度、时效的排序分，**≥1.5 视为高质量**。
- `authority`（0~4，-1 未知）：**≥3 为高权威来源**。
- `summary` 约 600~800 字，给模型读；`snippet` 约 100~200 字，给 UI 展示。引用时优先用 `summary`。
- 引用给 `title` + `url`，需要权威背书时优先选 `authority ≥ 3` 的结果。

## 4. 何时搜、何时不搜

搜索：涉及现实世界事实（人物、事件、数据、政策、产品、价格）、用户问「最新/今天/最近」、要求出处或求证、对某实体置信度不足。

不搜索：纯数学与逻辑推理、编程语法、广泛已知常识、用户明确说「不要搜」、纯创意写作、闲聊。

结果不够好时的升级顺序：精简到核心实体词 → 加操作符（`site:` / `after:`）→ 换英文关键词 → `--need-content` 取正文。连续 2~3 次仍不理想，直接说明证据不足，不要编造。

## 5. 限流

账户级 **100 QPS**（Search），与 Fetch 的 25 QPS 相互独立；**多个 API key 共享同一账户配额**，也与模型并发限制无关。超限返回 **429**，退避几秒后重试即可，不要连续猛打。

## 6. 错误处理

错误为 OpenAI 兼容格式，脚本会打印 `error.message` 并附处置提示。

| HTTP | 含义 | 处置 |
|---|---|---|
| 400 | 请求头/体非法，含字段值越界 | 改请求，不要原样重试 |
| 401 | Key 缺失或无效 | 到 https://platform.deepseek.com 取 key，设置 `DEEPSEEK_API_KEY` |
| 402 | 余额不足 | 充值后重试 |
| 408 / 429 / 5xx | 超时、限流、服务端错误 | 等待后重试 |
| 413 | 请求体过大 | 缩短 query / 减少参数 |

> 价格、限流、免费期都可能调整，以官方文档为准；本节的数字写死于 2026-10，若与文档不符以文档为据。
