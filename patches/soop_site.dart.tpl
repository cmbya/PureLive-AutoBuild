import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:pure_live/common/models/live_area.dart';
import 'package:pure_live/common/models/live_room.dart';
import 'package:pure_live/common/services/settings_service.dart';
import 'package:pure_live/core/interface/live_danmaku.dart';
import 'package:pure_live/core/interface/live_site.dart';
import 'package:pure_live/model/live_category.dart';
import 'package:pure_live/model/live_play_quality.dart';

class SoopNoDanmaku extends LiveDanmaku {}

class SoopSite extends LiveSite {
  static const String platformId = 'soop';

  static const String _listApi =
      'https://live.sooplive.com/api/main_broad_list_api.php';

  static const String _playerApi =
      'https://live.sooplive.com/afreeca/player_live_api.php';

  static const String _playHost =
      'https://play.sooplive.com';

  static const String _globalStreamInfoApi =
      'https://api.sooplive.com/v2/stream/info/';

  static const String _globalChannelInfoApi =
      'https://api.sooplive.com/v2/channel/info/';

  static const String _userAgent =
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) '
      'Gecko/20100101 Firefox/122.0';

  @override
  String id = platformId;

  @override
  String name = 'SOOP';

  @override
  LiveDanmaku getDanmaku() => SoopNoDanmaku();

  Map<String, dynamic>? _map(dynamic value) {
    if (value is Map<String, dynamic>) {
      return value;
    }

    if (value is Map) {
      return Map<String, dynamic>.from(value);
    }

    return null;
  }

  List<dynamic> _list(dynamic value) {
    return value is List ? value : const [];
  }

  int _int(dynamic value) {
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }

  String _normalizeImageUrl(dynamic value) {
    final url = value?.toString() ?? '';

    if (url.startsWith('//')) {
      return 'https:$url';
    }

    return url;
  }

  String _normalizeQuality(dynamic value) {
    final quality = value?.toString().trim() ?? '';

    if (quality.isEmpty || quality == 'original') {
      return 'master';
    }

    return quality;
  }

  String get _savedCookie =>
      SettingsService.to.cookieManager.soopCookie.v.trim();

  Map<String, String> _headers({
    String roomId = '',
    bool form = false,
  }) {
    final cookie = _savedCookie;

    return {
      'user-agent': _userAgent,
      'origin': _playHost,
      'referer': roomId.isEmpty
          ? '$_playHost/'
          : '$_playHost/$roomId',
      'accept-language':
          'ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6',
      if (cookie.isNotEmpty) 'cookie': cookie,
      if (form)
        'content-type':
            'application/x-www-form-urlencoded; charset=UTF-8',
    };
  }

  Future<Map<String, dynamic>> _getJson(
    Uri uri, {
    String roomId = '',
  }) async {
    final response = await http
        .get(
          uri,
          headers: _headers(roomId: roomId),
        )
        .timeout(const Duration(seconds: 20));

    if (response.statusCode < 200 ||
        response.statusCode >= 300) {
      throw Exception(
        'SOOP HTTP ${response.statusCode}',
      );
    }

    final decoded = jsonDecode(response.body);
    final result = _map(decoded);

    if (result == null) {
      throw Exception('SOOP JSON 返回格式异常');
    }

    return result;
  }

  Future<Map<String, dynamic>> _playerApiCall({
    required String bid,
    required String bno,
    required String type,
    String quality = 'master',
  }) async {
    final uri = Uri.parse(
      '$_playerApi?bjid=${Uri.encodeComponent(bid)}',
    );

    final response = await http
        .post(
          uri,
          headers: _headers(
            roomId: bno.isEmpty ? bid : '$bid/$bno',
            form: true,
          ),
          body: {
            'from_api': '0',
            'mode': 'landing',
            'player_type': 'html5',
            'stream_type': 'common',
            'type': type,
            'bid': bid,
            'bno': bno,
            'pwd': '',
            'quality': quality,
          },
        )
        .timeout(const Duration(seconds: 20));

    if (response.statusCode < 200 ||
        response.statusCode >= 300) {
      throw Exception(
        'SOOP Player API HTTP ${response.statusCode}',
      );
    }

    final root = _map(jsonDecode(response.body));
    return _map(root?['CHANNEL']) ?? {};
  }

  Future<Map<String, dynamic>> _globalInfo(
    String channelId,
  ) async {
    try {
      final streamRoot = await _getJson(
        Uri.parse('$_globalStreamInfoApi$channelId'),
      );

      final streamData = _map(streamRoot['data']);

      if (streamData?['isStream'] != true) {
        return {};
      }

      var nick = channelId;

      try {
        final channelRoot = await _getJson(
          Uri.parse('$_globalChannelInfoApi$channelId'),
        );

        final channelData = _map(channelRoot['data']);
        final channelInfo = _map(
          channelData?['streamerChannelInfo'],
        );

        nick = channelInfo?['nickname']?.toString() ?? channelId;
      } catch (_) {}

      return {
        'RESULT': 1,
        'BNO': channelId,
        'BJID': channelId,
        'BJNICK': nick,
        'TITLE': streamData?['title']?.toString() ?? '',
        'CTUSER':
            streamData?['totalViewCount']?.toString() ?? '0',
        'GLOBAL_M3U8':
            'https://global-media.sooplive.com/live/'
            '$channelId/master.m3u8',
      };
    } catch (_) {
      return {};
    }
  }

  Future<Map<String, dynamic>> _liveInfo(
    String roomId,
  ) async {
    final parts = roomId
        .split('/')
        .where((e) => e.trim().isNotEmpty)
        .toList();

    if (parts.isEmpty) {
      return {};
    }

    final bid = parts.first;
    final bno = parts.length > 1 ? parts[1] : '';

    final webInfo = await _playerApiCall(
      bid: bid,
      bno: bno,
      type: 'live',
      quality: 'master',
    );

    if (_int(webInfo['RESULT']) == 1) {
      return webInfo;
    }

    // www.sooplive.com/<channelId> 的全球站 fallback。
    final global = await _globalInfo(bid);

    if (_int(global['RESULT']) == 1) {
      return global;
    }

    return webInfo;
  }

  LiveRoom _roomFromList(
    Map<String, dynamic> item,
  ) {
    final bid = item['user_id']?.toString() ?? '';
    final bno = item['broad_no']?.toString() ?? '';

    final roomId = bno.isEmpty ? bid : '$bid/$bno';

    return LiveRoom(
      roomId: roomId,
      userId: bid,
      title: item['broad_title']?.toString() ?? '',
      nick: item['user_nick']?.toString() ?? bid,
      avatar: '',
      cover: _normalizeImageUrl(
        item['broad_thumb'] ?? item['broad_img'],
      ),
      area: item['category_name']?.toString() ?? '',
      watching: (
        item['current_view_cnt'] ??
        item['pc_view_cnt'] ??
        item['total_view_cnt'] ??
        '0'
      ).toString(),
      platform: platformId,
      status: true,
      liveStatus: LiveStatus.live,
      link: '$_playHost/$roomId',
    );
  }

  Future<List<LiveRoom>> _roomList({
    required int page,
    String? category,
  }) async {
    final query = <String, String>{
      'selectType': category == null ? 'action' : 'cate',
      'selectValue': category ?? 'all',
      'orderType': 'view_cnt',
      'pageNo': page.toString(),
      'lang': 'ko_KR',
    };

    final payload = await _getJson(
      Uri.parse(_listApi).replace(
        queryParameters: query,
      ),
    );

    final result = <LiveRoom>[];

    for (final raw in _list(payload['broad'])) {
      final item = _map(raw);

      if (item == null) {
        continue;
      }

      final room = _roomFromList(item);

      if ((room.roomId ?? '').isNotEmpty) {
        result.add(room);
      }
    }

    return result;
  }

  @override
  Future<List<LiveCategory>> getCategores(
    int page,
    int pageSize,
  ) async {
    return [
      LiveCategory(
        id: 'soop_main',
        name: 'SOOP',
        children: [
          LiveArea(
            platform: platformId,
            areaType: 'soop_category',
            typeName: 'SOOP',
            areaId: 'all',
            areaName: '全部',
            shortName: '全部',
          ),
          LiveArea(
            platform: platformId,
            areaType: 'soop_category',
            typeName: 'SOOP',
            areaId: '00040000',
            areaName: '游戏',
            shortName: '游戏',
          ),
          LiveArea(
            platform: platformId,
            areaType: 'soop_category',
            typeName: 'SOOP',
            areaId: '00130000',
            areaName: '聊天',
            shortName: '聊天',
          ),
          LiveArea(
            platform: platformId,
            areaType: 'soop_category',
            typeName: 'SOOP',
            areaId: '00030000',
            areaName: '体育',
            shortName: '体育',
          ),
          LiveArea(
            platform: platformId,
            areaType: 'soop_category',
            typeName: 'SOOP',
            areaId: '00010000',
            areaName: '娱乐',
            shortName: '娱乐',
          ),
        ],
      ),
    ];
  }

  @override
  Future<List<LiveRoom>> getRecommendRooms({
    int page = 1,
    int pageSize = 30,
  }) async {
    return _roomList(
      page: page < 1 ? 1 : page,
    );
  }

  @override
  Future<List<LiveRoom>> getCategoryRooms(
    LiveArea category, {
    int page = 1,
    int pageSize = 30,
  }) async {
    final categoryId = category.areaId?.trim() ?? '';

    return _roomList(
      page: page < 1 ? 1 : page,
      category: categoryId.isEmpty || categoryId == 'all'
          ? null
          : categoryId,
    );
  }

  @override
  Future<bool> getLiveStatus({
    required String platform,
    required String roomId,
  }) async {
    final data = await _liveInfo(roomId);
    return _int(data['RESULT']) == 1;
  }

  @override
  Future<LiveRoom> getRoomDetail({
    required String roomId,
    required String platform,
  }) async {
    final data = await _liveInfo(roomId);
    final isLive = _int(data['RESULT']) == 1;

    final parts = roomId
        .split('/')
        .where((e) => e.trim().isNotEmpty)
        .toList();

    final bid = parts.isEmpty ? roomId : parts.first;

    final bno = data['BNO']?.toString() ??
        (parts.length > 1 ? parts[1] : '');

    final normalized = bno.isEmpty || bno == bid
        ? bid
        : '$bid/$bno';

    return LiveRoom(
      roomId: normalized,
      userId: bid,
      title: data['TITLE']?.toString() ??
          (isLive ? '' : '未开播 / 无法观看'),
      nick: data['BJNICK']?.toString() ?? bid,
      avatar: '',
      cover: '',
      watching: (
        data['CTUSER'] ??
        data['VIEWCNT'] ??
        '0'
      ).toString(),
      platform: platformId,
      status: isLive,
      liveStatus: isLive ? LiveStatus.live : LiveStatus.offline,
      link: '$_playHost/$normalized',
      data: data,
    );
  }

  @override
  Future<List<LivePlayQuality>> getPlayQualites({
    required LiveRoom detail,
  }) async {
    final data = detail.data is Map
        ? Map<String, dynamic>.from(detail.data as Map)
        : await _liveInfo(detail.roomId ?? '');

    if (_int(data['RESULT']) != 1) {
      return [];
    }

    final globalM3u8 = data['GLOBAL_M3U8']?.toString() ?? '';
    final presets = _list(data['VIEWPRESET']);

    if (globalM3u8.isNotEmpty || presets.isEmpty) {
      return [
        LivePlayQuality(
          quality: '原画',
          sort: 99999999,
          data: 'master',
        ),
      ];
    }

    final qualities = <LivePlayQuality>[];
    final seen = <String>{};

    for (final raw in presets) {
      final item = _map(raw);

      if (item == null) {
        continue;
      }

      final rawName = item['name']?.toString() ?? '';

      if (rawName.isEmpty || rawName == 'auto') {
        continue;
      }

      final name = _normalizeQuality(rawName);

      if (!seen.add(name)) {
        continue;
      }

      qualities.add(
        LivePlayQuality(
          quality: item['label']?.toString() ?? name,
          sort: _int(item['bps']),
          data: name,
        ),
      );
    }

    qualities.sort(
      (a, b) => b.sort.compareTo(a.sort),
    );

    if (qualities.isEmpty) {
      qualities.add(
        LivePlayQuality(
          quality: '原画',
          sort: 99999999,
          data: 'master',
        ),
      );
    }

    return qualities;
  }

  String _returnType(String cdn) {
    if (cdn.contains('gs_cdn')) {
      return 'gs_cdn_pc_web';
    }

    if (cdn.contains('lg_cdn')) {
      return 'lg_cdn_pc_web';
    }

    return cdn;
  }

  @override
  Future<List<String>> getPlayUrls({
    required LiveRoom detail,
    required LivePlayQuality quality,
  }) async {
    final roomId = detail.roomId ?? '';
    final parts = roomId
        .split('/')
        .where((e) => e.trim().isNotEmpty)
        .toList();

    if (parts.isEmpty) {
      return [];
    }

    final bid = parts.first;

    final info = detail.data is Map
        ? Map<String, dynamic>.from(detail.data as Map)
        : await _liveInfo(roomId);

    if (_int(info['RESULT']) != 1) {
      return [];
    }

    final globalM3u8 = info['GLOBAL_M3U8']?.toString() ?? '';

    if (globalM3u8.isNotEmpty) {
      return [globalM3u8];
    }

    final bno = info['BNO']?.toString() ??
        (parts.length > 1 ? parts[1] : '');

    final rmd = info['RMD']?.toString() ?? '';
    final cdn = info['CDN']?.toString() ?? '';

    if (bno.isEmpty || rmd.isEmpty || cdn.isEmpty) {
      return [];
    }

    final qualityName = _normalizeQuality(quality.data);

    final aidInfo = await _playerApiCall(
      bid: bid,
      bno: bno,
      type: 'aid',
      quality: qualityName,
    );

    if (_int(aidInfo['RESULT']) != 1) {
      return [];
    }

    final aid = aidInfo['AID']?.toString() ?? '';

    if (aid.isEmpty) {
      return [];
    }

    final baseRmd = rmd.endsWith('/')
        ? rmd.substring(0, rmd.length - 1)
        : rmd;

    final assignUri = Uri.parse(
      '$baseRmd/broad_stream_assign.html',
    ).replace(
      queryParameters: {
        'return_type': _returnType(cdn),
        'broad_key': '$bno-common-$qualityName-hls',
      },
    );

    final assign = await _getJson(
      assignUri,
      roomId: '$bid/$bno',
    );

    var viewUrl = assign['view_url']?.toString() ?? '';

    if (viewUrl.isEmpty) {
      return [];
    }

    var viewUri = Uri.parse(viewUrl);

    // iOS 本版不额外放开 ATS；如果 CDN 给 http，优先尝试同地址 https。
    if (viewUri.scheme.toLowerCase() == 'http') {
      viewUri = viewUri.replace(scheme: 'https');
    }

    if (viewUri.scheme.toLowerCase() != 'https') {
      return [];
    }

    final playUri = viewUri.replace(
      queryParameters: {
        ...viewUri.queryParameters,
        'aid': aid,
      },
    );

    return [playUri.toString()];
  }
}
