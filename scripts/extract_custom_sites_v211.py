#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_digest(root: Path) -> str:
    h = hashlib.sha256()

    if not root.exists():
        return "MISSING"

    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        h.update(rel.encode("utf-8"))

        if path.is_symlink():
            h.update(b"L")
            h.update(str(path.readlink()).encode("utf-8"))
        elif path.is_file():
            h.update(b"F")
            h.update(sha256_file(path).encode("ascii"))
        elif path.is_dir():
            h.update(b"D")

    return h.hexdigest()


def run_generator(
    *,
    label: str,
    command: list[str],
    expected_file: Path,
) -> None:
    print("")
    print("=" * 72)
    print(f"{label}：在隔离副本里运行旧生成器")
    print("=" * 72)

    proc = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    output = proc.stdout or ""

    # The legacy patcher can return non-zero on Pure Live 2.1.1 because its
    # old sites.dart registration code no longer matches. That is expected
    # here: we only use it as a generator for the custom site implementation.
    if output:
        lines = output.splitlines()

        # Keep logs readable in Actions. The useful generation message and
        # tail are enough; do not flood the job with the whole legacy log.
        interesting = [
            line
            for line in lines
            if (
                "生成" in line
                or "twitch_site.dart" in line
                or "soop_site.dart" in line
                or "supportSites" in line
                or "结构变化" in line
                or "ERROR" in line
                or "Error" in line
            )
        ]

        for line in interesting[-30:]:
            print(line)

    if not expected_file.exists():
        print("")
        print(f"❌ {label} 没有生成：{expected_file}")
        print(f"旧生成器退出码：{proc.returncode}")
        print("")
        print("========== 旧生成器完整尾部日志 ==========")
        for line in (output.splitlines()[-100:]):
            print(line)
        raise SystemExit(1)

    print(f"✅ {label} 已生成：{expected_file}")

    if proc.returncode != 0:
        print(
            "ℹ️ 旧生成器后续的 legacy 注册步骤返回非零；"
            "本流程故意忽略，因为不会把那些修改带回官方源码。"
        )


def must_exist(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"❌ 缺少 {label}：{path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Pure Live 2.1.1+：保留官方 iOS/平台注册，只提取并替换"
            "自定义 Twitch / SOOP site 实现。"
        )
    )
    parser.add_argument("source")
    parser.add_argument("--hashes", required=True)
    parser.add_argument("--patch-twitch", required=True)
    parser.add_argument("--twitch-template", required=True)
    parser.add_argument("--patch-soop", required=True)
    parser.add_argument("--soop-template", required=True)
    parser.add_argument("--soop-auth-template", required=True)
    args = parser.parse_args()

    source = Path(args.source).resolve()
    hashes = Path(args.hashes).resolve()
    patch_twitch = Path(args.patch_twitch).resolve()
    twitch_template = Path(args.twitch_template).resolve()
    patch_soop = Path(args.patch_soop).resolve()
    soop_template = Path(args.soop_template).resolve()
    soop_auth_template = Path(args.soop_auth_template).resolve()

    sites = source / "lib/core/sites.dart"
    ios_dir = source / "ios"
    pubspec = source / "pubspec.yaml"

    must_exist(source, "Pure Live 源码")
    must_exist(sites, "官方 sites.dart")
    must_exist(ios_dir, "官方 iOS 工程")
    must_exist(pubspec, "官方 pubspec.yaml")
    must_exist(hashes, "Twitch 预检 hashes")
    must_exist(patch_twitch, "现有 patch_twitch.py")
    must_exist(twitch_template, "现有 Twitch 模板")
    must_exist(patch_soop, "现有 patch_soop.py")
    must_exist(soop_template, "现有 SOOP 模板")
    must_exist(soop_auth_template, "现有 SOOP Auth 模板")

    original_sites_hash = sha256_file(sites)
    original_ios_hash = tree_digest(ios_dir)
    original_pubspec_hash = sha256_file(pubspec)

    sites_text = sites.read_text(
        encoding="utf-8",
        errors="replace",
    )

    # v2.1.1 already has official registrations. We intentionally require
    # them and NEVER add/remove Site entries here.
    twitch_registered = (
        "TwitchSite()" in sites_text
        and (
            "id: twitchSite" in sites_text
            or 'id: "twitch"' in sites_text
            or "id: 'twitch'" in sites_text
        )
    )

    soop_registered = (
        "SoopSite()" in sites_text
        and (
            "id: soopSite" in sites_text
            or 'id: "soop"' in sites_text
            or "id: 'soop'" in sites_text
        )
    )

    if not twitch_registered:
        raise SystemExit(
            "❌ 当前上游没有检测到官方 Twitch 注册。"
            "此 workflow 专用于已经内置 Twitch/SOOP 的 Pure Live 2.1.1+。"
        )

    if not soop_registered:
        raise SystemExit(
            "❌ 当前上游没有检测到官方 SOOP 注册。"
            "此 workflow 专用于已经内置 Twitch/SOOP 的 Pure Live 2.1.1+。"
        )

    print("✅ 检测到官方 Twitch 注册")
    print("✅ 检测到官方 SOOP 注册")
    print("✅ 不修改 Sites.supportSites")

    with tempfile.TemporaryDirectory(
        prefix="purelive-custom-sites-"
    ) as tmp:
        tmp_root = Path(tmp)

        twitch_work = tmp_root / "twitch-source"
        soop_work = tmp_root / "soop-source"

        print("")
        print("复制官方源码到两个隔离生成目录……")
        shutil.copytree(
            source,
            twitch_work,
            symlinks=True,
        )
        shutil.copytree(
            source,
            soop_work,
            symlinks=True,
        )

        twitch_output = (
            twitch_work
            / "lib/core/site/twitch_site.dart"
        )

        run_generator(
            label="自定义 Twitch",
            command=[
                sys.executable,
                str(patch_twitch),
                str(twitch_work),
                "--hashes",
                str(hashes),
                "--template",
                str(twitch_template),
            ],
            expected_file=twitch_output,
        )

        soop_output = (
            soop_work
            / "lib/core/site/soop_site.dart"
        )

        run_generator(
            label="自定义 SOOP",
            command=[
                sys.executable,
                str(patch_soop),
                str(soop_work),
                "--template",
                str(soop_template),
                "--auth-page-template",
                str(soop_auth_template),
            ],
            expected_file=soop_output,
        )

        twitch_text = twitch_output.read_text(
            encoding="utf-8",
            errors="replace",
        )

        # User's current desired Twitch variant is explicitly no-danmaku.
        forbidden_twitch = [
            "TwitchDanmaku(",
            "twitch_danmaku.dart",
        ]

        stale = [
            token
            for token in forbidden_twitch
            if token in twitch_text
        ]

        if stale:
            raise SystemExit(
                "❌ 当前 patches/twitch_site.dart.tpl 仍是带 Twitch 弹幕的旧模板："
                + ", ".join(stale)
                + "\n请先保留仓库里已经验证过的“无 Twitch 弹幕网络”模板。"
            )

        soop_text = soop_output.read_text(
            encoding="utf-8",
            errors="replace",
        )

        # The custom SOOP V5.3 implementation uses the local soopCookie.
        # Pure 2.1.1 may already include the merged settings implementation.
        # Verify this BEFORE expensive macOS compilation.
        if "soopCookie" in soop_text:
            cookie_hits = []

            for candidate in (
                source
                / "lib/common/services/settings"
            ).rglob("*.dart"):
                content = candidate.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )

                if "soopCookie" in content:
                    cookie_hits.append(candidate)

            if not cookie_hits:
                raise SystemExit(
                    "❌ 自定义 SOOP 需要 soopCookie，"
                    "但当前 Pure Live 官方设置服务没有找到该字段。\n"
                    "为避免重新编译十几分钟后才失败，本次在预检阶段停止。\n"
                    "不要恢复旧 patch_soop 的 sites.dart 注册逻辑。"
                )

            print("✅ 官方源码已存在 SOOP Cookie 设置支持：")
            for hit in cookie_hits[:10]:
                print(f"   - {hit.relative_to(source)}")

        # Only two implementation files are brought back.
        real_twitch = (
            source
            / "lib/core/site/twitch_site.dart"
        )
        real_soop = (
            source
            / "lib/core/site/soop_site.dart"
        )

        shutil.copy2(
            twitch_output,
            real_twitch,
        )
        shutil.copy2(
            soop_output,
            real_soop,
        )

    # Hard guarantee: official registration/native iOS/pubspec were untouched.
    if sha256_file(sites) != original_sites_hash:
        raise SystemExit(
            "❌ 安全检查失败：sites.dart 被修改。"
        )

    if tree_digest(ios_dir) != original_ios_hash:
        raise SystemExit(
            "❌ 安全检查失败：官方 ios/ 工程被修改。"
        )

    if sha256_file(pubspec) != original_pubspec_hash:
        raise SystemExit(
            "❌ 安全检查失败：官方 pubspec.yaml 被修改。"
        )

    print("")
    print("=" * 72)
    print("✅ 自定义平台替换完成")
    print("✅ 只替换 lib/core/site/twitch_site.dart")
    print("✅ 只替换 lib/core/site/soop_site.dart")
    print("✅ sites.dart：官方原样保留")
    print("✅ ios/：官方原样保留")
    print("✅ pubspec.yaml：官方原样保留")
    print("=" * 72)


if __name__ == "__main__":
    main()
