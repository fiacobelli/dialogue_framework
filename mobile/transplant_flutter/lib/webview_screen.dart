import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:permission_handler/permission_handler.dart';
import 'app_config.dart';
import 'session_manager.dart';

class WebViewScreen extends StatefulWidget {
  const WebViewScreen({super.key});

  @override
  State<WebViewScreen> createState() => _WebViewScreenState();
}

class _WebViewScreenState extends State<WebViewScreen> {
  InAppWebViewController? _controller;
  Timer? _loadTimeout;
  Timer? _bootstrapTimeout;
  bool _isBootstrapping = true;
  bool _isLoading = true;
  bool _hasError = false;
  bool _microphoneGranted = false;
  String _status = 'Opening Ludi...';
  double _progress = 0;

  @override
  void initState() {
    super.initState();
    _log('initState');
    _bootstrap();
  }

  @override
  void dispose() {
    _log('dispose');
    _loadTimeout?.cancel();
    _bootstrapTimeout?.cancel();
    super.dispose();
  }

  void _log(String message) {
    debugPrint('[LUDI][webview] $message');
  }

  Future<void> _bootstrap() async {
    _log('bootstrap start');
    _bootstrapTimeout?.cancel();
    _bootstrapTimeout = Timer(const Duration(seconds: 5), () {
      if (!mounted || !_isBootstrapping) return;
      _log('bootstrap timeout fired');
      setState(() {
        _isBootstrapping = false;
        _status = 'Opening Ludi...';
      });
      _startLoadTimeout();
    });

    try {
      await SessionManager.clearOnLaunch().timeout(const Duration(seconds: 4));
    } catch (_) {
      _log('bootstrap clear failed or timed out; continuing');
      // If cache clearing fails, continue. The microsite is still usable.
    }
    await _ensureMicrophonePermission();
    if (!mounted) return;
    _bootstrapTimeout?.cancel();
    _log('bootstrap complete');
    setState(() {
      _isBootstrapping = false;
      _status = 'Opening Ludi...';
    });
    _startLoadTimeout();
  }

  Future<bool> _ensureMicrophonePermission() async {
    final status = await Permission.microphone.status;
    _log('microphone permission status: $status');
    if (status.isGranted) {
      _microphoneGranted = true;
      return true;
    }

    final requested = await Permission.microphone.request();
    _log('microphone permission requested: $requested');
    _microphoneGranted = requested.isGranted;
    return _microphoneGranted;
  }

  Future<PermissionResponse> _handleWebViewPermissionRequest(
    PermissionRequest request,
  ) async {
    _log('permission request: ${request.resources.join(",")}');
    final needsAudio = request.resources.any((resource) {
      final normalized = resource.toString().toLowerCase();
      return normalized.contains('audio') || normalized.contains('microphone');
    });

    if (needsAudio && !_microphoneGranted) {
      final granted = await _ensureMicrophonePermission();
      if (!granted) {
        _log('permission denied: microphone runtime permission unavailable');
        return PermissionResponse(
          resources: request.resources,
          action: PermissionResponseAction.DENY,
        );
      }
    }

    _log('permission granted: ${request.resources.join(",")}');
    return PermissionResponse(
      resources: request.resources,
      action: PermissionResponseAction.GRANT,
    );
  }

  void _startLoadTimeout() {
    _loadTimeout?.cancel();
    _log('load timeout armed');
    _loadTimeout = Timer(const Duration(seconds: 30), () {
      if (!mounted || !_isLoading) return;
      _log('load timeout fired');
      setState(() {
        _hasError = true;
        _isLoading = false;
        _status = 'Ludi is taking longer than expected.';
      });
    });
  }

  void _setLoading([String? status]) {
    _loadTimeout?.cancel();
    _startLoadTimeout();
    if (!mounted) return;
    _log('set loading: ${status ?? "Opening Ludi..."}');
    setState(() {
      _isLoading = true;
      _hasError = false;
      _status = status ?? 'Opening Ludi...';
      _progress = 0;
    });
  }

  void _setLoaded() {
    _loadTimeout?.cancel();
    if (_hasError) return;
    if (!mounted) return;
    _log('set loaded');
    setState(() {
      _isLoading = false;
      _hasError = false;
      _status = '';
      _progress = 100;
    });
  }

  void _setError(String status) {
    _loadTimeout?.cancel();
    if (!mounted) return;
    _log('set error: $status');
    setState(() {
      _isLoading = false;
      _hasError = true;
      _status = status;
    });
  }

  Future<void> _retry() async {
    _log('retry tapped');
    _setLoading('Retrying...');
    await _controller?.reload();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) async {
        if (didPop) return;
        final canGoBack = await _controller?.canGoBack() ?? false;
        if (canGoBack) _controller?.goBack();
      },
      child: Scaffold(
        body: Stack(
          children: [
            if (!_isBootstrapping)
              InAppWebView(
                initialUrlRequest: URLRequest(url: WebUri(kServerUrl)),
                initialSettings: InAppWebViewSettings(
                  mediaPlaybackRequiresUserGesture: false,
                  allowsInlineMediaPlayback: true,
                  javaScriptEnabled: true,
                  domStorageEnabled: true,
                  databaseEnabled: true,
                  useHybridComposition: true,
                ),
                onPermissionRequest: (controller, request) =>
                    _handleWebViewPermissionRequest(request),
                onWebViewCreated: (controller) {
                  _log('webview created');
                  _controller = controller;
                },
                onLoadStart: (controller, url) {
                  _log('load start: ${url?.toString() ?? "unknown"}');
                  _setLoading('Opening Ludi...');
                },
                onProgressChanged: (controller, progress) {
                  if (!mounted) return;
                  setState(() {
                    _progress = progress.toDouble();
                  });
                },
                onLoadStop: (controller, url) {
                  _log('load stop: ${url?.toString() ?? "unknown"}');
                  _setLoaded();
                },
                onReceivedError: (controller, request, error) {
                  if (request.isForMainFrame == true) {
                    _log('main frame error: ${error.description}');
                    _setError(
                      'Cannot reach the microsite. Check Wi-Fi and tap retry.',
                    );
                  }
                },
                onReceivedHttpError: (controller, request, errorResponse) {
                  if (request.isForMainFrame == true) {
                    _log('main frame http error: ${errorResponse.statusCode}');
                    _setError(
                      'The microsite returned an error. Check the connection and retry.',
                    );
                  }
                },
                onConsoleMessage: (controller, consoleMessage) {
                  _log(
                    'console: ${consoleMessage.messageLevel} ${consoleMessage.message}',
                  );
                },
              ),
            if (_isBootstrapping || _isLoading || _hasError)
              Positioned.fill(
                child: Container(
                  color: const Color(0xFFFFFCF7),
                  child: SafeArea(
                    child: Center(
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 420),
                        child: Padding(
                          padding: const EdgeInsets.all(24),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(
                                Icons.healing,
                                size: 56,
                                color: Color(0xFFE86F2C),
                              ),
                              const SizedBox(height: 18),
                              Text(
                                _hasError
                                    ? 'Could not load Ludi'
                                    : 'Loading Ludi...',
                                textAlign: TextAlign.center,
                                style: Theme.of(context).textTheme.headlineSmall
                                    ?.copyWith(
                                      fontWeight: FontWeight.w700,
                                      color: const Color(0xFF1C1917),
                                    ),
                              ),
                              const SizedBox(height: 12),
                              Text(
                                _status,
                                textAlign: TextAlign.center,
                                style: Theme.of(context).textTheme.bodyMedium
                                    ?.copyWith(
                                      color: const Color(0xFF78716C),
                                      height: 1.5,
                                    ),
                              ),
                              const SizedBox(height: 18),
                              if (_isBootstrapping)
                                LinearProgressIndicator(
                                  minHeight: 8,
                                  borderRadius: BorderRadius.circular(999),
                                )
                              else if (!_hasError)
                                LinearProgressIndicator(
                                  value: _progress > 0
                                      ? (_progress / 100.0).clamp(0.05, 1.0)
                                      : null,
                                  minHeight: 8,
                                  borderRadius: BorderRadius.circular(999),
                                ),
                              if (_hasError) ...[
                                const SizedBox(height: 10),
                                FilledButton(
                                  onPressed: _retry,
                                  child: const Text('Retry'),
                                ),
                              ],
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
