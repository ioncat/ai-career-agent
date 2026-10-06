import 'backend_time.dart';

/// Calendar span between two dates as "9 months 5 days" (years, months, days;
/// zero parts omitted, singular/plural handled). Same day -> "same day".
/// Only the date part counts — time of day is ignored.
String calendarSpan(DateTime from, DateTime to) {
  var a = DateTime(from.year, from.month, from.day);
  var b = DateTime(to.year, to.month, to.day);
  if (b.isBefore(a)) {
    final t = a;
    a = b;
    b = t;
  }
  var months = (b.year - a.year) * 12 + b.month - a.month;
  if (b.day < a.day) months--;
  final anchor = _addMonths(a, months);
  final days = b.difference(anchor).inDays;
  final years = months ~/ 12;
  final restMonths = months % 12;
  String unit(int n, String word) => '$n $word${n == 1 ? '' : 's'}';
  final parts = [
    if (years > 0) unit(years, 'year'),
    if (restMonths > 0) unit(restMonths, 'month'),
    if (days > 0) unit(days, 'day'),
  ];
  return parts.isEmpty ? 'same day' : parts.join(' ');
}

// a + n months, clamping the day to the target month's length (Jan 31 + 1 -> Feb 28/29).
DateTime _addMonths(DateTime a, int n) {
  final total = a.year * 12 + (a.month - 1) + n;
  final y = total ~/ 12;
  final m = total % 12 + 1;
  final last = DateTime(y, m + 1, 0).day;
  return DateTime(y, m, a.day > last ? last : a.day);
}

String _dmy(DateTime d) =>
    '${d.day.toString().padLeft(2, '0')}.${d.month.toString().padLeft(2, '0')}.${d.year}';

/// "01.01.2026 – 06.10.2026 (9 months 5 days)".
String formatDateRange(DateTime from, DateTime to) =>
    '${_dmy(from)} – ${_dmy(to)} (${calendarSpan(from, to)})';

/// Earliest and latest of backend timestamps, as LOCAL dates (what the user
/// sees on their calendar, not the UTC day). Null/unparseable values are
/// ignored; returns null when nothing usable is left.
({DateTime from, DateTime to})? rangeOfBackendTimes(Iterable<String?> isoValues) {
  DateTime? lo;
  DateTime? hi;
  for (final iso in isoValues) {
    if (iso == null || iso.isEmpty) continue;
    final DateTime t;
    try {
      t = parseBackendUtc(iso).toLocal();
    } catch (_) {
      continue;
    }
    if (lo == null || t.isBefore(lo)) lo = t;
    if (hi == null || t.isAfter(hi)) hi = t;
  }
  return lo == null || hi == null ? null : (from: lo, to: hi);
}
