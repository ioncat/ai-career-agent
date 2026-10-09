import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/models/pipeline_notification.dart';

void main() {
  test('a system event with a null user_id parses', () {
    final n = PipelineNotification.fromJson({
      'id': 5,
      'user_id': null,
      'event': 'feed_failing',
      'title': 'Feed failing',
      'read': 0,
      'created_at': '2026-10-09T10:00:00Z',
      'severity': 'warning',
      'origin': 'system',
      'code': 'feed_failing',
      'key': 'monitor:djinni:failing',
    });
    expect(n.userId, isNull);
    expect(n.severity, 'warning');
    expect(n.origin, 'system');
    expect(n.code, 'feed_failing');
    expect(n.key, 'monitor:djinni:failing');
    expect(n.isFailure, isFalse);
  });

  test('an old row without the new keys keeps the old meaning', () {
    final failed = PipelineNotification.fromJson({
      'id': 1,
      'user_id': 1,
      'event': 'cv_failed',
    });
    expect(failed.severity, 'error');
    expect(failed.isFailure, isTrue);
    expect(failed.origin, isNull);
    final done = PipelineNotification.fromJson({'id': 2, 'event': 'cv_done'});
    expect(done.isSuccess, isTrue);
  });

  test('unknown severity and odd types fall back to defaults', () {
    final n = PipelineNotification.fromJson({
      'id': 3,
      'event': 'analysis_done',
      'severity': 'shouting',
      'title': 42,
      'read': true,
    });
    expect(n.severity, 'success');
    expect(n.title, '');
    expect(n.read, isTrue);
  });

  test('copyWith keeps the new fields', () {
    final n = PipelineNotification.fromJson({
      'id': 4,
      'event': 'x',
      'severity': 'error',
      'origin': 'auto',
      'code': 'llm_timeout',
      'key': 'k',
    }).copyWith(read: true);
    expect(n.read, isTrue);
    expect(
      [n.severity, n.origin, n.code, n.key],
      ['error', 'auto', 'llm_timeout', 'k'],
    );
  });
}
