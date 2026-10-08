import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/utils/backend_time.dart';

void main() {
  group('parseBackendUtc', () {
    test('naive string (no timezone marker) is treated as UTC', () {
      final dt = parseBackendUtc('2026-07-24T12:53:34');
      expect(dt.isUtc, isTrue);
      expect(dt.hour, 12);
      expect(dt.minute, 53);
    });

    test('already-Z-suffixed string is left as-is (still parses correctly)', () {
      final dt = parseBackendUtc('2026-07-24T12:53:34Z');
      expect(dt.isUtc, isTrue);
      expect(dt.hour, 12);
    });

    test('string with explicit offset is left as-is', () {
      final dt = parseBackendUtc('2026-07-24T12:53:34+03:00');
      // 12:53 at +03:00 == 09:53 UTC
      expect(dt.toUtc().hour, 9);
    });

    test('naive and Z-suffixed forms of the same instant parse identically', () {
      final naive = parseBackendUtc('2026-07-24T12:53:34');
      final withZ = parseBackendUtc('2026-07-24T12:53:34Z');
      expect(naive.toUtc(), withZ.toUtc());
    });
  });

  group('relativeTimeFromBackend', () {
    test('a few minutes ago', () {
      final iso = DateTime.now()
          .toUtc()
          .subtract(const Duration(minutes: 15))
          .toIso8601String()
          .split('.')
          .first; // strip fractional seconds, no 'Z' — simulates DB storage
      expect(relativeTimeFromBackend(iso), '15m ago');
    });

    test('over an hour ago', () {
      final iso = DateTime.now()
          .toUtc()
          .subtract(const Duration(hours: 3))
          .toIso8601String()
          .split('.')
          .first;
      expect(relativeTimeFromBackend(iso), '3h ago');
    });

    test('just now for a sub-minute timestamp', () {
      final iso = DateTime.now()
          .toUtc()
          .subtract(const Duration(seconds: 5))
          .toIso8601String()
          .split('.')
          .first;
      expect(relativeTimeFromBackend(iso), 'just now');
    });

    test('unparseable input falls back to the raw string', () {
      expect(relativeTimeFromBackend('not-a-date'), 'not-a-date');
    });

    test('regression: a 15-minute-old naive timestamp must not read as hours '
        'ago regardless of device timezone (vacancy #824, 2026-07-24)', () {
      final iso = DateTime.now()
          .toUtc()
          .subtract(const Duration(minutes: 15))
          .toIso8601String()
          .split('.')
          .first;
      final result = relativeTimeFromBackend(iso);
      expect(result, isNot(contains('h ago')));
      expect(result, isNot(contains('d ago')));
    });
  });

  group('isIngestionDate', () {
    test('published_at equal to created_at is the ingestion time', () {
      expect(
        isIngestionDate('2026-08-23T09:33:48Z', '2026-08-23 09:33:48'),
        isTrue,
      );
    });

    test('a few seconds apart still counts as ingestion time', () {
      expect(
        isIngestionDate('2026-08-23T09:33:50Z', '2026-08-23T09:33:48Z'),
        isTrue,
      );
    });

    test('an older feed date is a real publish date', () {
      expect(
        isIngestionDate('2026-08-20T07:00:00Z', '2026-08-23T09:33:48Z'),
        isFalse,
      );
    });

    test('missing or unparsable created_at falls back to a publish date', () {
      expect(isIngestionDate('2026-08-23T09:33:48Z', null), isFalse);
      expect(isIngestionDate('2026-08-23T09:33:48Z', ''), isFalse);
      expect(isIngestionDate('2026-08-23T09:33:48Z', 'garbage'), isFalse);
    });
  });
}
