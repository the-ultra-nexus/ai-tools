#!/usr/bin/env python3
"""闪卡校验器 — 复刻 obsidian-spaced-repetition v1.15.4 的 parser 逻辑。

用法:
    python3 check-cards.py <文件.md> [更多.md ...]

退出码: 0 = 全绿, 1 = 有 ERROR, 2 = 只有 WARN

为什么需要它: parser 的三种失败模式都是「静默」的 —— 不报错、不生成卡，
只有 Obsidian 复习时才发现卡少了。这里提前抓出来。

复刻依据 (main.js):
  - parser(): 空行分支 `isEmptyLine && !options.multilineCardEndMarker`
  - QuestionTypeMultiLineBasic.expand(): side1 = slice(0, lineIdx(?))
  - QuestionTypeCloze: 除 ==挖空== 外文本两面共享
  - getQuestionContext(): 只收 fileCachedData.headings
  - determineQuestionTopicPathList(): 要求 topicPath.lineNum < question.firstLineNum
"""
import re
import sys

SINGLE_SEPARATORS = [(":::", "SingleLineReversed"), ("::", "SingleLineBasic")]
MULTILINE = "?"
MULTILINE_REVERSED = "??"
# 本库 data.json: multilineCardEndMarker = ""  → 任何空行都结束卡片
END_MARKER = ""


def is_cloze_line(line: str) -> bool:
    return bool(re.search(r"==[^=\n]+==", line))


def parse(text: str):
    """返回 [(card_type, card_text, first_line_idx, last_line_idx)]，1-based 行号另算。"""
    cards = []
    card_text = ""
    card_type = None
    first_line = 0
    lines = text.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        cur = lines[i]
        trimmed = cur.strip()

        # 跳过 HTML 注释（SR 注释除外，它属于上一张卡）
        if cur.startswith("<!--") and not cur.startswith("<!--SR:"):
            while i + 1 < len(lines) and "-->" not in cur:
                i += 1
            i += 1
            continue

        is_empty = len(trimmed) == 0
        has_end_marker = bool(END_MARKER) and trimmed == END_MARKER

        if (is_empty and not END_MARKER) or (is_empty and card_type is None) or has_end_marker:
            if card_type:
                cards.append((card_type, card_text.rstrip(), first_line, i - 1))
            card_type = None
            card_text = ""
            first_line = i + 1
            i += 1
            continue

        if card_text:
            card_text += "\n"
        card_text += cur.rstrip()

        for sep, ctype in SINGLE_SEPARATORS:
            if sep in cur:
                card_type = ctype
                break

        if card_type in ("SingleLineBasic", "SingleLineReversed"):
            card_text = cur
            first_line = i
            if i + 1 < len(lines) and lines[i + 1].startswith("<!--SR:"):
                card_text += "\n" + lines[i + 1]
                i += 1
            cards.append((card_type, card_text, first_line, i))
            card_type = None
            card_text = ""
        elif trimmed == MULTILINE:
            if len(card_text) > 1:
                card_type = "MultiLineBasic"
        elif trimmed == MULTILINE_REVERSED:
            if len(card_text) > 1:
                card_type = "MultiLineReversed"
        elif cur.startswith("```") or cur.startswith("~~~"):
            close = re.match(r"`+|~+", cur).group(0)
            while i + 1 < len(lines) and not lines[i + 1].startswith(close):
                i += 1
                card_text += "\n" + lines[i]
            card_text += "\n" + close
            i += 1
        elif card_type is None and is_cloze_line(cur):
            card_type = "Cloze"
        i += 1

    if card_type and card_text:
        cards.append((card_type, card_text.rstrip(), first_line, len(lines) - 1))
    return cards


def check(path: str):
    text = open(path, encoding="utf-8").read()
    lines = text.replace("\r\n", "\n").split("\n")
    cards = parse(text)
    errors, warns = [], []

    # 1. 基本计数
    sr_count = text.count("SR:")
    if not cards:
        errors.append("解析出 0 张卡 —— 检查 #flashcards 标签和卡型语法")

    headings = [
        (i + 1, l) for i, l in enumerate(lines) if re.match(r"^#{1,6} ", l)
    ]
    h1h2 = [(n, l) for n, l in headings if re.match(r"^#{1,2} ", l)]

    # 2. 逐卡检查
    for idx, (ctype, ctext, first, last) in enumerate(cards, 1):
        body = ctext.split("\n")
        front = body
        if ctype in ("MultiLineBasic", "MultiLineReversed"):
            sep_idxs = [j for j, l in enumerate(body) if l.strip() in ("?", "??")]
            if not sep_idxs:
                errors.append(f"卡{idx} (L{first + 1}): 多行卡找不到分隔符")
                continue
            front = body[: sep_idxs[0]]

        # 正面混入 heading → 会重复显示 + 进面包屑
        for l in front:
            if re.match(r"^#{1,6} ", l):
                errors.append(
                    f"卡{idx} (L{first + 1}): 正面混入 heading「{l[:40]}」"
                    f" → 会重复显示且进面包屑，应改正文行"
                )

        # 正面混入 #flashcards 标签 → 标签行被吃进卡文本
        for l in front:
            if l.strip().startswith("#flashcards"):
                errors.append(
                    f"卡{idx} (L{first + 1}): 正面混入标签行「{l.strip()[:40]}」"
                    f" → 标签须移到卡片起始行之前"
                )

        # Cloze 卡挂发音 → 两面都出，等于正面报答案
        if ctype == "Cloze":
            for l in body:
                if "==" not in l:
                    continue
                if re.search(r"\[[^\]]+\]\(https?://", l):
                    warns.append(
                        f"卡{idx} (L{first + 1}): Cloze 行含链接，两面都会显示，确认是否有意为之"
                    )
                # 先剥链接再查 IPA：URL 里的 /pronounce/ 会被音标正则误判
                bare = re.sub(r"\[[^\]]+\]\([^)]+\)", " ", l)
                # 斜杠内须含 IPA 专有字符（ˈ ˌ ə ɪ θ ð ʃ ʒ ŋ 等），避免匹配 URL 路径
                if re.search(r"/(?=[^/\s]*[ɪəʃθðˈˌŋʒɑɔʊɛæ])[^/\s]{1,30}/", bare):
                    warns.append(
                        f"卡{idx} (L{first + 1}): Cloze 行含 IPA，两面都会显示，确认是否有意为之"
                    )

    # 3. 孤儿分隔符：`?` 独立成行但没生成任何卡 → 正面与 ? 之间有空行（静默失败）
    sep_lines = [
        i + 1 for i, l in enumerate(lines) if l.strip() in (MULTILINE, MULTILINE_REVERSED)
    ]
    used_seps = set()
    for ctype, ctext, first, last in cards:
        if ctype in ("MultiLineBasic", "MultiLineReversed"):
            for ln in range(first + 1, last + 2):
                if ln in sep_lines:
                    used_seps.add(ln)
                    break
    for ln in sep_lines:
        if ln not in used_seps:
            errors.append(
                f"L{ln}: 孤儿分隔符「{lines[ln - 1].strip()}」—— 没生成任何卡。"
                f"最常见原因：正面正文行与分隔符之间有空行（空行清空 cardText，"
                f"分隔符就设不上卡型 → 该卡静默消失）"
            )

    # 4. 面包屑层含答案词嫌疑（无法自动判定，只提示人工核）
    if h1h2:
        warns.append(
            f"面包屑层 {len(h1h2)} 个 heading 会显示在每张卡上方，"
            f"人工确认措辞中性不含答案词"
        )

    # 5. 标签行位置：必须存在且位于卡片之前
    tag_lines = [
        (i + 1, l) for i, l in enumerate(lines) if l.strip().startswith("#flashcards")
    ]
    if not tag_lines:
        errors.append("找不到 #flashcards 标签行 —— 插件不会扫描此笔记")
    else:
        for card_idx, (ctype, ctext, first, last) in enumerate(cards, 1):
            if not any(tn < first + 1 for tn, _ in tag_lines):
                warns.append(
                    f"卡{card_idx} (L{first + 1}): 之前没有标签行 → 可能落入错误的牌组"
                )

    # 输出
    name = path.rsplit("/", 1)[-1]
    print(f"\n=== {name} ===")
    print(f"卡片 {len(cards)} 张 | SR 注释 {sr_count} 条 | heading {len(headings)} 个")
    by_type = {}
    for ctype, _, _, _ in cards:
        by_type[ctype] = by_type.get(ctype, 0) + 1
    if by_type:
        print("卡型: " + ", ".join(f"{k}×{v}" for k, v in sorted(by_type.items())))

    for e in errors:
        print(f"  ❌ {e}")
    for w in warns:
        print(f"  ⚠️  {w}")
    if not errors and not warns:
        print("  ✅ 全绿")
    elif not errors:
        print("  ✅ 无错误（有提示项）")
    return errors, warns


def main():
    paths = sys.argv[1:]
    if not paths:
        print(__doc__)
        return 2
    total_e = total_w = 0
    for p in paths:
        try:
            e, w = check(p)
        except FileNotFoundError:
            print(f"\n=== {p} ===\n  ❌ 文件不存在")
            total_e += 1
            continue
        total_e += len(e)
        total_w += len(w)
    print(f"\n汇总: {total_e} 个错误, {total_w} 个提示")
    return 1 if total_e else (2 if total_w else 0)


if __name__ == "__main__":
    sys.exit(main())
