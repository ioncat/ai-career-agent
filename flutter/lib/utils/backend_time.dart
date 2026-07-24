/// career-agent's backend stores every timestamp as a naive UTC string
/// (no 'Z'/offset marker) — SQLite `datetime('now')` and RSSWatcher both
/// write plain "YYYY-MM-DD[T ]HH:MM:SS". `DateTime.parse()` on a string
/// without a timezone marker is interpreted as LOCAL time by Dart, silently
/// shifting every relative/absolute display by the device's UTC offset.
///
/// Found 2026-07-24: vacancy #824, fetched ~15 minutes earlier, showed
/// "3h ago" in Kyiv summer time (UTC+3) — the offset matched exactly. The
/// same fix (`_asUtc`) had already been written independently three times
/// in `vacancy_detail_screen.dart` but never shared, so a fourth call site
/// (`vacancy_card.dart`) missed it entirely. Route every backend-timestamp
/// parse through this file instead of calling `DateTime.parse` directly.
///
/// The backend also normalizes these fields to carry an explicit 'Z' at the
/// API response boundary (see `web/api.py._normalize_dates`) — this is
/// defense in depth for any field or endpoint that boundary doesn't cover.
library;

DateTime parseBackendUtc(String iso) {
  final hasTz = iso.endsWith('Z') || RegExp(r'[+-]\d\d:\d\d$').hasMatch(iso);
  return DateTime.parse(hasTz ? iso : '${iso}Z');
}

/// "3h ago" / "12m ago" / "just now" — falls back to the raw string on parse
/// failure rather than throwing, since this is always used inline in a
/// widget build.
String relativeTimeFromBackend(String iso) {
  try {
    final dt = parseBackendUtc(iso);
    final diff = DateTime.now().difference(dt);
    if (diff.inDays > 0) return '${diff.inDays}d ago';
    if (diff.inHours > 0) return '${diff.inHours}h ago';
    if (diff.inMinutes > 0) return '${diff.inMinutes}m ago';
    return 'just now';
  } catch (_) {
    return iso;
  }
}
