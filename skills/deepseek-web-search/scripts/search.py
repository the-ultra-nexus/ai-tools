#!/usr/bin/env python3
"""DeepSeek 联网搜索 API 客户端（纯标准库）。

文档：https://api-docs.deepseek.com/guides/search
凭证：环境变量 DEEPSEEK_API_KEY

示例:
    python3 search.py "DeepSeek V4 发布"
    python3 search.py "site:github.com OR site:huggingface.co lang:en after:2025" -c 20
    python3 search.py "DeepSeek 财报" --need-content --ori-question "DeepSeek 去年营收多少"
"""
import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request

API_URL = "https://api.deepseek.com/v1/tools/search"
SUMMARY_LIMIT = 1000
CONTENT_LIMIT = 1000
HINTS = {
    401: "API Key 缺失或无效。到 https://platform.deepseek.com 获取后设置 DEEPSEEK_API_KEY。",
    402: "账户余额不足，充值后重试：https://platform.deepseek.com/top_up",
    408: "读取请求体超时，稍等后重试。",
    429: "超出账户级 QPS 限制（搜索 100 QPS，多 key 共享配额），退避几秒后重试。",
    500: "服务端内部错误，稍后重试。",
    504: "下游超时，稍后重试。",
}


def build_body(args):
    body = {"query": args.query, "count": args.count}
    if args.need_content:
        body["need_content"] = True
    if args.ori_question:
        body["ori_question"] = args.ori_question
    return body


def search(body, api_key):
    def build():
        # shortcut: urlopen 失败会把代理地址缓存进 req.host，复用对象会导致绕代理重试仍连死代理；重试必须新建
        return urllib.request.Request(
            API_URL,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

    try:
        with urllib.request.urlopen(build(), timeout=30) as resp:
            return json.load(resp)
    except urllib.error.URLError as exc:
        # shortcut: URLError 可能只是代理挂了；用空代理 opener 直连重试一次，不行才报错
        if not isinstance(exc, urllib.error.HTTPError) and urllib.request.getproxies():
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(build(), timeout=30) as resp:
                return json.load(resp)
        raise


def format_output(results, need_content):
    lines = [f"结果数: {len(results)}", ""]
    for i, item in enumerate(results, 1):
        lines.append(f"[{i}] {item.get('title') or '(无标题)'}")
        meta = []
        if item.get("date"):
            meta.append(item["date"][:10])
        if item.get("site_name"):
            meta.append(item["site_name"])
        authority = item.get("authority")
        if isinstance(authority, int) and authority >= 0:
            meta.append(f"权威 {authority}")
        score = item.get("rerank_score")
        if isinstance(score, (int, float)):
            meta.append(f"相关 {score:.2f}")
        if meta:
            lines.append("    " + " | ".join(meta))
        if item.get("url"):
            lines.append(f"    {item['url']}")
        summary = item.get("summary") or item.get("snippet") or ""
        if summary:
            lines.append("    " + summary[:SUMMARY_LIMIT].replace("\n", " "))
        if need_content and item.get("content"):
            lines.append("    --- 正文 ---")
            lines.append("    " + item["content"][:CONTENT_LIMIT].replace("\n", " "))
        lines.append("")
    return "\n".join(lines)


def fail(message, hint=""):
    print(f"Error: {message}", file=sys.stderr)
    if hint:
        print(hint, file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="DeepSeek 联网搜索 API\nhttps://api-docs.deepseek.com/guides/search"
    )
    parser.add_argument("query", help="搜索词，1~128 字符，支持 site:/lang:/after: 等操作符")
    parser.add_argument("--count", "-c", type=int, default=10, help="返回条数，1~50，默认 10")
    parser.add_argument("--need-content", action="store_true", help="同时返回网页正文")
    parser.add_argument("--ori-question", help="触发搜索的原始问题，1~128 字符，帮助理解意图")
    args = parser.parse_args()

    query = args.query.strip()
    if not query:
        fail("搜索词不能为空。")
    if len(query) > 128:
        fail(f"搜索词 {len(query)} 字符，超过 128 上限，请精简后重试。")
    if not 1 <= args.count <= 50:
        fail(f"--count 需在 1~50 之间，当前 {args.count}。")
    if args.ori_question and len(args.ori_question) > 128:
        fail("--ori-question 超过 128 字符。")

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key and sys.stdin.isatty():
        api_key = getpass.getpass("DEEPSEEK_API_KEY: ").strip()
    if not api_key:
        fail("未设置 DEEPSEEK_API_KEY。", HINTS[401])

    try:
        data = search(build_body(args), api_key)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            message = json.loads(raw)["error"]["message"]
        except Exception:
            message = raw[:500] or str(exc)
        fail(f"HTTP {exc.code}: {message}", HINTS.get(exc.code, "修改请求后重试，不要原样重试。"))
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        fail(f"网络错误: {reason}", "检查网络；已尝试绕过代理直连仍失败，请确认代理设置（http_proxy/https_proxy）与网络可用。")

    results = data.get("results") or []
    if not results:
        print("结果数: 0\n\n没有匹配的网页。精简查询词或放宽操作符后重试。")
        return
    print(format_output(results, args.need_content))


if __name__ == "__main__":
    main()
