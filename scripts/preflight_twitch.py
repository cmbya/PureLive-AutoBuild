#!/usr/bin/env python3
import argparse
import json
import random
import re
import string
import time
import urllib.parse
import urllib.request
from pathlib import Path

GQL_URL = "https://gql.twitch.tv/gql"
CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) "
    "Gecko/20100101 Firefox/115.0"
)

QUERY_NAMES = [
    "BrowsePage_AllDirectories",
    "DirectoryPage_Game",
    "ChannelShell",
    "StreamMetadata",
]

FALLBACK_HASHES = {
    "BrowsePage_AllDirectories":
        "2f67f71ba89f3c0ed26a141ec00da1defecb2303595f5cda4298169549783d9e",
    "DirectoryPage_Game":
        "c7c9d5aad09155c4161d2382092dc44610367f3536aac39019ec2582ae5065f9",
    "ChannelShell":
        "580ab410bcd0c1ad194224957ae2241e5d252b2c5173d8e0cce9d32d5bb14efe",
    "StreamMetadata":
        "b57f9b910f8cd1a4659d894fe7550ccc81ec9052c01e438b290fd66a040b9b93",
}

PLAYBACK_QUERY = (
    'query PlaybackAccessToken_Template('
    '$login: String!, $isLive: Boolean!, $vodID: ID!, '
    '$isVod: Boolean!, $playerType: String!, $platform: String!) { '
    'streamPlaybackAccessToken(channelName: $login, '
    'params: {platform: $platform, playerBackend: "mediaplayer", '
    'playerType: $playerType}) @include(if: $isLive) { '
    'value signature authorization { isForbidden forbiddenReasonCode } __typename } '
    'videoPlaybackAccessToken(id: $vodID, '
    'params: {platform: $platform, playerBackend: "mediaplayer", '
    'playerType: $playerType}) @include(if: $isVod) { '
    'value signature __typename }}'
)

def random_id(length=16):
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))

DEVICE_ID = random_id()

def headers(content_type="application/json"):
    return {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US",
        "Referer": "https://www.twitch.tv/",
        "Origin": "https://www.twitch.tv",
        "Client-Id": CLIENT_ID,
        "Client-Integrity": "",
        "Device-Id": DEVICE_ID,
        "Content-Type": content_type,
    }

def request_bytes(url, *, method="GET", data=None, request_headers=None, retries=3):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url, method=method, headers=request_headers or {}, data=data
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                return resp.read(), resp.status
        except Exception as exc:
            last_error = exc
            print(f"⚠️ 请求失败 {attempt}/{retries}: {exc}")
            if attempt < retries:
                time.sleep(attempt * 2)
    raise RuntimeError(f"请求最终失败：{url}\n{last_error}")

def get_current_hashes():
    base = (
        "https://raw.githubusercontent.com/"
        "DmitryScaletta/twitch-gql-queries/main/"
        "src/queries/{name}/query.ts"
    )
    hashes = {}
    for name in QUERY_NAMES:
        try:
            raw, _ = request_bytes(
                base.format(name=name),
                request_headers={"User-Agent": "PureLive-AutoBuild/4"},
                retries=2,
            )
            text = raw.decode("utf-8", errors="replace")
            match = re.search(
                r"sha256Hash\s*:\s*[\r\n\s]*['\"]([0-9a-f]{64})['\"]",
                text,
                re.I,
            )
            if not match:
                raise RuntimeError("query.ts 中没有 sha256Hash")
            value = match.group(1)
            source = "current"
        except Exception as exc:
            print(f"⚠️ {name} 动态 hash 获取失败：{exc}")
            value = FALLBACK_HASHES[name]
            source = "fallback"
        hashes[name] = value
        print(f"✅ {name}: {value} ({source})")
    return hashes

def gql_persisted(hashes, operation, variables):
    payload = {
        "operationName": operation,
        "variables": variables,
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": hashes[operation],
            }
        },
    }
    raw, status = request_bytes(
        GQL_URL,
        method="POST",
        data=json.dumps(payload).encode(),
        request_headers=headers(),
    )
    decoded = json.loads(raw.decode("utf-8"))
    if not (200 <= status < 300):
        raise RuntimeError(f"{operation} HTTP {status}: {decoded}")
    if isinstance(decoded, dict) and decoded.get("errors"):
        raise RuntimeError(f"{operation} GraphQL 错误：{decoded['errors']}")
    data = decoded.get("data") if isinstance(decoded, dict) else None
    if data is None:
        raise RuntimeError(f"{operation} 没有 data：{decoded}")
    return data

def gql_playback(login):
    payload = {
        "operationName": "PlaybackAccessToken_Template",
        "query": PLAYBACK_QUERY,
        "variables": {
            "isLive": True,
            "login": login,
            "isVod": False,
            "vodID": "",
            "playerType": "site",
            "platform": "web",
        },
    }
    raw, status = request_bytes(
        GQL_URL,
        method="POST",
        data=json.dumps(payload).encode(),
        request_headers=headers("text/plain;charset=UTF-8"),
    )
    decoded = json.loads(raw.decode("utf-8"))
    if not (200 <= status < 300):
        raise RuntimeError(f"Playback HTTP {status}: {decoded}")
    if isinstance(decoded, dict) and decoded.get("errors"):
        raise RuntimeError(f"Playback GraphQL 错误：{decoded['errors']}")
    token_data = (decoded.get("data") or {}).get("streamPlaybackAccessToken")
    if not token_data:
        raise RuntimeError("没有 streamPlaybackAccessToken")
    auth = token_data.get("authorization") or {}
    if auth.get("isForbidden") is True:
        raise RuntimeError(
            "Twitch 播放被限制：" + str(auth.get("forbiddenReasonCode"))
        )
    token = str(token_data.get("value") or "")
    signature = str(token_data.get("signature") or "")
    if not token or not signature:
        raise RuntimeError("Playback token/signature 为空")
    return token, signature

def build_usher_url(login, token, signature):
    params = {
        "acmb": "e30=",
        "allow_audio_only": "true",
        "allow_source": "true",
        "browser_family": "firefox",
        "browser_version": "124.0",
        "cdm": "wv",
        "fast_bread": "true",
        "os_name": "Windows",
        "os_version": "NT 10.0",
        "p": str(random.randint(1000000, 9999999)),
        "platform": "web",
        "play_session_id": random.choice([
            "bdd22331a986c7f1073628f2fc5b19da",
            "064bc3ff1722b6f53b0b5b8c01e46ca5",
        ]),
        "player_backend": "mediaplayer",
        "player_version": "1.28.0-rc.1",
        "playlist_include_framerate": "true",
        "reassignments_supported": "true",
        "sig": signature,
        "token": token,
        "transcode_mode": "cbr_v1",
    }
    return (
        f"https://usher.ttvnw.net/api/channel/hls/"
        f"{urllib.parse.quote(login.lower())}.m3u8?"
        f"{urllib.parse.urlencode(params)}"
    )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hash-output", default="twitch_hashes.json")
    args = parser.parse_args()

    print("======================================")
    print("Twitch V4 真实网络预检")
    print("======================================")
    hashes = get_current_hashes()
    Path(args.hash_output).write_text(
        json.dumps(hashes, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("\n1/6 分区列表")
    browse = gql_persisted(
        hashes,
        "BrowsePage_AllDirectories",
        {"cursor": None, "limit": 30, "options": {"sort": "RELEVANCE"}},
    )
    edges = (browse.get("directoriesWithTags") or {}).get("edges") or []
    categories = []
    for edge in edges:
        node = (edge or {}).get("node") or {}
        slug = str(node.get("slug") or "").strip()
        name = str(node.get("displayName") or node.get("name") or slug).strip()
        if slug:
            categories.append((slug, name))
    if not categories:
        raise RuntimeError("Twitch 分区为空")
    print(f"✅ {len(categories)} 个分类")
    for slug, name in categories[:8]:
        print(f"  - {name} ({slug})")

    print("\n2/6 分类直播")
    selected = None
    selected_category = None
    for slug, name in categories[:12]:
        data = gql_persisted(
            hashes,
            "DirectoryPage_Game",
            {
                "slug": slug,
                "options": {"sort": "VIEWER_COUNT"},
                "sortTypeIsRecency": False,
                "limit": 20,
                "includeIsDJ": True,
            },
        )
        stream_edges = ((data.get("game") or {}).get("streams") or {}).get("edges") or []
        for edge in stream_edges:
            node = (edge or {}).get("node") or {}
            login = str(((node.get("broadcaster") or {}).get("login")) or "").strip()
            if login:
                selected = node
                selected_category = (slug, name)
                break
        if selected:
            break
    if not selected:
        raise RuntimeError("热门分类里没有找到在线主播")

    broadcaster = selected.get("broadcaster") or {}
    login = str(broadcaster.get("login") or "").strip()
    display_name = str(broadcaster.get("displayName") or login)
    print(f"✅ 测试分类：{selected_category[1]} ({selected_category[0]})")
    print(f"✅ 测试主播：{display_name} ({login})")

    print("\n3/6 主播详情 / 在线状态")
    shell = gql_persisted(
        hashes,
        "ChannelShell",
        {"login": login},
    )

    user = shell.get("userOrError") or {}

    if not user.get("login"):
        raise RuntimeError(
            f"ChannelShell 没有返回有效主播：{user}"
        )

    if user.get("stream") is None:
        raise RuntimeError(
            "分类显示主播在线，但 ChannelShell 判定离线"
        )

    print(
        "✅ ChannelShell 正常："
        + str(
            user.get("displayName")
            or user.get("login")
        )
    )

    # StreamMetadata 只用于补充：
    # 标题 / 游戏分区 / 部分头像等信息。
    #
    # Twitch 偶尔会在其中某个非关键字段
    # （例如 user.primaryTeam）返回 service error。
    # Pure 里的 TwitchSite 本身已经对这个查询做了 try/catch，
    # 所以这里也不能把它当成“直播能否工作”的硬性门槛。
    try:
        metadata = gql_persisted(
            hashes,
            "StreamMetadata",
            {
                "channelLogin": login,
                "includeIsDJ": True,
            },
        )

        meta_user = metadata.get("user") or {}

        if meta_user.get("id"):
            print("✅ StreamMetadata 补充信息正常")
        else:
            print(
                "⚠️ StreamMetadata 没有完整用户信息，"
                "但不影响 Twitch 播放，继续预检"
            )

    except Exception as exc:
        print(
            "⚠️ StreamMetadata 当前返回错误："
            f"{exc}"
        )
        print(
            "⚠️ 该查询仅用于补充主播信息，"
            "不影响 ChannelShell / Playback / HLS，继续预检"
        )

    print("\n4/6 Playback Token")
    token, signature = gql_playback(login)
    print("✅ Playback Token 正常")

    print("\n5/6 Master M3U8")
    master_url = build_usher_url(login, token, signature)
    master_raw, master_status = request_bytes(
        master_url,
        request_headers=headers("text/plain;charset=UTF-8"),
    )
    master_text = master_raw.decode("utf-8", errors="replace")
    if "#EXTM3U" not in master_text or "#EXT-X-STREAM-INF" not in master_text:
        raise RuntimeError(f"Master M3U8 异常：HTTP {master_status}")
    print(
        "✅ Master M3U8 正常，视频清晰度："
        + str(master_text.count("#EXT-X-STREAM-INF"))
    )

    print("\n6/6 具体清晰度 M3U8")
    lines = [x.strip() for x in master_text.splitlines() if x.strip()]
    variant_url = None
    for i, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF"):
            continue
        for next_line in lines[i + 1:]:
            if not next_line.startswith("#"):
                variant_url = urllib.parse.urljoin(master_url, next_line)
                break
        if variant_url:
            break
    if not variant_url:
        raise RuntimeError("无法解析具体清晰度地址")
    variant_raw, status = request_bytes(
        variant_url,
        request_headers=headers("text/plain;charset=UTF-8"),
    )
    if "#EXTM3U" not in variant_raw.decode("utf-8", errors="replace"):
        raise RuntimeError(f"具体清晰度 M3U8 异常：HTTP {status}")
    print("✅ 具体清晰度 M3U8 正常")

    print("\n======================================")
    print("✅ Twitch V4 网络预检全部通过")
    print(f"测试主播：https://www.twitch.tv/{login}")
    print("======================================")

if __name__ == "__main__":
    main()
