# Pure Live 2.1.1+ 官方 iOS + 自定义 Twitch / SOOP

这套方案废弃旧的 iOS 修复思路。

## 为什么要换

Pure Live 2.1.1 已经有官方 iOS，并且官方 `sites.dart`
已经注册了 Twitch / SOOP：

```dart
Site(id: twitchSite, ..., liveSite: TwitchSite()),
Site(id: soopSite, ..., liveSite: SoopSite()),
Site(id: iptvSite, ..., liveSite: IptvSite()),
```

旧补丁还在尝试：

- 删除 share_handler
- 禁用 Swift Package Manager
- 修改 Podfile / ShareExtension
- 向 `Sites.supportSites` 再次注入 Twitch / SOOP
- 用旧的 `id: "iptv"` 文本当锚点

这些行为已经不适合 2.1.1。

## 新方案

只做两件事：

1. 完整保留 Pure Live 官方 iOS 工程和官方平台注册。
2. 把你已经验证过的自定义 Twitch / SOOP **实现文件**替换进去。

真正回写上游源码的只有：

```text
lib/core/site/twitch_site.dart
lib/core/site/soop_site.dart
```

不会改：

```text
ios/
pubspec.yaml
lib/core/sites.dart
```

## 为什么还保留旧 patch_twitch.py / patch_soop.py

不是再让它们修改官方源码。

新脚本会把官方源码复制到临时隔离目录，在临时目录运行旧生成器，
只拿出最终生成的：

```text
twitch_site.dart
soop_site.dart
```

旧脚本后面因为 `sites.dart` 结构不匹配而报错也没关系，
那些错误修改永远不会回写官方源码。

这样可以继续复用你现有 Twitch 动态 hash 渲染和 SOOP 模板，
不用重新猜模板变量。

## 要上传的文件

覆盖：

```text
.github/workflows/purelive-daily-ios-release.yml
```

新增：

```text
scripts/extract_custom_sites_v211.py
```

旧的这些文件可以留着，但新 iOS workflow 不再直接用它们去改官方源码：

```text
scripts/patch_pure_ios.py
scripts/patch_sites_compat.py
```

现有下面这些文件继续保留：

```text
scripts/patch_twitch.py
scripts/patch_soop.py
scripts/preflight_twitch.py
scripts/preflight_soop.py
patches/twitch_site.dart.tpl
patches/soop_site.dart.tpl
patches/soop_account_settings_page.dart.tpl
```

## 第一次测试

GitHub Actions 手动运行 iOS workflow：

```text
version = v2.1.1
force_build = true
```

预检阶段应看到：

```text
✅ 检测到官方 Twitch 注册
✅ 检测到官方 SOOP 注册
✅ 不修改 Sites.supportSites
✅ sites.dart：官方原样保留
✅ ios/：官方原样保留
✅ pubspec.yaml：官方原样保留
```

然后才会启动 macOS 编译。

## 输出

Release 会同时有两个 IPA：

```text
PureLive-2.1.1-Custom-Twitch-SOOP-iOS-Official-Unsigned.ipa
PureLive-2.1.1-Custom-Twitch-SOOP-iOS-LiveContainer.ipa
```

- `Official-Unsigned`：完整保留官方 App Extension。
- `LiveContainer`：只在最终 IPA 副本里删除 `PlugIns`，源码和编译过程仍然是官方 iOS。
