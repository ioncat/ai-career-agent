import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/pipeline_notification.dart';
import '../repositories/vacancy_repository.dart';
import '../utils/notification_cursor.dart';
import 'settings_provider.dart';

const _kCursorTsKey = 'notifications_cursor_ts';
const _kCursorIdsKey = 'notifications_cursor_ids';

// ── State ─────────────────────────────────────────────────────────────────────

class NotificationState {
  final List<PipelineNotification> items;
  final List<PipelineNotification> fresh; // items arrived in the last poll cycle

  /// > 0 only on the first poll after a start, when more than
  /// [NotificationCursor.startupSummaryThreshold] events arrived while the app
  /// was closed: show one summary instead of [fresh] (which is then empty).
  final int summaryCount;

  const NotificationState({
    this.items = const [],
    this.fresh = const [],
    this.summaryCount = 0,
  });

  int get unreadCount => items.where((n) => !n.read).length;

  NotificationState copyWith({
    List<PipelineNotification>? items,
    List<PipelineNotification>? fresh,
    int? summaryCount,
  }) =>
      NotificationState(
        items: items ?? this.items,
        fresh: fresh ?? this.fresh,
        summaryCount: summaryCount ?? this.summaryCount,
      );
}

// ── Notifier ──────────────────────────────────────────────────────────────────

class NotificationNotifier extends AsyncNotifier<NotificationState> {
  Timer? _timer;
  // Persisted poll position (phase 3); null until loaded / on the first run.
  NotificationCursor? _cursor;
  bool _cursorLoaded = false;
  bool _startupPollDone = false;

  Future<void> _loadCursor() async {
    if (_cursorLoaded) return;
    _cursorLoaded = true;
    try {
      final prefs = await SharedPreferences.getInstance();
      _cursor = NotificationCursor.decode(
        prefs.getString(_kCursorTsKey),
        prefs.getString(_kCursorIdsKey),
      );
    } catch (_) {}
  }

  Future<void> _saveCursor(NotificationCursor c) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kCursorTsKey, c.ts);
      await prefs.setString(_kCursorIdsKey, c.encodeIds());
    } catch (_) {}
  }

  @override
  Future<NotificationState> build() async {
    ref.onDispose(() => _timer?.cancel());
    final settings = await ref.watch(settingsProvider.future);
    _schedulePolling(settings.pollIntervalSeconds);
    return const NotificationState();
  }

  void _schedulePolling(int intervalSeconds) {
    _timer?.cancel();
    _timer = Timer.periodic(
      Duration(seconds: intervalSeconds),
      (_) => _poll(),
    );
    _poll(); // immediate first fetch
  }

  Future<void> _poll() async {
    try {
      await _loadCursor();
      final settings = await ref.read(settingsProvider.future);
      final repo = VacancyRepository(baseUrl: settings.apiUrl);
      final cursor = _cursor;
      final fetched = await repo.fetchNotifications(
        since: cursor?.sinceParam,
        unreadOnly: false,
        limit: 50,
      );
      final startup = !_startupPollDone;
      _startupPollDone = true;

      // First run ever (no stored cursor): what is already there is history.
      final List<PipelineNotification> newOnes;
      final NotificationCursor next;
      if (cursor == null) {
        newOnes = const [];
        next = NotificationCursor.firstRun(fetched, DateTime.now());
      } else {
        newOnes = fetched.where(cursor.isNew).toList();
        next = cursor.advance(fetched);
      }
      _cursor = next;
      if (cursor == null ||
          next.ts != cursor.ts ||
          next.encodeIds() != cursor.encodeIds()) {
        await _saveCursor(next);
      }

      // Merge with existing — prepend new items, deduplicate by id
      final current = state.valueOrNull?.items ?? [];
      final existingIds = {for (final n in current) n.id};
      final incoming =
          fetched.where((n) => !existingIds.contains(n.id)).toList();
      final merged = [...incoming, ...current];
      final split = splitFresh(newOnes, startup: startup);

      state = AsyncData(NotificationState(
        items: merged,
        fresh: split.individual, // only events not shown before
        summaryCount: split.summaryCount,
      ));
    } catch (_) {
      // Swallow polling errors — don't disrupt the UI
    }
  }

  Future<void> markRead(int notificationId) async {
    try {
      final settings = await ref.read(settingsProvider.future);
      final repo = VacancyRepository(baseUrl: settings.apiUrl);
      await repo.markNotificationRead(notificationId);
      final updated = (state.valueOrNull?.items ?? [])
          .map((n) => n.id == notificationId
              ? n.copyWith(read: true)
              : n)
          .toList();
      state = AsyncData(
          state.valueOrNull?.copyWith(items: updated) ??
              NotificationState(items: updated));
    } catch (_) {}
  }

  Future<void> markAllRead() async {
    try {
      final settings = await ref.read(settingsProvider.future);
      final repo = VacancyRepository(baseUrl: settings.apiUrl);
      await repo.markAllNotificationsRead();
      final updated = (state.valueOrNull?.items ?? [])
          .map((n) => n.copyWith(read: true))
          .toList();
      state = AsyncData(
          state.valueOrNull?.copyWith(items: updated) ??
              NotificationState(items: updated));
    } catch (_) {}
  }

  Future<void> refresh() => _poll();
}

// ── Provider ──────────────────────────────────────────────────────────────────

final notificationProvider =
    AsyncNotifierProvider<NotificationNotifier, NotificationState>(
  NotificationNotifier.new,
);
