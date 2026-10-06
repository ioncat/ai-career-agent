import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/utils/date_range.dart';

// Date range + calendar span shown under the Analytics counters (2026-10-06).

void main() {
  group('calendarSpan', () {
    test('months and days', () {
      expect(calendarSpan(DateTime(2026, 1, 1), DateTime(2026, 10, 6)), '9 months 5 days');
    });

    test('same day and singular units', () {
      expect(calendarSpan(DateTime(2026, 5, 5), DateTime(2026, 5, 5)), 'same day');
      expect(calendarSpan(DateTime(2026, 5, 5), DateTime(2026, 5, 6)), '1 day');
      expect(calendarSpan(DateTime(2026, 5, 5), DateTime(2026, 6, 5)), '1 month');
    });

    test('whole months have no days part', () {
      expect(calendarSpan(DateTime(2026, 3, 10), DateTime(2026, 9, 10)), '6 months');
    });

    test('years once the span reaches 12 months', () {
      expect(calendarSpan(DateTime(2025, 1, 1), DateTime(2026, 3, 2)), '1 year 2 months 1 day');
    });

    test('month-end day is clamped, not skipped (Jan 31 -> Mar 1)', () {
      expect(calendarSpan(DateTime(2026, 1, 31), DateTime(2026, 3, 1)), '1 month 1 day');
    });

    test('time of day is ignored and argument order does not matter', () {
      final a = DateTime(2026, 1, 1, 23, 59);
      final b = DateTime(2026, 10, 6, 0, 1);
      expect(calendarSpan(a, b), '9 months 5 days');
      expect(calendarSpan(b, a), '9 months 5 days');
    });
  });

  test('formatDateRange uses dd.MM.yyyy, an en dash and the span in brackets', () {
    expect(
      formatDateRange(DateTime(2026, 1, 1), DateTime(2026, 10, 6)),
      '01.01.2026 – 06.10.2026 (9 months 5 days)',
    );
  });

  group('rangeOfBackendTimes', () {
    test('earliest and latest, order independent', () {
      final r = rangeOfBackendTimes([
        '2026-08-10T12:00:00Z',
        '2026-06-20T12:00:00Z',
        '2026-10-05T12:00:00Z',
      ])!;
      expect((r.from.month, r.from.day), (6, 20));
      expect((r.to.month, r.to.day), (10, 5));
    });

    test('accepts the backend naive-UTC form without a Z', () {
      final r = rangeOfBackendTimes(['2026-06-20 12:00:00'])!;
      expect((r.from.month, r.from.day), (6, 20));
    });

    test('ignores null, empty and unparseable values', () {
      final r = rangeOfBackendTimes([null, '', 'garbage', '2026-06-20T12:00:00Z'])!;
      expect((r.from.month, r.from.day), (6, 20));
      expect(r.to, r.from);
    });

    test('null when nothing usable', () {
      expect(rangeOfBackendTimes([]), isNull);
      expect(rangeOfBackendTimes([null, 'x']), isNull);
    });
  });
}
