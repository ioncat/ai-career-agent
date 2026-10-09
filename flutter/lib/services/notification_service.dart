import 'package:local_notifier/local_notifier.dart';
import '../models/pipeline_notification.dart';

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
          ? '1 vacancy analysed'
          : '$count vacancies analysed',
    );
    await notification.show();
  }

  /// One OS notification for many events that arrived while the app was
  /// closed (notifications phase 3), instead of one per event.
  static Future<void> showSummary(int count) async {
    if (!_initialized) return;
    final notification = LocalNotification(
      title: 'Career Agent',
      body: '$count events while the app was closed',
    );
    await notification.show();
  }

  static Future<void> showPipelineEvent(PipelineNotification n) async {
    if (!_initialized) return;
    final notification = LocalNotification(
      title: n.title.isNotEmpty ? n.title : 'Career Agent',
      body: n.body.isNotEmpty ? n.body : n.event,
    );
    await notification.show();
  }
}
