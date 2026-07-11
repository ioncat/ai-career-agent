import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/pipeline_notification.dart';
import '../repositories/vacancy_repository.dart';
import 'settings_provider.dart';

// ── State ─────────────────────────────────────────────────────────────────────

class NotificationState {
  final List<PipelineNotification> items;
  final List<PipelineNotification> fresh; // items arrived in the last poll cycle

  const NotificationState({
    this.items = const [],
    this.fresh = const [],
  });

  int get unreadCount => items.where((n) => !n.read).length;

  NotificationState copyWith({
    List<PipelineNotification>? items,
    List<PipelineNotification>? fresh,
  }) =>
      NotificationState(
        items: items ?? this.items,
        fresh: fresh ?? this.fresh,
      );
}

// ── Notifier ──────────────────────────────────────────────────────────────────

class NotificationNotifier extends AsyncNotifier<NotificationState> {
  Timer? _timer;
  String? _lastSince; // ISO 8601 of latest known notification

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
      final settings = await ref.read(settingsProvider.future);
      final repo = VacancyRepository(baseUrl: settings.apiUrl);
      final fetched = await repo.fetchNotifications(
        since: _lastSince,
        unreadOnly: false,
        limit: 50,
      );
      if (fetched.isEmpty) {
        // Clear fresh list from previous cycle
        state = AsyncData(state.valueOrNull?.copyWith(fresh: const []) ??
            const NotificationState());
        return;
      }

      // Update _lastSince to the most recent item's created_at
      final newest = fetched.reduce(
          (a, b) => a.createdAt.compareTo(b.createdAt) > 0 ? a : b);
      _lastSince = newest.createdAt;

      // Merge with existing — prepend new items, deduplicate by id
      final current = state.valueOrNull?.items ?? [];
      final existingIds = {for (final n in current) n.id};
      final incoming =
          fetched.where((n) => !existingIds.contains(n.id)).toList();
      final merged = [...incoming, ...current];

      state = AsyncData(NotificationState(
        items: merged,
        fresh: incoming, // only newly arrived this cycle
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
              ? PipelineNotification(
                  id: n.id,
                  userId: n.userId,
                  vacancyId: n.vacancyId,
                  event: n.event,
                  title: n.title,
                  body: n.body,
                  read: true,
                  createdAt: n.createdAt,
                )
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
          .map((n) => PipelineNotification(
                id: n.id,
                userId: n.userId,
                vacancyId: n.vacancyId,
                event: n.event,
                title: n.title,
                body: n.body,
                read: true,
                createdAt: n.createdAt,
              ))
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
