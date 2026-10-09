import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/models/pipeline_notification.dart';
import 'package:career_agent/utils/notification_cursor.dart';

PipelineNotification _n(int id, String at) => PipelineNotification(
  id: id,
  event: 'cv_done',
  title: 't',
  body: '',
  read: false,
  createdAt: at,
);

void main() {
  const t1 = '2026-10-09T10:00:00Z';
  const t2 = '2026-10-09T10:05:00Z';

  test('events after the cursor are new, older ones are not', () {
    const c = NotificationCursor(t1, {1});
    expect(c.isNew(_n(2, t2)), isTrue);
    expect(c.isNew(_n(0, '2026-10-09T09:00:00Z')), isFalse);
  });

  test('at the exact cursor time only unseen ids are new', () {
    const c = NotificationCursor(t1, {1});
    expect(c.isNew(_n(1, t1)), isFalse);
    expect(c.isNew(_n(7, t1)), isTrue);
  });

  test('advance moves to the newest time and keeps the ids seen there', () {
    final c = const NotificationCursor(t1, {
      1,
    }).advance([_n(2, t2), _n(3, t2), _n(1, t1)]);
    expect(c.ts, t2);
    expect(c.idsAtTs, {2, 3});
  });

  test('advance at the same time adds ids to the existing ones', () {
    final c = const NotificationCursor(t1, {1}).advance([_n(4, t1)]);
    expect(c.ts, t1);
    expect(c.idsAtTs, {1, 4});
  });

  test('a naive and a Z timestamp of the same instant compare equal', () {
    const c = NotificationCursor('2026-10-09T10:00:00', {1});
    expect(c.isNew(_n(1, t1)), isFalse);
  });

  test('first run: existing events are history, the next one is new', () {
    final now = DateTime.utc(2026, 10, 9, 11);
    final c = NotificationCursor.firstRun([_n(1, t1), _n(2, t2)], now);
    expect(c.isNew(_n(1, t1)), isFalse);
    expect(c.isNew(_n(2, t2)), isFalse);
    expect(c.isNew(_n(3, '2026-10-09T11:00:01Z')), isTrue);
  });

  test('encode and decode round-trip; empty or missing ts is no cursor', () {
    const c = NotificationCursor(t1, {3, 1});
    final d = NotificationCursor.decode(c.ts, c.encodeIds())!;
    expect(d.ts, t1);
    expect(d.idsAtTs, {1, 3});
    expect(NotificationCursor.decode(null, '1'), isNull);
    expect(NotificationCursor.decode('', ''), isNull);
    expect(NotificationCursor.decode(t1, 'x,2')!.idsAtTs, {2});
  });

  test('more than 3 events at startup become one summary', () {
    final four = [for (var i = 0; i < 4; i++) _n(i, t2)];
    final s = splitFresh(four, startup: true);
    expect(s.individual, isEmpty);
    expect(s.summaryCount, 4);
  });

  test('3 at startup, or many later on, are shown one by one', () {
    final three = [for (var i = 0; i < 3; i++) _n(i, t2)];
    expect(splitFresh(three, startup: true).summaryCount, 0);
    final five = [for (var i = 0; i < 5; i++) _n(i, t2)];
    expect(splitFresh(five, startup: false).individual.length, 5);
  });
}
