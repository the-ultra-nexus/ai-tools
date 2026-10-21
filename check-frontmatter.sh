#!/usr/bin/env bash
# 校验 skills/*/SKILL.md 的 YAML frontmatter：必须含 name/description，且能被 YAML 解析。
# 未加引号的 description 里含 ": "（如查询操作符 site:/after:）会让 YAML 报
# "Nested mappings are not allowed in compact mappings"，pi 加载时直接丢弃该 skill。
# exit code 1 表示有不合法文件（供 git pre-commit hook 使用）。
set -uo pipefail
REPO="$(cd "$(dirname "$0")" && pwd)"
fail=0
for f in "$REPO"/skills/*/SKILL.md; do
  [ -e "$f" ] || continue
  out="$(python3 - "$f" <<'PY'
import re, sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
if not m:
    print("无 frontmatter（缺少 --- 包裹）")
    sys.exit(1)
try:
    import yaml
except ImportError:            # 无 PyYAML 时退化为裸解析检查
    print("跳过：未安装 PyYAML，仅检查字段存在")
    for k in ("name", "description"):
        if not re.search(rf"^{k}:\s*\S", m.group(1), re.M):
            print(f"frontmatter 缺少 {k}")
            sys.exit(1)
    sys.exit(0)
data = yaml.safe_load(m.group(1))
if not isinstance(data, dict):
    print("frontmatter 不是 mapping")
    sys.exit(1)
bad = False
for k in ("name", "description"):
    if not isinstance(data.get(k), str) or not data[k].strip():
        print(f"frontmatter 缺少或为空：{k}")
        bad = True
sys.exit(1 if bad else 0)
PY
)"
  if [ $? -ne 0 ]; then
    echo "FAIL ${f#$REPO/}"
    [ -n "$out" ] && echo "     $out" | sed 's/^/     /'
    fail=1
  fi
done
if [ "$fail" -ne 0 ]; then
  cat <<'TIP'

提示：description 未加引号、且含 "冒号+空格" 时 YAML 会解析失败（Nested mappings）。
把它改成单引号包裹：description: '... site:/after: ...'
TIP
fi
exit $fail
