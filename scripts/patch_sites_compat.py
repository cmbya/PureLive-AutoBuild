#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import sys


EXACT_IPTV_LINE = (
    '    Site(id: "iptv", '
    'name: i18n("site_iptv"), '
    'logo: "assets/images/logo.png", '
    'liveSite: IptvSite()),\n'
)


def find_matching_paren(text: str, open_pos: int) -> int:
    depth = 0
    quote = None
    escaped = False

    for i in range(open_pos, len(text)):
        ch = text[i]

        if quote is not None:
            if escaped:
                escaped = False
                continue

            if ch == "\\":
                escaped = True
                continue

            if ch == quote:
                quote = None

            continue

        if ch in ("'", '"'):
            quote = ch
            continue

        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1

            if depth == 0:
                return i

    return -1


def find_support_sites_region(text: str) -> tuple[int, int]:
    match = re.search(
        r"static\s+List(?:\s*<\s*Site\s*>)?\s+"
        r"get\s+supportSites\s*=>\s*\[",
        text,
    )

    if not match:
        raise SystemExit(
            "❌ 找不到 Sites.supportSites 声明。"
            "Pure Live 上游结构再次发生变化。"
        )

    start = match.end()

    close = re.search(
        r"(?m)^[ \t]*\];",
        text[start:],
    )

    if not close:
        raise SystemExit(
            "❌ 找到 supportSites，但找不到结束的 ];"
        )

    end = start + close.start()
    return start, end


def find_site_call(
    text: str,
    region_start: int,
    region_end: int,
    site_id: str,
) -> tuple[int, int] | None:
    cursor = region_start

    while True:
        site_pos = text.find(
            "Site(",
            cursor,
            region_end,
        )

        if site_pos < 0:
            return None

        open_pos = site_pos + len("Site")

        close_pos = find_matching_paren(
            text,
            open_pos,
        )

        if close_pos < 0 or close_pos >= region_end:
            raise SystemExit(
                "❌ supportSites 中发现 Site(，"
                "但括号无法正确匹配。"
            )

        block = text[
            site_pos:
            close_pos + 1
        ]

        if re.search(
            rf"\bid\s*:\s*['\"]{re.escape(site_id)}['\"]",
            block,
        ):
            line_start = text.rfind(
                "\n",
                region_start,
                site_pos,
            )

            if line_start < 0:
                line_start = site_pos
            else:
                line_start += 1

            end = close_pos + 1

            while end < len(text) and text[end] in " \t":
                end += 1

            if end < len(text) and text[end] == ",":
                end += 1

            while end < len(text) and text[end] in " \t":
                end += 1

            if text.startswith("\r\n", end):
                end += 2
            elif end < len(text) and text[end] == "\n":
                end += 1

            return line_start, end

        cursor = close_pos + 1


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "用法：python3 scripts/patch_sites_compat.py source"
        )

    root = Path(sys.argv[1])
    path = root / "lib/core/sites.dart"

    if not path.exists():
        raise SystemExit(
            f"❌ 找不到 {path}"
        )

    original = path.read_text(
        encoding="utf-8",
    )

    text = original.replace(
        "\r\n",
        "\n",
    )

    region_start, region_end = find_support_sites_region(
        text
    )

    if EXACT_IPTV_LINE in text[
        region_start:
        region_end
    ]:
        print(
            "✅ sites.dart IPTV 锚点已经兼容，"
            "无需修改"
        )
    else:
        found = find_site_call(
            text,
            region_start,
            region_end,
            "iptv",
        )

        if found is None:
            preview = text[
                region_start:
                min(
                    region_end,
                    region_start + 1800,
                )
            ]

            print("")
            print(
                "========== supportSites 当前内容 =========="
            )
            print(preview)
            print(
                "=========================================="
            )
            print("")

            raise SystemExit(
                '❌ 找到了 supportSites，但找不到 '
                'id: "iptv" 的 Site(...)。'
            )

        start, end = found
        old_block = text[
            start:
            end
        ].rstrip()

        print(
            "ℹ️ Pure Live 新版 IPTV Site 结构："
        )
        print(old_block)

        text = (
            text[:start]
            + EXACT_IPTV_LINE
            + text[end:]
        )

        print(
            "✅ 已把 IPTV Site 规范为 Twitch/SOOP "
            "旧补丁可识别的兼容锚点"
        )

    if (
        "import 'package:pure_live/core/site/kuaishou_site.dart';"
        not in text
    ):
        raise SystemExit(
            "❌ kuaishou_site.dart import 锚点也发生变化，"
            "停止以避免错误修改。"
        )

    if not re.search(
        r"static\s+const\s+String\s+iptvSite\s*=\s*"
        r"['\"]iptv['\"]\s*;",
        text,
    ):
        raise SystemExit(
            "❌ iptvSite 常量锚点也发生变化，"
            "停止以避免错误修改。"
        )

    new_start, new_end = find_support_sites_region(
        text
    )

    if EXACT_IPTV_LINE not in text[
        new_start:
        new_end
    ]:
        raise SystemExit(
            "❌ IPTV 兼容锚点写入后校验失败。"
        )

    path.write_text(
        text,
        encoding="utf-8",
    )

    print("")
    print(
        "=========================================="
    )
    print(
        "✅ Pure Live 2.1.1 sites.dart 兼容处理完成"
    )
    print(
        "✅ 接下来可继续运行现有 patch_twitch.py"
    )
    print(
        "✅ SOOP 如仍使用 IPTV 锚点也可继续复用"
    )
    print(
        "=========================================="
    )


if __name__ == "__main__":
    main()
