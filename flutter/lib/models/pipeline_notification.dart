class PipelineNotification {
  final int id;
  final int userId;
  final int? vacancyId;
  final String event;
  final String title;
  final String body;
  final bool read;
  final String createdAt;

  const PipelineNotification({
    required this.id,
    required this.userId,
    this.vacancyId,
    required this.event,
    required this.title,
    required this.body,
    required this.read,
    required this.createdAt,
  });

  factory PipelineNotification.fromJson(Map<String, dynamic> json) {
    return PipelineNotification(
      id: json['id'] as int,
      userId: json['user_id'] as int,
      vacancyId: json['vacancy_id'] as int?,
      event: json['event'] as String? ?? '',
      title: json['title'] as String? ?? '',
      body: json['body'] as String? ?? '',
      read: (json['read'] as int? ?? 0) == 1,
      createdAt: json['created_at'] as String? ?? '',
    );
  }

  bool get isFailure => event.endsWith('_failed');
  bool get isSuccess => event.endsWith('_done');

  String get displayIcon {
    if (isFailure) return '❌';
    if (isSuccess) return '✅';
    return 'ℹ️';
  }
}
