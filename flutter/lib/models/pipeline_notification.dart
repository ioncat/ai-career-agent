/// A pipeline / system event from `GET /api/notifications`.
///
/// Since the notifications phase-2 schema (backend d663850) `user_id` is null
/// for system events, and each event carries `severity`, `origin`, `code` and
/// `key`. Every field is read tolerantly: a missing or unexpected value falls
/// back to a default, so one odd row never breaks the poll.
class PipelineNotification {
  final int id;
  final int? userId;
  final int? vacancyId;
  final String event;
  final String title;
  final String body;
  final bool read;
  final String createdAt;

  /// success | info | warning | error. Old rows without it: derived from the
  /// event name (`*_failed` = error, `*_done` = success, else info).
  final String severity;

  /// user | auto | system; null when the backend did not say.
  final String? origin;

  /// Stable code of the event (e.g. a failure code); null when absent.
  final String? code;

  /// Idempotency key on the backend; null when absent.
  final String? key;

  const PipelineNotification({
    required this.id,
    this.userId,
    this.vacancyId,
    required this.event,
    required this.title,
    required this.body,
    required this.read,
    required this.createdAt,
    this.severity = 'info',
    this.origin,
    this.code,
    this.key,
  });

  static const _severities = {'success', 'info', 'warning', 'error'};

  factory PipelineNotification.fromJson(Map<String, dynamic> json) {
    String? str(String k) {
      final v = json[k];
      return v is String && v.isNotEmpty ? v : null;
    }

    int? integer(String k) {
      final v = json[k];
      return v is int ? v : (v is num ? v.toInt() : null);
    }

    final event = str('event') ?? '';
    final rawRead = json['read'];
    final sev = str('severity');
    return PipelineNotification(
      id: integer('id') ?? 0,
      userId: integer('user_id'),
      vacancyId: integer('vacancy_id'),
      event: event,
      title: str('title') ?? '',
      body: str('body') ?? '',
      read: rawRead == true || rawRead == 1,
      createdAt: str('created_at') ?? '',
      severity: sev != null && _severities.contains(sev)
          ? sev
          : _severityFromEvent(event),
      origin: str('origin'),
      code: str('code'),
      key: str('key'),
    );
  }

  static String _severityFromEvent(String event) {
    if (event.endsWith('_failed')) return 'error';
    if (event.endsWith('_done')) return 'success';
    return 'info';
  }

  PipelineNotification copyWith({bool? read}) => PipelineNotification(
    id: id,
    userId: userId,
    vacancyId: vacancyId,
    event: event,
    title: title,
    body: body,
    read: read ?? this.read,
    createdAt: createdAt,
    severity: severity,
    origin: origin,
    code: code,
    key: key,
  );

  bool get isFailure => severity == 'error';
  bool get isSuccess => severity == 'success';

  String get displayIcon {
    if (isFailure) return '❌';
    if (isSuccess) return '✅';
    return 'ℹ️';
  }
}
