#!/usr/bin/env python3
import argparse
import re
from pathlib import Path


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
    parser.add_argument("--template", required=True)
    parser.add_argument("--auth-page-template", required=True)
    args = parser.parse_args()

    source = Path(args.source).resolve()

    print("======================================")
    print("注入 SOOP V1")
    print("======================================")

    # 1. SOOP site
    template = Path(args.template).read_text(encoding="utf-8")
    site_path = source / "lib/core/site/soop_site.dart"
    write(site_path, template)
    print("✅ 生成 lib/core/site/soop_site.dart（无弹幕）")

    # 1.5 SOOP 登录 / Cookie 设置页
    auth_page = Path(args.auth_page_template).read_text(encoding="utf-8")
    auth_page_path = (
        source
        / "lib/modules/settings/pages/soop_account_settings_page.dart"
    )
    write(auth_page_path, auth_page)
    print("✅ 生成 SOOP 登录 / Cookie 设置页")

    # 1.6 CookieSettingsController 增加 soopCookie
    cookie_path = (
        source
        / "lib/common/services/settings/cookie_settings_controller.dart"
    )
    cookie_text = read(cookie_path)

    if "final RxString soopCookie" not in cookie_text:
        field_marker = (
            "  final RxString kuaishouCookie = "
            "hiveString('kuaishouCookie', '');\n"
        )
        if field_marker not in cookie_text:
            raise SystemExit(
                "❌ CookieSettingsController 字段结构变化"
            )
        cookie_text = cookie_text.replace(
            field_marker,
            field_marker
            + "  final RxString soopCookie = "
            "hiveString('soopCookie', '');\n",
            1,
        )

    if "soopCookie.v = '';" not in cookie_text:
        clear_marker = "    kuaishouCookie.v = '';\n"
        if clear_marker not in cookie_text:
            raise SystemExit(
                "❌ CookieSettingsController clearAllCookies 结构变化"
            )
        cookie_text = cookie_text.replace(
            clear_marker,
            clear_marker + "    soopCookie.v = '';\n",
            1,
        )

    if "'soopCookie': soopCookie.v" not in cookie_text:
        json_marker = (
            "      'kuaishouCookie': kuaishouCookie.v,\n"
        )
        if json_marker not in cookie_text:
            raise SystemExit(
                "❌ CookieSettingsController toJson 结构变化"
            )
        cookie_text = cookie_text.replace(
            json_marker,
            json_marker + "      'soopCookie': soopCookie.v,\n",
            1,
        )

    if "soopCookie.v = json['soopCookie']" not in cookie_text:
        from_marker = (
            "    kuaishouCookie.v = json['kuaishouCookie'] ?? '';\n"
        )
        if from_marker not in cookie_text:
            raise SystemExit(
                "❌ CookieSettingsController fromJson 结构变化"
            )
        cookie_text = cookie_text.replace(
            from_marker,
            from_marker
            + "    soopCookie.v = json['soopCookie'] ?? '';\n",
            1,
        )

    if "'soopCookie': cookie['soopCookie']" not in cookie_text:
        extract_marker = (
            "      'kuaishouCookie': cookie['kuaishouCookie'] ?? '',\n"
        )
        if extract_marker not in cookie_text:
            raise SystemExit(
                "❌ CookieSettingsController extractConfig 结构变化"
            )
        cookie_text = cookie_text.replace(
            extract_marker,
            extract_marker
            + "      'soopCookie': cookie['soopCookie'] ?? '',\n",
            1,
        )

    write(cookie_path, cookie_text)
    print("✅ SOOP Cookie 接入 Pure 本地配置与备份")

    # 1.7 平台设置加入 SOOP 登录入口
    platform_path = (
        source
        / "lib/modules/settings/pages/platform_settings_page.dart"
    )
    platform_text = read(platform_path)

    auth_import = (
        "import 'package:pure_live/modules/settings/pages/"
        "soop_account_settings_page.dart';\n"
    )

    if auth_import not in platform_text:
        import_marker = (
            "import 'package:pure_live/common/index.dart';\n"
        )
        if import_marker not in platform_text:
            raise SystemExit(
                "❌ PlatformSettingsPage import 结构变化"
            )
        platform_text = platform_text.replace(
            import_marker,
            import_marker + auth_import,
            1,
        )

    if "SOOP 登录 / Cookie" not in platform_text:
        tile_marker = (
            "            context.buildTile(\n"
            "              icon: Remix.price_tag_3_line,\n"
        )
        if tile_marker not in platform_text:
            raise SystemExit(
                "❌ PlatformSettingsPage tile 结构变化"
            )

        tile_block = (
            "            context.buildTile(\n"
            "              icon: Icons.cookie_outlined,\n"
            '              title: "SOOP 登录 / Cookie",\n'
            '              subtitle: "账号登录或手动保存 Cookie，用于需要登录权限的直播",\n'
            "              onTap: () {\n"
            "                Get.to(() => const SoopAccountSettingsPage());\n"
            "              },\n"
            "            ),\n"
        )

        platform_text = platform_text.replace(
            tile_marker,
            tile_block + tile_marker,
            1,
        )

    write(platform_path, platform_text)
    print("✅ 平台设置加入 SOOP 登录 / Cookie 入口")

    # 2. sites.dart
    path = source / "lib/core/sites.dart"
    text = read(path)

    import_line = "import 'package:pure_live/core/site/soop_site.dart';\n"
    if import_line not in text:
        marker = "import 'package:pure_live/core/site/twitch_site.dart';\n"
        if marker not in text:
            marker = "import 'package:pure_live/core/site/kuaishou_site.dart';\n"
        if marker not in text:
            raise SystemExit("❌ sites.dart import 结构变化")
        text = text.replace(marker, marker + import_line, 1)

    const_line = '  static const String soopSite = "soop";\n'
    if const_line not in text:
        marker = '  static const String twitchSite = "twitch";\n'
        if marker not in text:
            marker = '  static const String iptvSite = "iptv";\n'
        if marker not in text:
            raise SystemExit("❌ sites.dart 常量结构变化")
        text = text.replace(marker, marker + const_line, 1)

    if 'id: "soop"' not in text:
        marker = (
            '    Site(id: "iptv", name: i18n("site_iptv"), '
            'logo: "assets/images/logo.png", liveSite: IptvSite()),\n'
        )
        if marker not in text:
            raise SystemExit("❌ sites.dart supportSites 结构变化")

        soop_line = (
            '    Site(id: "soop", name: "SOOP", '
            'logo: "assets/images/logo.png", liveSite: SoopSite()),\n'
        )
        text = text.replace(marker, soop_line + marker, 1)

    write(path, text)
    print("✅ 注册 SOOP 平台")

    # 3. LiveUrlTool
    path = source / "lib/common/utils/live_url_tool.dart"
    text = read(path)

    if "Sites.soopSite" not in text:
        marker = "    // 网易CC\n"
        if marker not in text:
            raise SystemExit("❌ LiveUrlTool 结构变化")

        block = r'''    // SOOP
    if (realUrl.toLowerCase().contains("sooplive") ||
        realUrl.toLowerCase().contains("afreecatv")) {
      try {
        var soopUrl = realUrl.split("?").first.trimEndChar('/');

        if (!soopUrl.startsWith("http://") &&
            !soopUrl.startsWith("https://")) {
          soopUrl = "https://$soopUrl";
        }

        final uri = Uri.parse(soopUrl);
        final host = uri.host.toLowerCase();
        final segments = uri.pathSegments
            .where((e) => e.trim().isNotEmpty)
            .toList();

        if (host == "play.sooplive.com" ||
            host == "play.sooplive.co.kr" ||
            host == "play.afreecatv.com") {
          if (segments.isEmpty) {
            return [];
          }

          final bid = segments[0].trim();
          final bno = segments.length > 1 ? segments[1].trim() : "";

          if (bid.isEmpty) {
            return [];
          }

          return [
            bno.isEmpty ? bid : "$bid/$bno",
            Sites.soopSite,
          ];
        }

        if (host == "www.sooplive.com" && segments.isNotEmpty) {
          // station/<channelId> 或全球站 /<channelId>
          final bid = segments[0].toLowerCase() == "station" &&
                  segments.length > 1
              ? segments[1].trim()
              : segments[0].trim();

          const reserved = {
            "live",
            "vod",
            "search",
            "station",
            "login",
            "item",
          };

          if (bid.isEmpty || reserved.contains(bid.toLowerCase())) {
            return [];
          }

          return [bid, Sites.soopSite];
        }

        if (host == "ch.sooplive.com" && segments.isNotEmpty) {
          final bid = segments[0].trim();

          if (bid.isEmpty) {
            return [];
          }

          return [bid, Sites.soopSite];
        }

        return [];
      } catch (_) {
        return [];
      }
    }

'''
        text = text.replace(marker, block + marker, 1)

    write(path, text)
    print("✅ SOOP 房间链接解析")

    # 4. ToolBox clipboard: append sooplive / afreecatv to existing regex.
    path = source / "lib/modules/toolbox/toolbox_controller.dart"
    text = read(path)

    if "sooplive" not in text.lower():
        match = re.search(
            r'RegExp\(r"([^"]*bilibili[^"]*)"([^)]*)\)\.hasMatch\(text\)',
            text,
        )
        if not match:
            raise SystemExit("❌ ToolBoxController 剪贴板 RegExp 结构变化")

        pattern = match.group(1)
        tail = match.group(2)

        if "sooplive" not in pattern:
            pattern += "|sooplive|afreecatv"

        replacement = f'RegExp(r"{pattern}"{tail}).hasMatch(text)'
        text = text[:match.start()] + replacement + text[match.end():]

    write(path, text)
    print("✅ 剪贴板自动识别 SOOP")

    # 5. LivePlay: SOOP 不启动弹幕 + 官方网页跳转
    path = source / "lib/modules/live_play/controllers/live_play_controller.dart"
    text = read(path)

    except_match = re.search(
        r"const except = \[(.*?)\];",
        text,
        flags=re.S,
    )
    if not except_match:
        raise SystemExit("❌ LivePlayController 弹幕 except 列表结构变化")

    content = except_match.group(1)
    if "Sites.soopSite" not in content:
        new_content = content.rstrip() + ", Sites.soopSite"
        text = (
            text[:except_match.start(1)]
            + new_content
            + text[except_match.end(1):]
        )

    if "case Sites.soopSite:" not in text:
        marker = "      case Sites.kuaishouSite:\n"
        if marker not in text:
            raise SystemExit("❌ LivePlayController openNaviteAPP 结构变化")

        block = (
            "      case Sites.soopSite:\n"
            '        nativeUrl = "https://play.sooplive.com/${detail.roomId}";\n'
            '        webUrl = "https://play.sooplive.com/${detail.roomId}";\n'
            "        break;\n"
        )
        text = text.replace(marker, block + marker, 1)

    write(path, text)
    print("✅ SOOP 弹幕连接禁用")
    print("✅ SOOP 官方网页跳转加入")

    # 6. Player HLS headers
    path = source / "lib/modules/live_play/controllers/player_controller.dart"
    text = read(path)

    if "currentSite.id == Sites.soopSite" not in text:
        marker = "    } else if (currentSite.id == Sites.iptvSite) {\n"
        if marker not in text:
            raise SystemExit("❌ PlayerController getHeaders 结构变化")

        block = (
            "    } else if (currentSite.id == Sites.soopSite) {\n"
            "      final soopRoomId = currentRoom?.roomId ?? \"\";\n"
            "      headers = {\n"
            '        "user-agent":\n'
            '            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) '
            'Gecko/20100101 Firefox/122.0",\n'
            '        "accept-language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",\n'
            '        "origin": "https://play.sooplive.com",\n'
            '        if (SettingsService.to.cookieManager.soopCookie.v.isNotEmpty)\n'
            '          "cookie": SettingsService.to.cookieManager.soopCookie.v,\n'
            '        "referer": soopRoomId.isEmpty\n'
            '            ? "https://play.sooplive.com/"\n'
            '            : "https://play.sooplive.com/$soopRoomId",\n'
            "      };\n"
        )
        text = text.replace(marker, block + marker, 1)

    write(path, text)
    print("✅ SOOP HLS Headers 加入播放器")

    # 7. final checks
    checks = {
        "SoopSite": site_path.exists(),
        "Sites": 'static const String soopSite = "soop";' in read(source / "lib/core/sites.dart"),
        "URL": "Sites.soopSite" in read(source / "lib/common/utils/live_url_tool.dart"),
        "DanmakuExcept": "Sites.soopSite" in read(source / "lib/modules/live_play/controllers/live_play_controller.dart"),
        "PlayerHeader": "currentSite.id == Sites.soopSite" in read(source / "lib/modules/live_play/controllers/player_controller.dart"),
        "SoopCookieConfig": "soopCookie" in read(source / "lib/common/services/settings/cookie_settings_controller.dart"),
        "SoopAuthPage": auth_page_path.exists(),
        "SoopSettingsEntry": "SOOP 登录 / Cookie" in read(source / "lib/modules/settings/pages/platform_settings_page.dart"),
    }

    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("❌ SOOP 注入验证失败：" + ", ".join(failed))

    print("======================================")
    print("✅ SOOP V1 注入完成")
    print("======================================")


if __name__ == "__main__":
    main()
