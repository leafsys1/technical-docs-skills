#!/usr/bin/env python3
"""Offline Markdown integrity hints. Never runs document commands or rewrites files."""
import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)\s*#*\s*$")
LINK_START = re.compile(r"!?\[[^\]\n]*\]\(")
REFERENCE_DEF = re.compile(r"^ {0,3}\[([^\]]+)\]:\s*(.*)$")
REFERENCE_USE = re.compile(r"!?\[[^\]\n]+\]\[([^\]\n]+)\]")
INLINE_CODE = re.compile(r"(`+).*?\1")
UNFINISHED = re.compile(r"\b(?:TODO|TBD)\b|【待补[^】]*】|\{\{[^}]+\}\}")


def target_at(text, start=0):
    """Read one inline/reference target, including escaped or nested parentheses."""
    i = start
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text):
        return ""
    if text[i] == "<":
        end = text.find(">", i + 1)
        return text[i + 1:end] if end >= 0 else ""
    result, depth = [], 0
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text):
            result.append(text[i + 1])
            i += 2
            continue
        if c.isspace() and depth == 0:
            break
        if c == ")":
            if depth == 0:
                break
            depth -= 1
        elif c == "(":
            depth += 1
        result.append(c)
        i += 1
    return "".join(result)


def check_document(filename, *, root=None, release=False, style=False):
    path = Path(filename)
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    findings, prose, links = [], [], []
    counts = {"local_links_checked": 0, "remote_links_not_checked": 0,
              "absolute_or_site_links_not_checked": 0, "code_blocks": 0}

    def add(level, code, line, message):
        findings.append({"level": level, "code": code, "line": line, "message": message})

    opened = None
    previous_heading = 0
    h1_count = 0
    in_frontmatter = bool(len(lines) > 1 and lines[0].strip() == "---"
                          and re.match(r"^[A-Za-z_][\w-]*\s*:", lines[1]))
    for number, line in enumerate(lines, 1):
        if in_frontmatter:
            if number > 1 and line.strip() in ("---", "..."):
                in_frontmatter = False
            continue
        fence = FENCE.match(line)
        if opened:
            marker, length, start, language = opened
            if (fence and fence[1][0] == marker and len(fence[1]) >= length
                    and not fence[2].strip()):
                opened = None
            elif language in ("bash", "sh", "shell", "zsh"):
                if re.match(r"^\s*\$\s+\S", line):
                    add("warning", "shell-prompt", number, "命令带终端提示符，复制前需确认。")
                if re.search(r"<(?:HOST|IP|PORT|PATH|MODEL|USER|TOKEN)[A-Z_0-9]*>", line):
                    add("warning", "shell-placeholder", number, "尖括号占位符可能被 Shell 解释为重定向。")
            continue
        if fence and (fence[1][0] != "`" or "`" not in fence[2]):
            language = fence[2].strip().split(maxsplit=1)[0] if fence[2].strip() else ""
            opened = (fence[1][0], len(fence[1]), number, language)
            counts["code_blocks"] += 1
            if not language:
                add("warning", "fence-language", number, "代码块未标语言；纯输出可标 text。")
            continue
        # Code and URLs are not prose and must not be edited by a style checker.
        visible = INLINE_CODE.sub("", line)
        prose.append((number, visible))
        heading = HEADING.match(visible)
        if heading:
            level = len(heading[1])
            if previous_heading and level > previous_heading + 1:
                add("warning", "heading-jump", number, "标题层级跳级，需人工确认目录结构。")
            previous_heading = level
            if level == 1:
                h1_count += 1
                if h1_count > 1:
                    add("warning", "multiple-h1", number, "出现多个主标题，需确认是否为同一交付件。")
        if UNFINISHED.search(visible):
            add("error" if release else "warning", "unfinished-slot", number,
                "发现未填槽位；正式交付前需填写，或明确作为示例/限制说明。")
        if style and re.search(r"值得注意的是|让我们来看看|综上所述|无缝赋能|强大而灵活", visible):
            add("warning", "style-candidate", number, "疑似低信息表达，仅提示人工判断，不判定作者身份。")

    if opened:
        add("error", "unclosed-fence", opened[2], "代码围栏未关闭；标记数量为偶数不能排除该问题。")
    if in_frontmatter:
        add("error", "unclosed-frontmatter", 1, "文档头部元数据未关闭。")

    definitions = {}
    for number, line in prose:
        definition = REFERENCE_DEF.match(line)
        if definition:
            definitions[definition[1].casefold()] = target_at(definition[2])
            continue
        for match in LINK_START.finditer(line):
            target = target_at(line, match.end())
            if target:
                links.append((number, target))
        for match in REFERENCE_USE.finditer(line):
            links.append((number, ("reference", match[1].casefold())))
    for number, target in links:
        if isinstance(target, tuple):
            key = target[1]
            if key not in definitions:
                add("warning", "reference-undefined", number, "引用式链接缺少定义。")
                continue
            target = definitions[key]
        if not target or target.startswith("#"):
            continue
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            counts["remote_links_not_checked"] += 1
            continue
        location = unquote(parsed.path)
        if not location:
            continue
        if location.startswith(("/", "\\")):
            counts["absolute_or_site_links_not_checked"] += 1
            continue
        artifact = (path.parent / location).resolve()
        if root is not None and not artifact.is_relative_to(Path(root).resolve()):
            add("error", "artifact-outside-root", number, "相对工件指向交付根目录之外，无法保证交付后可访问。")
            continue
        counts["local_links_checked"] += 1
        if not artifact.exists():
            add("error", "missing-artifact", number, "相对链接指向的本地文件或目录不存在。")

    for number, line in enumerate(lines, 1):
        if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", line):
            add("warning", "private-key-marker", number, "出现私钥格式标识；人工确认并移除真实凭据，勿复述其值。")
    errors = sum(x["level"] == "error" for x in findings)
    return {"file": str(path), "scope": "offline-markdown-integrity", "structural_checks_ok": errors == 0,
            "errors": errors, "warnings": len(findings) - errors, "findings": findings,
            **counts, "commands_executed": False, "renderer_used": False,
            "limits": ["不验证事实、版本接口、真实命令或复现结论", "不访问外部链接或核对标题锚点",
                       "支持常见围栏和 Markdown 链接；复杂容器、HTML、布局及最终载体仍需实际渲染"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+")
    parser.add_argument("--root", type=Path, help="已确定的交付根目录；相对工件不得越界")
    parser.add_argument("--release", action="store_true", help="将正文未填槽位作为结构交付错误")
    parser.add_argument("--style", action="store_true", help="提示少量候选表达，不自动修改或判定 AI 作者")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        reports = [check_document(p, root=args.root, release=args.release, style=args.style) for p in args.files]
    except (OSError, UnicodeError, ValueError) as error:
        print("无法读取或检查输入：" + type(error).__name__, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"reports": reports}, ensure_ascii=False, indent=2))
    else:
        for report in reports:
            print(f"{report['file']}: {report['errors']} 项结构错误，{report['warnings']} 项待复核提示")
            for item in report["findings"]:
                print(f"  {item['line']}: {item['level']} {item['code']} — {item['message']}")
        print("仅完成离线结构/工件检查；未验证事实、命令执行、实际渲染或复现。")
    return 1 if any(r["errors"] for r in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
