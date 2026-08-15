import 'dart:convert';

import 'package:cookie_jar/cookie_jar.dart';
import 'package:dio/dio.dart';
import 'package:dio_cookie_manager/dio_cookie_manager.dart';
import 'package:pure_live/common/index.dart';

class SoopAccountSettingsPage extends StatefulWidget {
  const SoopAccountSettingsPage({super.key});

  @override
  State<SoopAccountSettingsPage> createState() =>
      _SoopAccountSettingsPageState();
}

class _SoopAccountSettingsPageState extends State<SoopAccountSettingsPage> {
  static const String _loginUrl =
      'https://login.sooplive.com/app/LoginAction.php';
  static const String _authCheckUrl =
      'https://afevent2.sooplive.com/api/get_private_info.php';
  static const String _userAgent =
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) '
      'Gecko/20100101 Firefox/122.0';

  late final TextEditingController _cookieController;
  final TextEditingController _usernameController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();

  bool _loading = false;
  bool _showPassword = false;
  String _statusText = '尚未验证';
  bool? _statusOk;

  @override
  void initState() {
    super.initState();

    _cookieController = TextEditingController(
      text: SettingsService.to.cookieManager.soopCookie.v,
    );

    if (_cookieController.text.trim().isNotEmpty) {
      _statusText = '已保存 Cookie，尚未验证';
    }
  }

  @override
  void dispose() {
    _cookieController.dispose();
    _usernameController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  Map<String, dynamic>? _asMap(dynamic value) {
    if (value is Map<String, dynamic>) {
      return value;
    }

    if (value is Map) {
      return Map<String, dynamic>.from(value);
    }

    if (value is String && value.trim().isNotEmpty) {
      try {
        final decoded = jsonDecode(value);

        if (decoded is Map) {
          return Map<String, dynamic>.from(decoded);
        }
      } catch (_) {}
    }

    return null;
  }

  String _normalizeCookie(String value) {
    var result = value.trim();

    if (result.toLowerCase().startsWith('cookie:')) {
      result = result.substring(7).trim();
    }

    result = result
        .replaceAll('\r', '')
        .replaceAll('\n', ' ')
        .trim();

    while (result.contains('  ')) {
      result = result.replaceAll('  ', ' ');
    }

    return result;
  }

  Dio _newDio({String cookie = ''}) {
    final headers = <String, dynamic>{
      'user-agent': _userAgent,
      'accept-language': 'ko-KR,ko;q=0.9,en-US;q=0.7,en;q=0.6',
      'referer': 'https://play.sooplive.com/',
      'origin': 'https://play.sooplive.com',
    };

    if (cookie.trim().isNotEmpty) {
      headers['cookie'] = cookie.trim();
    }

    return Dio(
      BaseOptions(
        headers: headers,
        connectTimeout: const Duration(seconds: 20),
        receiveTimeout: const Duration(seconds: 20),
        sendTimeout: const Duration(seconds: 20),
        followRedirects: true,
        validateStatus: (status) =>
            status != null && status >= 200 && status < 400,
      ),
    );
  }

  Future<String?> _verifyWithDio(Dio dio) async {
    final response = await dio.get(_authCheckUrl);

    final root = _asMap(response.data);
    final channel = _asMap(root?['CHANNEL']);

    final loginId = channel?['LOGIN_ID']?.toString().trim() ?? '';

    return loginId.isEmpty ? null : loginId;
  }

  void _setStatus(String text, bool? ok) {
    if (!mounted) return;

    setState(() {
      _statusText = text;
      _statusOk = ok;
    });
  }

  void _setLoading(bool value) {
    if (!mounted) return;

    setState(() {
      _loading = value;
    });
  }

  Future<void> _saveCookie() async {
    final cookie = _normalizeCookie(_cookieController.text);

    if (cookie.isEmpty) {
      ToastUtil.show('请输入 SOOP Cookie');
      return;
    }

    SettingsService.to.cookieManager.soopCookie.v = cookie;
    _cookieController.text = cookie;

    _setStatus('Cookie 已保存，尚未验证', null);
    ToastUtil.show('SOOP Cookie 已保存');
  }

  Future<void> _verifySavedCookie() async {
    final cookie = _normalizeCookie(_cookieController.text);

    if (cookie.isEmpty) {
      ToastUtil.show('请先输入 Cookie');
      return;
    }

    _setLoading(true);

    try {
      final dio = _newDio(cookie: cookie);
      final loginId = await _verifyWithDio(dio);

      if (loginId == null) {
        _setStatus('Cookie 无效或已过期', false);
        ToastUtil.show('SOOP Cookie 无效或已过期');
        return;
      }

      SettingsService.to.cookieManager.soopCookie.v = cookie;
      _cookieController.text = cookie;

      _setStatus('已登录：$loginId', true);
      ToastUtil.show('SOOP Cookie 验证成功');
    } catch (e) {
      _setStatus('Cookie 验证失败', false);
      ToastUtil.show('SOOP Cookie 验证失败：$e');
    } finally {
      _setLoading(false);
    }
  }

  Future<void> _loginWithAccount() async {
    final username = _usernameController.text.trim();
    final password = _passwordController.text;

    if (username.isEmpty || password.isEmpty) {
      ToastUtil.show('请输入 SOOP 账号和密码');
      return;
    }

    _setLoading(true);

    try {
      final jar = CookieJar();
      final dio = _newDio();

      dio.interceptors.add(CookieManager(jar));

      final response = await dio.post(
        _loginUrl,
        data: {
          'szWork': 'login',
          'szType': 'json',
          'szUid': username,
          'szPassword': password,
          'isSaveId': 'true',
          'isSavePw': 'false',
          'isSaveJoin': 'false',
          'isLoginRetain': 'Y',
        },
        options: Options(
          contentType: Headers.formUrlEncodedContentType,
        ),
      );

      final root = _asMap(response.data);
      final result = int.tryParse(root?['RESULT']?.toString() ?? '') ?? 0;

      if (result != 1) {
        final message = root?['MESSAGE']?.toString() ??
            root?['RESULTMSG']?.toString() ??
            'RESULT=$result';

        _setStatus('账号登录失败', false);
        ToastUtil.show('SOOP 登录失败：$message');
        return;
      }

      final loginId = await _verifyWithDio(dio);

      if (loginId == null) {
        _setStatus('登录请求成功，但身份验证失败', false);
        ToastUtil.show('SOOP 登录后身份验证失败');
        return;
      }

      var cookies = await jar.loadForRequest(Uri.parse(_authCheckUrl));

      if (cookies.isEmpty) {
        cookies = await jar.loadForRequest(
          Uri.parse('https://www.sooplive.com/'),
        );
      }

      if (cookies.isEmpty) {
        throw Exception('登录成功，但没有取得 SOOP Cookie');
      }

      final cookie = cookies
          .map((item) => '${item.name}=${item.value}')
          .join('; ');

      SettingsService.to.cookieManager.soopCookie.v = cookie;
      _cookieController.text = cookie;

      // 密码只用于这一次登录，不保存。
      _passwordController.clear();

      _setStatus('已登录：$loginId', true);
      ToastUtil.show('SOOP 登录成功，Cookie 已保存');
    } catch (e) {
      _setStatus('账号登录失败', false);
      ToastUtil.show('SOOP 登录失败：$e');
    } finally {
      _setLoading(false);
    }
  }

  void _clearCookie() {
    SettingsService.to.cookieManager.soopCookie.v = '';
    _cookieController.clear();

    _setStatus('已清除 SOOP Cookie', null);
    ToastUtil.show('SOOP Cookie 已清除');
  }

  Widget _statusCard(BuildContext context) {
    final theme = Theme.of(context);

    final Color color;

    if (_statusOk == true) {
      color = Colors.green;
    } else if (_statusOk == false) {
      color = theme.colorScheme.error;
    } else {
      color = theme.colorScheme.primary;
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: color.withValues(alpha: 0.25),
        ),
      ),
      child: Row(
        children: [
          Icon(
            _statusOk == true
                ? Icons.verified_user_outlined
                : _statusOk == false
                    ? Icons.error_outline
                    : Icons.info_outline,
            color: color,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              _statusText,
              style: TextStyle(
                color: color,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          if (_loading)
            const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(
                strokeWidth: 2,
              ),
            ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('SOOP 登录 / Cookie'),
      ),
      body: ListView(
        physics: const BouncingScrollPhysics(),
        padding: const EdgeInsets.all(16),
        children: [
          _statusCard(context),
          const SizedBox(height: 20),

          Text(
            '方式一：账号登录',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            '账号和密码会直接提交到 SOOP 官方登录接口。'
            '密码不会保存；登录成功后只在本机保存 Cookie。',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _usernameController,
            enabled: !_loading,
            autocorrect: false,
            decoration: const InputDecoration(
              labelText: 'SOOP 账号',
              border: OutlineInputBorder(),
              prefixIcon: Icon(Icons.person_outline),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _passwordController,
            enabled: !_loading,
            obscureText: !_showPassword,
            autocorrect: false,
            enableSuggestions: false,
            decoration: InputDecoration(
              labelText: 'SOOP 密码',
              border: const OutlineInputBorder(),
              prefixIcon: const Icon(Icons.lock_outline),
              suffixIcon: IconButton(
                onPressed: () {
                  setState(() {
                    _showPassword = !_showPassword;
                  });
                },
                icon: Icon(
                  _showPassword
                      ? Icons.visibility_off
                      : Icons.visibility,
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: _loading ? null : _loginWithAccount,
            icon: const Icon(Icons.login),
            label: const Text('登录并保存 Cookie'),
          ),

          const SizedBox(height: 28),
          const Divider(),
          const SizedBox(height: 20),

          Text(
            '方式二：手动 Cookie',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            '也可以在浏览器登录 SOOP 后，复制请求头中的 Cookie 值粘贴到这里。'
            '可以带或不带 “Cookie:” 前缀。',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _cookieController,
            enabled: !_loading,
            minLines: 4,
            maxLines: 8,
            autocorrect: false,
            enableSuggestions: false,
            decoration: const InputDecoration(
              labelText: 'SOOP Cookie',
              hintText:
                  'AuthTicket=...; BbsTicket=...; UserTicket=...',
              alignLabelWithHint: true,
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              FilledButton.tonalIcon(
                onPressed: _loading ? null : _saveCookie,
                icon: const Icon(Icons.save_outlined),
                label: const Text('保存 Cookie'),
              ),
              FilledButton.tonalIcon(
                onPressed: _loading ? null : _verifySavedCookie,
                icon: const Icon(Icons.verified_outlined),
                label: const Text('验证 Cookie'),
              ),
              TextButton.icon(
                onPressed: _loading ? null : _clearCookie,
                icon: const Icon(Icons.delete_outline),
                label: const Text('清除'),
              ),
            ],
          ),

          const SizedBox(height: 24),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Theme.of(context)
                  .colorScheme
                  .surfaceContainerHighest
                  .withValues(alpha: 0.35),
              borderRadius: BorderRadius.circular(10),
            ),
            child: const Text(
              '说明：普通公开 SOOP 直播不一定需要登录。'
              '保存 Cookie 后，SOOP 的房间信息、清晰度、AID、'
              'HLS 和播放器请求都会自动携带它，主要用于需要登录权限的直播或更高画质。',
            ),
          ),
        ],
      ),
    );
  }
}
