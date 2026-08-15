import 'dart:convert';
import 'dart:math';

import 'package:http/http.dart' as http;
import 'package:pure_live/common/models/live_area.dart';
import 'package:pure_live/common/models/live_room.dart';
import 'package:pure_live/core/interface/live_danmaku.dart';
import 'package:pure_live/core/interface/live_site.dart';
import 'package:pure_live/model/live_category.dart';
import 'package:pure_live/model/live_play_quality.dart';

class TwitchNoDanmaku extends LiveDanmaku {}

class TwitchSite extends LiveSite {
  static const String platformId = 'twitch';
  static const String _clientId = 'kimne78kx3ncx6brgo4mv6wki5h1ko';
  static const String _gqlUrl = 'https://gql.twitch.tv/gql';

  static const String _browseHash = '__BROWSE_HASH__';
  static const String _directoryHash = '__DIRECTORY_HASH__';
  static const String _channelShellHash = '__CHANNEL_HASH__';
  static const String _streamMetadataHash = '__METADATA_HASH__';

  static const String _userAgent =
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) '
      'Gecko/20100101 Firefox/115.0';

  static const String _playbackQuery =
      'query PlaybackAccessToken_Template('
      r'$login: String!, $isLive: Boolean!, $vodID: ID!, '
      r'$isVod: Boolean!, $playerType: String!, $platform: String!) { '
      'streamPlaybackAccessToken('
      r'channelName: $login, '
      r'params: {platform: $platform, playerBackend: "mediaplayer", '
      r'playerType: $playerType}) '
      r'@include(if: $isLive) { '
      'value signature authorization { isForbidden forbiddenReasonCode } '
      '__typename } '
      'videoPlaybackAccessToken('
      r'id: $vodID, '
      r'params: {platform: $platform, playerBackend: "mediaplayer", '
      r'playerType: $playerType}) '
      r'@include(if: $isVod) { value signature __typename }}';

  static List<LiveRoom>? _recommendCache;
  static DateTime? _recommendCacheAt;

  final String _deviceId = _randomString(16);

  @override
  String id = platformId;

  @override
  String name = 'Twitch';

  @override
  LiveDanmaku getDanmaku() => TwitchNoDanmaku();

  static String _randomString(int length) {
    const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
    final random = Random();
    return List.generate(
      length,
      (_) => chars[random.nextInt(chars.length)],
    ).join();
  }

  Map<String, String> _headers({
    String contentType = 'application/json',
  }) {
    return {
      'client-id': _clientId,
      'client-integrity': '',
      'device-id': _deviceId,
      'content-type': contentType,
      'user-agent': _userAgent,
      'accept-language': 'en-US',
      'origin': 'https://www.twitch.tv',
      'referer': 'https://www.twitch.tv/',
    };
  }

  Map<String, dynamic>? _map(dynamic value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    return null;
  }

  List<dynamic> _list(dynamic value) =>
      value is List ? value : const [];

  Future<Map<String, dynamic>> _persisted(
    String operation,
    String hash,
    Map<String, dynamic> variables,
  ) async {
    final response = await http
        .post(
          Uri.parse(_gqlUrl),
          headers: _headers(),
          body: jsonEncode({
            'operationName': operation,
            'variables': variables,
            'extensions': {
              'persistedQuery': {
                'version': 1,
                'sha256Hash': hash,
              },
            },
          }),
        )
        .timeout(const Duration(seconds: 20));

    if (response.statusCode < 200 ||
        response.statusCode >= 300) {
      throw Exception(
        'Twitch $operation HTTP ${response.statusCode}',
      );
    }

    final decoded = jsonDecode(response.body);

    if (decoded is! Map) {
      throw Exception('Twitch $operation 返回格式异常');
    }

    final errors = decoded['errors'];
    if (errors is List && errors.isNotEmpty) {
      throw Exception(
        'Twitch $operation: ${errors.toString()}',
      );
    }

    final data = _map(decoded['data']);
    if (data == null) {
      throw Exception('Twitch $operation 没有 data');
    }

    return data;
  }

  Future<List<Map<String, dynamic>>> _directories({
    int limit = 60,
  }) async {
    final data = await _persisted(
      'BrowsePage_AllDirectories',
      _browseHash,
      {
        'cursor': null,
        'limit': limit,
        'options': {'sort': 'RELEVANCE'},
      },
    );

    final connection = _map(data['directoriesWithTags']);
    final result = <Map<String, dynamic>>[];

    for (final rawEdge in _list(connection?['edges'])) {
      final edge = _map(rawEdge);
      final node = _map(edge?['node']);
      if (node == null) continue;

      final slug = node['slug']?.toString().trim() ?? '';
      if (slug.isNotEmpty) result.add(node);
    }

    return result;
  }

  Future<List<LiveRoom>> _categoryStreams(
    String slug, {
    int limit = 30,
  }) async {
    final data = await _persisted(
      'DirectoryPage_Game',
      _directoryHash,
      {
        'slug': slug,
        'options': {'sort': 'VIEWER_COUNT'},
        'sortTypeIsRecency': false,
        'limit': limit,
        'includeIsDJ': true,
      },
    );

    final game = _map(data['game']);
    if (game == null) return [];

    final streams = _map(game['streams']);
    final result = <LiveRoom>[];

    for (final rawEdge in _list(streams?['edges'])) {
      final edge = _map(rawEdge);
      final node = _map(edge?['node']);
      if (node == null) continue;

      final room = _streamToRoom(node);
      if ((room.roomId ?? '').isNotEmpty) {
        result.add(room);
      }
    }

    return result;
  }

  LiveRoom _streamToRoom(Map<String, dynamic> node) {
    final broadcaster = _map(node['broadcaster']);
    final game = _map(node['game']);

    final login =
        broadcaster?['login']?.toString() ?? '';
    final displayName =
        broadcaster?['displayName']?.toString() ?? login;

    return LiveRoom(
      roomId: login,
      userId: broadcaster?['id']?.toString() ?? login,
      title: node['title']?.toString() ?? '',
      nick: displayName,
      avatar:
          broadcaster?['profileImageURL']?.toString() ?? '',
      cover: node['previewImageURL']?.toString() ?? '',
      area:
          game?['displayName']?.toString() ??
          game?['name']?.toString() ??
          '',
      watching:
          node['viewersCount']?.toString() ?? '0',
      platform: platformId,
      status: true,
      liveStatus: LiveStatus.live,
      link: 'https://www.twitch.tv/$login',
    );
  }

  int _safePage(int page) => page < 1 ? 1 : page;

  int _safePageSize(int pageSize) {
    if (pageSize < 1) return 30;
    if (pageSize > 100) return 100;
    return pageSize;
  }

  List<LiveRoom> _slice(
    List<LiveRoom> rooms,
    int page,
    int pageSize,
  ) {
    final safePage = _safePage(page);
    final safeSize = _safePageSize(pageSize);
    final start = (safePage - 1) * safeSize;

    if (start >= rooms.length) return [];

    return rooms.sublist(
      start,
      min(start + safeSize, rooms.length),
    );
  }

  @override
  Future<List<LiveCategory>> getCategores(
    int page,
    int pageSize,
  ) async {
    final directories = await _directories(limit: 60);
    final children = <LiveArea>[];

    for (final item in directories) {
      final slug = item['slug']?.toString() ?? '';
      final displayName =
          item['displayName']?.toString() ??
          item['name']?.toString() ??
          slug;

      if (slug.isEmpty || displayName.isEmpty) continue;

      children.add(
        LiveArea(
          platform: platformId,
          areaType: 'twitch_game',
          typeName: '热门分类',
          areaId: slug,
          areaName: displayName,
          areaPic: item['avatarURL']?.toString() ?? '',
          shortName: displayName,
        ),
      );
    }

    return [
      LiveCategory(
        id: 'twitch_games',
        name: '热门分类',
        children: children,
      ),
    ];
  }

  @override
  Future<List<LiveRoom>> getCategoryRooms(
    LiveArea category, {
    int page = 1,
    int pageSize = 30,
  }) async {
    final slug = category.areaId?.trim() ?? '';
    if (slug.isEmpty) return [];

    final safePage = _safePage(page);
    final safeSize = _safePageSize(pageSize);
    final fetchLimit = min(safePage * safeSize, 100);

    final rooms = await _categoryStreams(
      slug,
      limit: fetchLimit,
    );

    return _slice(rooms, safePage, safeSize);
  }

  Future<List<LiveRoom>> _loadRecommendRooms() async {
    final now = DateTime.now();

    if (_recommendCache != null &&
        _recommendCacheAt != null &&
        now.difference(_recommendCacheAt!).inSeconds < 90) {
      return _recommendCache!;
    }

    final directories = await _directories(limit: 6);
    final tasks = <Future<List<LiveRoom>>>[];

    for (final item in directories) {
      final slug = item['slug']?.toString() ?? '';
      if (slug.isEmpty) continue;

      tasks.add(
        _categoryStreams(slug, limit: 15),
      );
    }

    final groups = await Future.wait(tasks);
    final dedup = <String, LiveRoom>{};

    for (final group in groups) {
      for (final room in group) {
        final key = room.roomId?.toLowerCase() ?? '';
        if (key.isEmpty) continue;
        dedup.putIfAbsent(key, () => room);
      }
    }

    final rooms = dedup.values.toList();

    rooms.sort((a, b) {
      final av = int.tryParse(a.watching ?? '0') ?? 0;
      final bv = int.tryParse(b.watching ?? '0') ?? 0;
      return bv.compareTo(av);
    });

    _recommendCache = rooms;
    _recommendCacheAt = now;

    return rooms;
  }

  @override
  Future<List<LiveRoom>> getRecommendRooms({
    int page = 1,
    int pageSize = 30,
  }) async {
    final rooms = await _loadRecommendRooms();
    return _slice(rooms, page, pageSize);
  }

  Future<Map<String, dynamic>?> _channelShell(
    String roomId,
  ) async {
    final data = await _persisted(
      'ChannelShell',
      _channelShellHash,
      {'login': roomId},
    );

    final user = _map(data['userOrError']);

    if (user == null ||
        (user['login']?.toString() ?? '').isEmpty) {
      return null;
    }

    return user;
  }

  Future<Map<String, dynamic>?> _streamMetadata(
    String roomId,
  ) async {
    try {
      final data = await _persisted(
        'StreamMetadata',
        _streamMetadataHash,
        {
          'channelLogin': roomId,
          'includeIsDJ': true,
        },
      );
      return _map(data['user']);
    } catch (_) {
      return null;
    }
  }

  @override
  Future<bool> getLiveStatus({
    required String platform,
    required String roomId,
  }) async {
    final user = await _channelShell(roomId);
    return user != null && user['stream'] != null;
  }

  @override
  Future<LiveRoom> getRoomDetail({
    required String roomId,
    required String platform,
  }) async {
    final login = roomId.trim();
    final user = await _channelShell(login);

    if (user == null) {
      return LiveRoom(
        roomId: login,
        userId: login,
        title: '未开播 / 离线',
        nick: login,
        platform: platformId,
        status: false,
        liveStatus: LiveStatus.offline,
        link: 'https://www.twitch.tv/$login',
      );
    }

    final stream = _map(user['stream']);
    final isLive = stream != null;

    final metadata = await _streamMetadata(login);
    final metaStream = _map(metadata?['stream']);
    final game = _map(metaStream?['game']);
    final lastBroadcast = _map(metadata?['lastBroadcast']);

    final normalizedLogin =
        user['login']?.toString() ?? login;

    return LiveRoom(
      roomId: normalizedLogin,
      userId: user['id']?.toString() ?? normalizedLogin,
      title:
          lastBroadcast?['title']?.toString() ??
          (isLive ? 'Twitch 直播' : '未开播 / 离线'),
      nick:
          user['displayName']?.toString() ?? normalizedLogin,
      avatar:
          user['profileImageURL']?.toString() ??
          metadata?['profileImageURL']?.toString() ??
          '',
      cover:
          isLive
              ? 'https://static-cdn.jtvnw.net/'
                  'previews-ttv/live_user_'
                  '${normalizedLogin.toLowerCase()}-640x360.jpg'
              : '',
      area: game?['name']?.toString() ?? '',
      watching:
          stream?['viewersCount']?.toString() ?? '0',
      platform: platformId,
      status: isLive,
      liveStatus:
          isLive ? LiveStatus.live : LiveStatus.offline,
      link:
          'https://www.twitch.tv/$normalizedLogin',
    );
  }

  Future<Map<String, dynamic>?> _playbackToken(
    String roomId,
  ) async {
    final response = await http
        .post(
          Uri.parse(_gqlUrl),
          headers: _headers(
            contentType: 'text/plain;charset=UTF-8',
          ),
          body: jsonEncode({
            'operationName':
                'PlaybackAccessToken_Template',
            'query': _playbackQuery,
            'variables': {
              'isLive': true,
              'login': roomId,
              'isVod': false,
              'vodID': '',
              'playerType': 'site',
              'platform': 'web',
            },
          }),
        )
        .timeout(const Duration(seconds: 20));

    if (response.statusCode < 200 ||
        response.statusCode >= 300) {
      throw Exception(
        'Twitch Playback HTTP ${response.statusCode}',
      );
    }

    final decoded = jsonDecode(response.body);

    if (decoded is! Map) {
      throw Exception('Twitch Playback 返回格式异常');
    }

    final errors = decoded['errors'];
    if (errors is List && errors.isNotEmpty) {
      throw Exception(
        'Twitch Playback: ${errors.toString()}',
      );
    }

    final data = _map(decoded['data']);
    final token = _map(
      data?['streamPlaybackAccessToken'],
    );

    if (token == null) return null;

    final authorization = _map(
      token['authorization'],
    );

    if (authorization?['isForbidden'] == true) {
      throw Exception(
        'Twitch 播放被限制：'
        '${authorization?['forbiddenReasonCode']}',
      );
    }

    return token;
  }

  String _buildMasterUrl({
    required String roomId,
    required String signature,
    required String token,
  }) {
    final sessionIds = [
      'bdd22331a986c7f1073628f2fc5b19da',
      '064bc3ff1722b6f53b0b5b8c01e46ca5',
    ];

    return Uri.https(
      'usher.ttvnw.net',
      '/api/channel/hls/${roomId.toLowerCase()}.m3u8',
      {
        'acmb': 'e30=',
        'allow_audio_only': 'true',
        'allow_source': 'true',
        'browser_family': 'firefox',
        'browser_version': '124.0',
        'cdm': 'wv',
        'fast_bread': 'true',
        'os_name': 'Windows',
        'os_version': 'NT 10.0',
        'p': (1000000 + Random().nextInt(8999999)).toString(),
        'platform': 'web',
        'play_session_id':
            sessionIds[Random().nextInt(sessionIds.length)],
        'player_backend': 'mediaplayer',
        'player_version': '1.28.0-rc.1',
        'playlist_include_framerate': 'true',
        'reassignments_supported': 'true',
        'sig': signature,
        'token': token,
        'transcode_mode': 'cbr_v1',
      },
    ).toString();
  }

  Future<String?> _masterUrl(String roomId) async {
    final tokenData = await _playbackToken(roomId);
    if (tokenData == null) return null;

    final signature =
        tokenData['signature']?.toString() ?? '';
    final token =
        tokenData['value']?.toString() ?? '';

    if (signature.isEmpty || token.isEmpty) {
      return null;
    }

    return _buildMasterUrl(
      roomId: roomId,
      signature: signature,
      token: token,
    );
  }

  @override
  Future<List<LivePlayQuality>> getPlayQualites({
    required LiveRoom detail,
  }) async {
    final roomId = detail.roomId?.trim() ?? '';

    if (roomId.isEmpty || detail.status == false) {
      return [];
    }

    final master = await _masterUrl(roomId);

    if (master == null || master.isEmpty) {
      return [];
    }

    final response = await http
        .get(
          Uri.parse(master),
          headers: _headers(
            contentType: 'text/plain;charset=UTF-8',
          ),
        )
        .timeout(const Duration(seconds: 20));

    if (response.statusCode < 200 ||
        response.statusCode >= 300) {
      throw Exception(
        'Twitch M3U8 HTTP ${response.statusCode}',
      );
    }

    final qualities =
        _parseMasterPlaylist(response.body, master);

    if (qualities.isNotEmpty) {
      return qualities;
    }

    return [
      LivePlayQuality(
        quality: '自动',
        sort: 10000000,
        data: master,
      ),
    ];
  }

  @override
  Future<List<String>> getPlayUrls({
    required LiveRoom detail,
    required LivePlayQuality quality,
  }) async {
    final selectedUrl =
        quality.data?.toString() ?? '';

    if (selectedUrl.isNotEmpty) {
      return [selectedUrl];
    }

    final roomId = detail.roomId?.trim() ?? '';
    if (roomId.isEmpty) return [];

    final master = await _masterUrl(roomId);
    return (master == null || master.isEmpty)
        ? []
        : [master];
  }

  List<LivePlayQuality> _parseMasterPlaylist(
    String body,
    String masterUrl,
  ) {
    final result = <LivePlayQuality>[];
    final mediaNames = <String, String>{};
    final lines = const LineSplitter().convert(body);

    for (final raw in lines) {
      final line = raw.trim();

      if (!line.startsWith('#EXT-X-MEDIA:')) {
        continue;
      }

      final group = RegExp(
        r'GROUP-ID="([^"]+)"',
      ).firstMatch(line)?.group(1);

      final name = RegExp(
        r'NAME="([^"]+)"',
      ).firstMatch(line)?.group(1);

      if (group != null && name != null) {
        mediaNames[group] = name;
      }
    }

    final used = <String>{};
    final base = Uri.parse(masterUrl);

    for (var i = 0; i < lines.length; i++) {
      final line = lines[i].trim();

      if (!line.startsWith('#EXT-X-STREAM-INF:')) {
        continue;
      }

      String urlLine = '';

      for (var j = i + 1; j < lines.length; j++) {
        final candidate = lines[j].trim();

        if (candidate.isEmpty ||
            candidate.startsWith('#')) {
          continue;
        }

        urlLine = candidate;
        break;
      }

      if (urlLine.isEmpty) continue;

      final resolved =
          Uri.parse(urlLine).isAbsolute
              ? urlLine
              : base.resolve(urlLine).toString();

      if (!used.add(resolved)) continue;

      final bandwidth =
          int.tryParse(
            RegExp(
              r'BANDWIDTH=(\d+)',
            ).firstMatch(line)?.group(1) ??
                '',
          ) ??
          0;

      final resolution = RegExp(
        r'RESOLUTION=(\d+)x(\d+)',
      ).firstMatch(line);

      final height =
          int.tryParse(resolution?.group(2) ?? '') ??
          0;

      final fps =
          double.tryParse(
            RegExp(
              r'FRAME-RATE=([0-9.]+)',
            ).firstMatch(line)?.group(1) ??
                '',
          );

      final videoGroup = RegExp(
        r'VIDEO="([^"]+)"',
      ).firstMatch(line)?.group(1);

      if (videoGroup == 'audio_only') {
        continue;
      }

      String label = videoGroup == null
          ? ''
          : (mediaNames[videoGroup] ?? videoGroup);

      if (height > 0) {
        label = '${height}p';
        if (fps != null && fps >= 50) {
          label += '60';
        }
      }

      final sourceName =
          videoGroup == null
              ? null
              : mediaNames[videoGroup];

      if (videoGroup == 'chunked' ||
          sourceName?.toLowerCase().contains('source') ==
              true) {
        label =
            label.isEmpty ? '原画' : '$label（原画）';
      }

      if (label.isEmpty) label = '自动';

      result.add(
        LivePlayQuality(
          quality: label,
          sort:
              bandwidth > 0
                  ? bandwidth
                  : height * 1000 +
                      (fps?.round() ?? 0),
          data: resolved,
        ),
      );
    }

    result.sort(
      (a, b) => b.sort.compareTo(a.sort),
    );

    return result;
  }
}
