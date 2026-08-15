#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path

PLACEHOLDERS = {
    "__BROWSE_HASH__": "BrowsePage_AllDirectories",
    "__DIRECTORY_HASH__": "DirectoryPage_Game",
    "__CHANNEL_HASH__": "ChannelShell",
    "__METADATA_HASH__": "StreamMetadata",
}

def read(path: Path):
    if not path.exists():
        raise SystemExit(f"❌ 找不到文件：{path}")
    return path.read_text(encoding="utf-8")

def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("--hashes", required=True)
    parser.add_argument("--template", required=True)
    args = parser.parse_args()

    source = Path(args.source).resolve()
    hashes = json.loads(Path(args.hashes).read_text(encoding="utf-8"))
    template = Path(args.template).read_text(encoding="utf-8")

    for placeholder, operation in PLACEHOLDERS.items():
        value = hashes.get(operation)
        if not value or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise SystemExit(f"❌ Twitch hash 无效：{operation}")
        template = template.replace(placeholder, value)

    if re.search(r"__[A-Z_]+HASH__", template):
        raise SystemExit("❌ TwitchSite 仍有 hash 占位符")

    write(source / "lib/core/site/twitch_site.dart", template)
    print("✅ 生成 twitch_site.dart（无 Twitch 弹幕网络）")

    # Sites
    path = source / "lib/core/sites.dart"
    text = read(path)

    import_line = "import 'package:pure_live/core/site/twitch_site.dart';\n"
    if import_line not in text:
        marker = "import 'package:pure_live/core/site/kuaishou_site.dart';\n"
        if marker not in text:
            raise SystemExit("❌ sites.dart import 结构变化")
        text = text.replace(marker, marker + import_line, 1)

    const_line = '  static const String twitchSite = "twitch";\n'
    if const_line not in text:
        marker = '  static const String iptvSite = "iptv";\n'
        if marker not in text:
            raise SystemExit("❌ sites.dart 常量结构变化")
        text = text.replace(marker, marker + const_line, 1)

    if 'id: "twitch"' not in text:
        marker = (
            '    Site(id: "iptv", name: i18n("site_iptv"), '
            'logo: "assets/images/logo.png", liveSite: IptvSite()),\n'
        )
        if marker not in text:
            raise SystemExit("❌ sites.dart supportSites 结构变化")
        twitch_line = (
            '    Site(id: "twitch", name: "Twitch", '
            'logo: "assets/images/logo.png", liveSite: TwitchSite()),\n'
        )
        text = text.replace(marker, twitch_line + marker, 1)

    write(path, text)
    print("✅ 注册 Twitch 平台")

    # URL parser
    path = source / "lib/common/utils/live_url_tool.dart"
    text = read(path)

    if "Sites.twitchSite" not in text:
        marker = "    // 网易CC\n"
        if marker not in text:
            raise SystemExit("❌ LiveUrlTool 结构变化")

        block = r'''    // Twitch
    if (realUrl.toLowerCase().contains("twitch.tv")) {
      try {
        var twitchUrl = realUrl.split("?").first.trimEndChar('/');

        if (!twitchUrl.startsWith("http://") &&
            !twitchUrl.startsWith("https://")) {
          twitchUrl = "https://$twitchUrl";
        }

        final uri = Uri.parse(twitchUrl);
        final host = uri.host.toLowerCase();

        if (host != "twitch.tv" &&
            host != "www.twitch.tv" &&
            host != "m.twitch.tv") {
          return [];
        }

        final segments =
            uri.pathSegments.where((e) => e.trim().isNotEmpty).toList();

        if (segments.isEmpty) {
          return [];
        }

        final login = segments.first.trim();

        const reservedPaths = {
          "directory",
          "videos",
          "downloads",
          "settings",
          "subscriptions",
          "inventory",
          "wallet",
          "search",
          "drops",
          "turbo",
          "prime",
          "store",
          "jobs",
          "p",
        };

        if (login.isEmpty ||
            reservedPaths.contains(login.toLowerCase())) {
          return [];
        }

        return [login, Sites.twitchSite];
      } catch (_) {
        return [];
      }
    }

'''
        text = text.replace(marker, block + marker, 1)

    write(path, text)
    print("✅ Twitch 链接解析")

    # Clipboard
    path = source / "lib/modules/toolbox/toolbox_controller.dart"
    text = read(path)

    if "twitch\\\\.tv" not in text:
        old = (
            'RegExp(r"bilibili|huya|douyu|douyin|kuaishou|163")'
            '.hasMatch(text)'
        )
        new = (
            'RegExp('
            'r"bilibili|huya|douyu|douyin|kuaishou|163|twitch\\\\.tv", '
            'caseSensitive: false'
            ').hasMatch(text)'
        )
        if old not in text:
            raise SystemExit("❌ ToolBoxController 结构变化")
        text = text.replace(old, new, 1)

    write(path, text)
    print("✅ 剪贴板识别 Twitch")

    # Search UI: Pure uses web search here
    path = source / "lib/modules/search/search_controller.dart"
    text = read(path)

    if "case Sites.twitchSite:" not in text:
        marker = "      default:\n"
        if marker not in text:
            raise SystemExit("❌ SearchController switch 结构变化")
        block = (
            "      case Sites.twitchSite:\n"
            '        return "https://www.twitch.tv/search?term=$q";\n'
        )
        text = text.replace(marker, block + marker, 1)

    write(path, text)
    print("✅ Pure 搜索页使用 Twitch 官方搜索")

    # LivePlay: disable Twitch danmaku start; noop object still handles init/switch safely
    path = source / "lib/modules/live_play/controllers/live_play_controller.dart"
    text = read(path)

    old_except = (
        "const except = "
        "[Sites.kuaishouSite, Sites.iptvSite, Sites.ccSite];"
    )
    new_except = (
        "const except = "
        "[Sites.kuaishouSite, Sites.iptvSite, Sites.ccSite, Sites.twitchSite];"
    )
    if new_except not in text:
        if old_except not in text:
            raise SystemExit("❌ LivePlayController 弹幕排除列表结构变化")
        text = text.replace(old_except, new_except, 1)

    if "case Sites.twitchSite:" not in text:
        marker = "      case Sites.kuaishouSite:\n"
        if marker not in text:
            raise SystemExit("❌ LivePlayController openNaviteAPP 结构变化")
        block = (
            "      case Sites.twitchSite:\n"
            '        nativeUrl = "https://www.twitch.tv/${detail.roomId}";\n'
            '        webUrl = "https://www.twitch.tv/${detail.roomId}";\n'
            "        break;\n"
        )
        text = text.replace(marker, block + marker, 1)

    write(path, text)
    print("✅ Twitch 实际弹幕连接禁用")
    print("✅ Twitch 官方网页跳转加入")

    # Player HLS headers
    path = source / "lib/modules/live_play/controllers/player_controller.dart"
    text = read(path)

    if "currentSite.id == Sites.twitchSite" not in text:
        marker = "    } else if (currentSite.id == Sites.iptvSite) {\n"
        if marker not in text:
            raise SystemExit("❌ PlayerController getHeaders 结构变化")

        block = (
            "    } else if (currentSite.id == Sites.twitchSite) {\n"
            "      headers = {\n"
            '        "user-agent":\n'
            '            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) '
            'Gecko/20100101 Firefox/115.0",\n'
            '        "accept-language": "en-US",\n'
            '        "origin": "https://www.twitch.tv",\n'
            '        "referer": "https://www.twitch.tv/",\n'
            '        "client-id": "kimne78kx3ncx6brgo4mv6wki5h1ko",\n'
            "      };\n"
        )

        text = text.replace(marker, block + marker, 1)

    write(path, text)
    print("✅ Twitch HLS 请求头加入播放器")

    checks = {
        "TwitchSite":
            (source / "lib/core/site/twitch_site.dart").exists(),
        "Sites":
            'static const String twitchSite = "twitch";' in read(source / "lib/core/sites.dart"),
        "URL":
            "Sites.twitchSite" in read(source / "lib/common/utils/live_url_tool.dart"),
        "Search":
            "case Sites.twitchSite:" in read(source / "lib/modules/search/search_controller.dart"),
        "DanmakuExcept":
            "Sites.twitchSite" in read(source / "lib/modules/live_play/controllers/live_play_controller.dart"),
        "PlayerHeader":
            "currentSite.id == Sites.twitchSite" in read(source / "lib/modules/live_play/controllers/player_controller.dart"),
    }

    failed = [key for key, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("❌ Twitch 注入验证失败：" + ", ".join(failed))

    print("======================================")
    print("✅ Twitch V4 注入完成")
    print("======================================")

if __name__ == "__main__":
    main()
