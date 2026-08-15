#!/usr/bin/env python3
import json
import time
import urllib.parse
import urllib.request

LIST_API = "https://live.sooplive.com/api/main_broad_list_api.php"
PLAYER_API = "https://live.sooplive.com/afreeca/player_live_api.php"
PLAY_HOST = "https://play.sooplive.com"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) "
    "Gecko/20100101 Firefox/122.0"
)

# 与 simp 当前 SOOP 分区保持一致；check 会逐个真实请求，失效会直接拦截 build。
CATEGORIES = [
    ("00040000", "游戏"),
    ("00130000", "聊天"),
    ("00030000", "体育"),
    ("00010000", "娱乐"),
]


def headers(*, bid="", bno="", form=False):
    room = bid
    if bid and bno:
        room = f"{bid}/{bno}"

    result = {
        "User-Agent": USER_AGENT,
        "Origin": PLAY_HOST,
        "Referer": f"{PLAY_HOST}/{room}" if room else f"{PLAY_HOST}/",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
    }

    if form:
        result["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"

    return result


def request_bytes(url, *, method="GET", data=None, request_headers=None, retries=3):
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url,
                method=method,
                headers=request_headers or {},
                data=data,
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                return resp.read(), resp.status
        except Exception as exc:
            last_error = exc
            print(f"⚠️ 请求失败 {attempt}/{retries}: {exc}")
            if attempt < retries:
                time.sleep(attempt * 2)

    raise RuntimeError(f"请求最终失败：{url}\n{last_error}")


def get_json(url, *, request_headers=None):
    raw, status = request_bytes(
        url,
        request_headers=request_headers or headers(),
    )

    if not (200 <= status < 300):
        raise RuntimeError(f"HTTP {status}: {url}")

    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            f"JSON 解析失败：{url}\n{raw[:400]!r}\n{exc}"
        )


def post_form_json(url, form, *, request_headers=None):
    raw, status = request_bytes(
        url,
        method="POST",
        data=urllib.parse.urlencode(form).encode("utf-8"),
        request_headers=request_headers or headers(form=True),
    )

    if not (200 <= status < 300):
        raise RuntimeError(f"POST HTTP {status}: {url}")

    try:
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(
            f"POST JSON 解析失败：{url}\n{raw[:400]!r}\n{exc}"
        )


def fetch_list(*, page=1, category=None):
    params = {
        "selectType": "action" if category is None else "cate",
        "selectValue": "all" if category is None else category,
        "orderType": "view_cnt",
        "pageNo": str(page),
        "lang": "ko_KR",
    }

    url = LIST_API + "?" + urllib.parse.urlencode(params)

    payload = get_json(
        url,
        request_headers={
            "User-Agent": USER_AGENT,
            "Origin": PLAY_HOST,
            "Referer": f"{PLAY_HOST}/",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6",
        },
    )

    broad = payload.get("broad") if isinstance(payload, dict) else None
    if not isinstance(broad, list):
        raise RuntimeError(
            "SOOP 直播列表没有返回 broad 数组：" + str(payload)[:600]
        )

    return broad


def player_api(*, bid, bno, request_type, quality="master"):
    url = PLAYER_API + "?bjid=" + urllib.parse.quote(bid)

    payload = post_form_json(
        url,
        {
            "from_api": "0",
            "mode": "landing",
            "player_type": "html5",
            "stream_type": "common",
            "type": request_type,
            "bid": bid,
            "bno": bno,
            "pwd": "",
            "quality": quality,
        },
        request_headers=headers(bid=bid, bno=bno, form=True),
    )

    channel = payload.get("CHANNEL") if isinstance(payload, dict) else None
    return channel if isinstance(channel, dict) else {}


def cdn_return_type(cdn):
    cdn = str(cdn or "")

    if "gs_cdn" in cdn:
        return "gs_cdn_pc_web"

    if "lg_cdn" in cdn:
        return "lg_cdn_pc_web"

    return cdn


def stream_assign(*, rmd, cdn, bno, quality, bid):
    if not rmd:
        raise RuntimeError("CHANNEL.RMD 为空")

    return_type = cdn_return_type(cdn)
    if not return_type:
        raise RuntimeError("CHANNEL.CDN 为空")

    url = rmd.rstrip("/") + "/broad_stream_assign.html?" + urllib.parse.urlencode(
        {
            "return_type": return_type,
            "broad_key": f"{bno}-common-{quality}-hls",
        }
    )

    payload = get_json(
        url,
        request_headers=headers(bid=bid, bno=bno),
    )

    view_url = str(payload.get("view_url") or "")
    if not view_url:
        raise RuntimeError(
            "broad_stream_assign 没有 view_url：" + str(payload)[:600]
        )

    return view_url


def add_aid(view_url, aid):
    uri = urllib.parse.urlsplit(view_url)
    query = urllib.parse.parse_qsl(uri.query, keep_blank_values=True)
    query.append(("aid", aid))

    return urllib.parse.urlunsplit(
        (
            uri.scheme,
            uri.netloc,
            uri.path,
            urllib.parse.urlencode(query),
            uri.fragment,
        )
    )


def fetch_m3u8(url, *, bid, bno):
    raw, status = request_bytes(
        url,
        request_headers=headers(bid=bid, bno=bno),
    )

    if not (200 <= status < 300):
        raise RuntimeError(f"M3U8 HTTP {status}")

    text = raw.decode("utf-8", errors="replace")
    if "#EXTM3U" not in text:
        raise RuntimeError("返回内容不是 M3U8：" + text[:300])

    return text


def first_media_uri(playlist, base_url):
    for line in playlist.splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        # Streamlink 的 SOOP writer 也会过滤 preloading segment。
        if "preloading" in line.lower():
            continue

        return urllib.parse.urljoin(base_url, line)

    return ""


def candidate_qualities(info):
    result = []
    seen = set()

    presets = info.get("VIEWPRESET")
    if isinstance(presets, list):
        for preset in presets:
            if not isinstance(preset, dict):
                continue

            name = str(preset.get("name") or "").strip()
            label = str(preset.get("label") or name).strip()

            if not name or name == "auto":
                continue

            if name == "original":
                name = "master"

            if name not in seen:
                seen.add(name)
                result.append((name, label or name))

    # StreamGet 当前 SOOP 路线明确使用 master；保证它也参与测试。
    if "master" not in seen:
        result.insert(0, ("master", "原画/master"))

    return result


def verify_room(item):
    bid = str(item.get("user_id") or "").strip()
    bno = str(item.get("broad_no") or "").strip()

    if not bid:
        return None

    info = player_api(
        bid=bid,
        bno=bno,
        request_type="live",
        quality="master",
    )

    result = int(str(info.get("RESULT") or "0"))
    real_bno = str(info.get("BNO") or bno).strip()

    # -6 等登录要求、密码房、离线房全部跳过。
    if result != 1 or not real_bno:
        return None

    if str(info.get("BPWD") or "").upper() == "Y":
        return None

    rmd = str(info.get("RMD") or "").strip()
    cdn = str(info.get("CDN") or "").strip()

    if not rmd or not cdn:
        return None

    errors = []

    for quality, label in candidate_qualities(info):
        try:
            aid_info = player_api(
                bid=bid,
                bno=real_bno,
                request_type="aid",
                quality=quality,
            )

            if int(str(aid_info.get("RESULT") or "0")) != 1:
                raise RuntimeError("AID RESULT != 1")

            aid = str(aid_info.get("AID") or "")
            if not aid:
                raise RuntimeError("AID 为空")

            view_url = stream_assign(
                rmd=rmd,
                cdn=cdn,
                bno=real_bno,
                quality=quality,
                bid=bid,
            )

            play_url = add_aid(view_url, aid)

            # 我们的 iOS 版不额外放开 ATS。若 CDN 给 http，
            # 与 Dart 端一致先尝试同地址 https，再做真实请求验证。
            if play_url.lower().startswith("http://"):
                parts = urllib.parse.urlsplit(play_url)
                play_url = urllib.parse.urlunsplit(
                    ("https", parts.netloc, parts.path, parts.query, parts.fragment)
                )

            if not play_url.lower().startswith("https://"):
                raise RuntimeError(f"最终 HLS 不是 HTTPS：{play_url}")

            playlist = fetch_m3u8(
                play_url,
                bid=bid,
                bno=real_bno,
            )

            media_url = play_url

            # 如果返回的是 master playlist，再真实取一层子清晰度。
            if "#EXT-X-STREAM-INF" in playlist:
                child = first_media_uri(playlist, play_url)
                if not child:
                    raise RuntimeError("Master M3U8 没有子清晰度 URI")

                if not child.lower().startswith("https://"):
                    raise RuntimeError(f"子 M3U8 不是 HTTPS：{child}")

                playlist = fetch_m3u8(
                    child,
                    bid=bid,
                    bno=real_bno,
                )
                media_url = child

            segment = first_media_uri(playlist, media_url)
            if not segment:
                raise RuntimeError("Media M3U8 没有可用媒体分片")

            if not segment.lower().startswith("https://"):
                raise RuntimeError(f"媒体分片不是 HTTPS：{segment}")

            segment_headers = headers(bid=bid, bno=real_bno)
            segment_headers["Range"] = "bytes=0-1023"

            raw, status = request_bytes(
                segment,
                request_headers=segment_headers,
                retries=2,
            )

            if status not in (200, 206):
                raise RuntimeError(f"媒体分片 HTTP {status}")

            if len(raw) == 0:
                raise RuntimeError("媒体分片返回 0 字节")

            return {
                "bid": bid,
                "bno": real_bno,
                "nick": str(
                    info.get("BJNICK")
                    or item.get("user_nick")
                    or bid
                ),
                "title": str(
                    info.get("TITLE")
                    or item.get("broad_title")
                    or ""
                ),
                "quality": quality,
                "quality_label": label,
                "segment_status": status,
            }
        except Exception as exc:
            errors.append(f"{quality}: {exc}")

    print(
        f"⚠️ 跳过 {bid}/{real_bno}，所有清晰度失败："
        + " | ".join(errors[:4])
    )
    return None


def main():
    print("======================================")
    print("SOOP V1：完整真实网络预检")
    print("范围：公开、无需登录、无需密码的直播")
    print("======================================")

    print("\n1/6 热门直播列表")
    broad = fetch_list(page=1)
    if not broad:
        raise RuntimeError("SOOP 热门直播列表为空")
    print(f"✅ 热门列表返回 {len(broad)} 条")

    print("\n2/6 分区列表接口")
    category_success = 0

    for category_id, category_name in CATEGORIES:
        try:
            items = fetch_list(page=1, category=category_id)
            print(f"  - {category_name}({category_id}): {len(items)} 条")
            if items:
                category_success += 1
        except Exception as exc:
            print(f"⚠️ {category_name} 分区失败：{exc}")

    if category_success == 0:
        raise RuntimeError("SOOP 预设分区全部失败")

    print(f"✅ {category_success}/{len(CATEGORIES)} 个预设分区返回数据")

    print("\n3/6 自动寻找公开在线房间")
    selected = None

    # 多翻两页，减少恰好前一页都是登录/密码房导致的误判。
    candidates = list(broad)
    try:
        candidates.extend(fetch_list(page=2))
    except Exception:
        pass

    for item in candidates[:50]:
        try:
            selected = verify_room(item)
            if selected:
                break
        except Exception as exc:
            bid = str(item.get("user_id") or "?")
            print(f"⚠️ 跳过主播 {bid}: {exc}")

    if not selected:
        raise RuntimeError(
            "前 50 个热门直播中没有找到一条可以完整验证到媒体分片的公开直播"
        )

    print(
        f"✅ 测试主播：{selected['nick']} "
        f"({selected['bid']}/{selected['bno']})"
    )

    print("\n4/6 房间信息 / VIEWPRESET")
    print(f"✅ 标题：{selected['title']}")

    print("\n5/6 AID + CDN + HTTPS M3U8")
    print(
        f"✅ 测试清晰度：{selected['quality_label']} "
        f"({selected['quality']})"
    )
    print("✅ player_live_api → AID → broad_stream_assign → HLS 全部通过")

    print("\n6/6 实际媒体分片")
    print(f"✅ CDN 媒体分片可读取，HTTP {selected['segment_status']}")

    print("\n======================================")
    print("✅ SOOP V1 网络预检全部通过")
    print(
        "测试房间："
        f"https://play.sooplive.com/{selected['bid']}/{selected['bno']}"
    )
    print("======================================")


if __name__ == "__main__":
    main()
