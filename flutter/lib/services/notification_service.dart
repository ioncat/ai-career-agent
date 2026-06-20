import 'package:local_notifier/local_notifier.dart';

class NotificationService {
  static bool _initialized = false;

  static Future<void> init() async {
    if (_initialized) return;
    await localNotifier.setup(appName: 'Career Agent');
    _initialized = true;
  }

  static Future<void> showNewVacancies(int count) async {
    final notification = LocalNotification(
      title: 'Career Agent',
      body: count == 1
          ? '1 новая вакансия проанализирована'
          : '$count новых вакансий проанализировано',
    );
    await notification.show();
  }
}
