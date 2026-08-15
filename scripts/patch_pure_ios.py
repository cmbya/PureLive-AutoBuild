#!/usr/bin/env python3
import argparse
import re
from pathlib import Path

def need(path: Path):
    if not path.exists():
        raise SystemExit(f"❌ 找不到文件：{path}")
    return path

def remove_method(text: str, signature: str):
    start = text.find(signature)
    if start == -1:
        return text, False
    line_start = text.rfind("\n", 0, start) + 1
    brace = text.find("{", start)
    if brace == -1:
        raise SystemExit(f"❌ 无法识别方法：{signature}")
    depth = 0
    end = None
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise SystemExit(f"❌ 无法识别方法结束：{signature}")
    while end < len(text) and text[end] == "\n":
        end += 1
    return text[:line_start] + text[end:], True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    args = parser.parse_args()
    source = Path(args.source).resolve()

    print("======================================")
    print("Pure Live iOS 修复")
    print("======================================")

    pubspec = need(source / "pubspec.yaml")
    text = pubspec.read_text(encoding="utf-8")

    old = "file_picker: ^12.0.0-beta.5"
    new = "file_picker: 12.0.0-beta.5"
    if old in text:
        text = text.replace(old, new, 1)
        print("✅ file_picker 锁定 beta.5")
    elif new in text:
        print("✅ file_picker 已锁定")
    else:
        print("ℹ️ file_picker 上游已变化，不强制替换")

    text2 = re.sub(
        r"(?m)^\s{2}share_handler:\s*[^\n]+\n",
        "",
        text,
        count=1,
    )
    if text2 != text:
        print("✅ 删除 share_handler 依赖")
    text = text2

    commented = (
        "flutter:\n"
        "  uses-material-design: true\n"
        "  # config:\n"
        "  #     enable-swift-package-manager: false"
    )
    enabled = (
        "flutter:\n"
        "  config:\n"
        "    enable-swift-package-manager: false\n"
        "  uses-material-design: true"
    )
    if commented in text:
        text = text.replace(commented, enabled, 1)
        print("✅ pubspec 关闭 SwiftPM")
    elif "enable-swift-package-manager: false" not in text:
        marker = "flutter:\n  uses-material-design: true"
        if marker in text:
            text = text.replace(marker, enabled, 1)
            print("✅ pubspec 关闭 SwiftPM")

    pubspec.write_text(text, encoding="utf-8")

    index_file = need(source / "lib/common/index.dart")
    text = index_file.read_text(encoding="utf-8")
    text2 = text.replace(
        "export 'package:share_handler/share_handler.dart';\n",
        "",
        1,
    )
    if text2 != text:
        print("✅ 删除 share_handler export")
    index_file.write_text(text2, encoding="utf-8")

    main_file = need(source / "lib/main.dart")
    text = main_file.read_text(encoding="utf-8")
    text2 = re.sub(
        r"(?m)^\s*initSharedMediaListener\(\);\s*\n",
        "",
        text,
        count=1,
    )
    if text2 != text:
        print("✅ 删除 ShareHandler 初始化调用")
    text = text2
    text, removed = remove_method(
        text,
        "Future<void> initSharedMediaListener() async {",
    )
    if removed:
        print("✅ 删除 ShareHandler 方法")
    main_file.write_text(text, encoding="utf-8")

    podfile = need(source / "ios/Podfile")
    text = podfile.read_text(encoding="utf-8")
    text = re.sub(
        r"\n\s*# share_handler addition start.*?# share_handler addition end\s*",
        "\n",
        text,
        flags=re.S,
        count=1,
    )
    text = re.sub(
        r"\n\s*target 'ShareExtension' do.*?\n\s*end\s*",
        "\n",
        text,
        flags=re.S,
        count=1,
    )
    podfile.write_text(text, encoding="utf-8")
    if "target 'ShareExtension'" in text:
        raise SystemExit("❌ Podfile 仍存在 ShareExtension")
    print("✅ Podfile 移除 ShareExtension")

    project = need(source / "ios/Runner.xcodeproj/project.pbxproj")
    text = project.read_text(encoding="utf-8")

    phase_match = re.search(
        r"([A-F0-9]{24}) /\* Embed Foundation Extensions \*/ = \{",
        text,
    )
    phase_id = phase_match.group(1) if phase_match else None

    dep_id = None
    dep_pattern = re.compile(
        r"([A-F0-9]{24}) /\* PBXTargetDependency \*/ = \{(.*?)\n\s*\};",
        re.S,
    )
    for match in dep_pattern.finditer(text):
        if "ShareExtension" in match.group(2):
            dep_id = match.group(1)
            break

    runner_pattern = re.compile(
        r"([A-F0-9]{24}) /\* Runner \*/ = \{\n\s*isa = PBXNativeTarget;.*?\n\s*\};",
        re.S,
    )
    runner_match = runner_pattern.search(text)
    if not runner_match:
        raise SystemExit("❌ 找不到 Runner PBXNativeTarget")

    runner = runner_match.group(0)
    old_runner = runner

    if phase_id:
        runner = re.sub(
            rf"^\s*{re.escape(phase_id)} /\* Embed Foundation Extensions \*/,\s*\n",
            "",
            runner,
            flags=re.M,
        )
    if dep_id:
        runner = re.sub(
            rf"^\s*{re.escape(dep_id)} /\* PBXTargetDependency \*/,\s*\n",
            "",
            runner,
            flags=re.M,
        )

    text = text[:runner_match.start()] + runner + text[runner_match.end():]
    project.write_text(text, encoding="utf-8")

    if runner != old_runner:
        print("✅ Runner 与 ShareExtension 构建链断开")
    else:
        print("ℹ️ Runner 已没有 ShareExtension 构建引用")

    entitlements = need(source / "ios/Runner/Runner.entitlements")
    entitlements.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        '<dict>\n'
        '</dict>\n'
        '</plist>\n',
        encoding="utf-8",
    )
    print("✅ 清空 Runner App Group")

    errors = []
    if re.search(
        r"(?m)^\s{2}share_handler:",
        pubspec.read_text(encoding="utf-8"),
    ):
        errors.append("pubspec 仍有 share_handler")
    if "package:share_handler/" in index_file.read_text(encoding="utf-8"):
        errors.append("index.dart 仍有 share_handler")
    if "ShareHandler.instance" in main_file.read_text(encoding="utf-8"):
        errors.append("main.dart 仍有 ShareHandler")
    if "target 'ShareExtension'" in podfile.read_text(encoding="utf-8"):
        errors.append("Podfile 仍有 ShareExtension")

    check = project.read_text(encoding="utf-8")
    check_runner = runner_pattern.search(check)
    if not check_runner:
        errors.append("Runner Target 修改后无法识别")
    else:
        block = check_runner.group(0)
        if phase_id and phase_id in block:
            errors.append("Runner 仍有 Embed Foundation Extensions")
        if dep_id and dep_id in block:
            errors.append("Runner 仍有 ShareExtension dependency")

    if errors:
        for item in errors:
            print("❌ " + item)
        raise SystemExit("iOS 修复验证失败")

    print("======================================")
    print("✅ Pure Live iOS 修复完成")
    print("======================================")

if __name__ == "__main__":
    main()
