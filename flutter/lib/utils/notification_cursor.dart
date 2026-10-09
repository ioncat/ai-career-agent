import '../models/pipeline_notification.dart';
import 'backend_time.dart';

/// Where the notification poll stopped, persisted across app restarts
/// (notifications phase 3). Without it the first poll after a restart asked
/// for the newest 50 events and treated every one as fresh: a toast and an OS
/// notification each, for things already seen.
///
/// The backend poll is `created_at >= since`, so events sharing the cursor's
/// exact timestamp come back again; [idsAtTs] remembers which of them were
/// already seen.
class NotificationCursor {
  final String ts;
  final Set<int> idsAtTs;

  const NotificationCursor(this.ts, [this.idsAtTs = const {}]);

  /// More fresh events than this at startup collapse into one summary.
  static const startupSummaryThreshold = 3;

  static int _cmp(String a, String b) {
    try {
      return parseBackendUtc(a).compareTo(parseBackendUtc(b));
    } catch (_) {
      return a.compareTo(b);
    }
  }

  /// True for an event the user has not been shown yet.
  bool isNew(PipelineNotification n) {
    final c = _cmp(n.createdAt, ts);
    return c > 0 || (c == 0 && !idsAtTs.contains(n.id));
  }

  /// The cursor after [items] were seen: the newest timestamp among the cursor
  /// and the items, with the ids seen at exactly that timestamp.
  NotificationCursor advance(Iterable<PipelineNotification> items) {
    var newTs = ts;
    for (final n in items) {
      if (n.createdAt.isNotEmpty && _cmp(n.createdAt, newTs) > 0) {
        newTs = n.createdAt;
      }
    }
    final ids = {
      if (_cmp(newTs, ts) == 0) ...idsAtTs,
      for (final n in items)
        if (n.createdAt.isNotEmpty && _cmp(n.createdAt, newTs) == 0) n.id,
    };
    return NotificationCursor(newTs, ids);
  }

  /// First run (no stored cursor): everything already there is history, not
  /// fresh. With no events at all, start from [now] so the next event counts.
  static NotificationCursor firstRun(
    List<PipelineNotification> existing,
    DateTime now,
  ) => NotificationCursor(now.toUtc().toIso8601String()).advance(existing);

  String encodeIds() => (idsAtTs.toList()..sort()).join(',');

  static NotificationCursor? decode(String? ts, String? ids) {
    if (ts == null || ts.isEmpty) return null;
    final parsed = <int>{
      for (final s in (ids ?? '').split(',')) ?int.tryParse(s.trim()),
    };
    return NotificationCursor(ts, parsed);
  }
}

/// How fresh events are presented: one by one, or, when many arrived at once
/// (typically while the app was closed), as a single summary.
({List<PipelineNotification> individual, int summaryCount}) splitFresh(
  List<PipelineNotification> fresh, {
  required bool startup,
}) {
  if (startup && fresh.length > NotificationCursor.startupSummaryThreshold) {
    return (individual: const [], summaryCount: fresh.length);
  }
  return (individual: fresh, summaryCount: 0);
}
