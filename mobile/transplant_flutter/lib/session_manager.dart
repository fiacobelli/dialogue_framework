import 'package:flutter/foundation.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

class SessionManager {
  static Future<void> clearOnLaunch() async {
    debugPrint('[LUDI][session] clearing cookies and cache');
    await CookieManager.instance().deleteAllCookies();
    await InAppWebViewController.clearAllCache();
    debugPrint('[LUDI][session] clear complete');
  }
}
