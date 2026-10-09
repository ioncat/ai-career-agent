import 'dart:async';
import 'dart:convert';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/vacancy.dart';
import '../repositories/vacancy_repository.dart';
import '../utils/backend_time.dart';
import 'settings_provider.dart';
import 'vacancy_cv_provider.dart';
import 'vacancy_detail_provider.dart';
import '../utils/prefs_health.dart';

enum PollingStatus { idle, polling, found, empty, error }

/// Ids present in both lists whose status or updated_at changed. The per-
/// vacancy detail caches (analysis, CV) are fetched once and never refresh on
/// their own; a change seen by the list poll is the one signal that they are
/// stale (2026-10-09: an analysis finished while the vacancy moved Inbox ->
/// Analyzed showed the cached empty analysis until a manual Refresh).
Set<int> changedVacancyIds(
  List<VacancyListItem> before,
  List<VacancyListItem> after,
) {
  final old = {for (final v in before) v.id: v};
  return {
    for (final v in after)
      if (old[v.id] case final o?
          when o.status != v.status || o.updatedAt != v.updatedAt)
        v.id,
  };
}

const _kCacheKey = 'vacancy_list_cache';
const _kCacheTimestampKey = 'vacancy_list_cache_ts';

class PollingState {
  final List<VacancyListItem> vacancies;
  final PollingStatus status;
  final int newCount;
  /// Subset of newCount: only status==analyzed. Used for "N vacancies analysed" notification.
  final int newAnalyzedCount;
  final DateTime? lastUpdatedAt;
  final String? errorMessage;
  final bool fromCache;

  const PollingState({
    this.vacancies = const [],
    this.status = PollingStatus.idle,
    this.newCount = 0,
    this.newAnalyzedCount = 0,
    this.lastUpdatedAt,
    this.errorMessage,
    this.fromCache = false,
  });

  PollingState copyWith({
    List<VacancyListItem>? vacancies,
    PollingStatus? status,
    int? newCount,
    int? newAnalyzedCount,
    DateTime? lastUpdatedAt,
    String? errorMessage,
    bool? fromCache,
  }) {
    return PollingState(
      vacancies: vacancies ?? this.vacancies,
      status: status ?? this.status,
      newCount: newCount ?? this.newCount,
      newAnalyzedCount: newAnalyzedCount ?? this.newAnalyzedCount,
      lastUpdatedAt: lastUpdatedAt ?? this.lastUpdatedAt,
      errorMessage: errorMessage ?? this.errorMessage,
      fromCache: fromCache ?? this.fromCache,
    );
  }
}

class VacancyListNotifier extends AsyncNotifier<PollingState> {
  Timer? _timer;

  @override
  Future<PollingState> build() async {
    final settings = await ref.watch(settingsProvider.future);

    _timer?.cancel();
    _timer = Timer.periodic(
      Duration(seconds: settings.pollIntervalSeconds),
      (_) => _poll(),
    );
    ref.onDispose(() => _timer?.cancel());

    // Load cache immediately, then fetch in background
    final cached = await _loadCache();
    if (cached != null) {
      // Show cache instantly, kick off background refresh
      state = AsyncData(cached);
      _poll();
      return cached;
    }

    return _fetchAll(settings.apiUrl);
  }

  Future<PollingState?> _loadCache() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final json = prefs.getString(_kCacheKey);
      final tsStr = prefs.getString(_kCacheTimestampKey);
      if (json == null) return null;

      final list = (jsonDecode(json) as List)
          .map((e) => VacancyListItem.fromJson(e as Map<String, dynamic>))
          .toList();

      final ts = tsStr != null ? DateTime.tryParse(tsStr) : null;

      return PollingState(
        vacancies: list,
        status: PollingStatus.idle,
        lastUpdatedAt: ts,
        fromCache: true,
      );
    } catch (_) {
      return null;
    }
  }

  Future<void> _saveCache(List<VacancyListItem> items) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final json = jsonEncode(items.map((v) => v.toJson()).toList());
      reportPrefsWrite(
        await prefs.setString(_kCacheKey, json) &&
            await prefs.setString(
              _kCacheTimestampKey,
              DateTime.now().toIso8601String(),
            ),
        'vacancy list cache',
      );
    } catch (_) {}
  }

  Future<PollingState> _fetchAll(String apiUrl) async {
    final repo = VacancyRepository(baseUrl: apiUrl);
    final items = await repo.listVacancies();
    await _saveCache(items);
    return PollingState(
      vacancies: items,
      status: PollingStatus.idle,
      lastUpdatedAt: DateTime.now(),
      fromCache: false,
    );
  }

  Future<void> _poll() async {
    final settings = ref.read(settingsProvider).valueOrNull;
    if (settings == null) return;

    final current = state.valueOrNull;
    state = AsyncData(
      (current ?? const PollingState()).copyWith(status: PollingStatus.polling),
    );

    try {
      final repo = VacancyRepository(baseUrl: settings.apiUrl);
      final items = await repo.listVacancies();
      await _saveCache(items);

      for (final id in changedVacancyIds(current?.vacancies ?? const [], items)) {
        ref.invalidate(vacancyDetailProvider(id));
        ref.invalidate(vacancyCvProvider(id));
      }

      final existingIds = current?.vacancies.map((v) => v.id).toSet() ?? {};
      final newAnalyzed = items
          .where((v) => !existingIds.contains(v.id) && v.status == 'analyzed')
          .length;
      final newFetched = items
          .where((v) => !existingIds.contains(v.id) && v.status == 'fetched')
          .length;
      final newTotal = newAnalyzed + newFetched;

      state = AsyncData(PollingState(
        vacancies: items,
        status: newTotal > 0 ? PollingStatus.found : PollingStatus.empty,
        newCount: newTotal,
        newAnalyzedCount: newAnalyzed,
        lastUpdatedAt: DateTime.now(),
        fromCache: false,
      ));
    } catch (e) {
      state = AsyncData(
        (current ?? const PollingState()).copyWith(
          status: PollingStatus.error,
          errorMessage: e.toString(),
        ),
      );
    }
  }

  Future<void> refresh() => _poll();
}

final vacancyListProvider =
    AsyncNotifierProvider<VacancyListNotifier, PollingState>(
        VacancyListNotifier.new);

// One-shot request to switch the sidebar to another folder (value = folder name:
// inbox/analyzed/processed/applied/archive). VacancyInboxScreen sets it (e.g. the
// "already applied" line opens vacancy X in the Applied folder), AppShell consumes it
// and resets it to null.
final folderNavRequestProvider = StateProvider<String?>((ref) => null);

// Reverse of VacancyListItem.duplicateOf (2026-09-02) — `duplicateOf` is a
// one-way pointer (the later-found posting points at the canonical one), so
// the canonical card itself had no way to show it has a known duplicate
// elsewhere. Found live: #1431 (Djinni, canonical) showed no badge at all,
// while its sibling #1432 (DOU, duplicate_of=1431) showed "Dup #1431" — the
// relationship was only visible from one side of the pair. Computed here
// (not per-card) so every VacancyCard can look itself up by id in O(1)
// without each one re-scanning the full list.
final duplicatedByProvider = Provider<Map<int, List<int>>>((ref) {
  final vacancies = ref.watch(vacancyListProvider).valueOrNull?.vacancies ?? const [];
  final map = <int, List<int>>{};
  for (final v in vacancies) {
    final originalId = v.duplicateOf;
    if (originalId == null) continue;
    (map[originalId] ??= []).add(v.id);
  }
  return map;
});

// Folders where "freshest" means our own last action on the vacancy
// (analysis finished / CV+cover generated), not how recently the JD itself
// was posted — sorted by updated_at instead of the backend's default
// published_at order. Inbox keeps published_at — it's about JD freshness on
// the market. Applied/Archive each get their own dedicated timestamp
// (appliedAt/declinedAt) below, not updated_at, for the same reason: that
// column is bumped by ~10 unrelated write paths (starred/salary/tags edits,
// duplicate linking), so "last touched" silently drifts from "when the user
// actually applied/declined it".
const kUpdatedAtSortedFolders = {'analyzed', 'processed'};

int _compareByNullableIso(String? aIso, String? bIso) {
  final aTime = aIso != null ? parseBackendUtc(aIso) : null;
  final bTime = bIso != null ? parseBackendUtc(bIso) : null;
  if (aTime == null && bTime == null) return 0;
  if (aTime == null) return 1;
  if (bTime == null) return -1;
  return bTime.compareTo(aTime); // descending — most recent first
}

final folderVacanciesProvider =
    Provider.family<List<VacancyListItem>, String>((ref, folder) {
  final state = ref.watch(vacancyListProvider).valueOrNull;
  if (state == null) return [];
  final filtered = state.vacancies.where((v) => _folderMatch(v, folder)).toList();
  if (kUpdatedAtSortedFolders.contains(folder)) {
    filtered.sort((a, b) => _compareByNullableIso(a.updatedAt, b.updatedAt));
  } else if (folder == 'applied') {
    // applied_at (2026-08-13) — when the user actually marked it applied,
    // not published_at (job posting date, unrelated) or updated_at (bumped
    // by ~10 unrelated write paths, same class of bug as the "Analyzed"
    // chip fix). Found live: a vacancy applied to seconds ago showed up
    // second, not first. Supersedes the 2026-07-26 published_at decision —
    // that one didn't have an applied_at field to sort by yet.
    filtered.sort((a, b) => _compareByNullableIso(a.appliedAt, b.appliedAt));
  } else if (folder == 'archive') {
    // declined_at (2026-09-05) — when the vacancy was actually declined, not
    // publishedAt (JD posting date) or updatedAt. User request: the vacancy
    // just skipped should show up first, regardless of how old its JD is.
    filtered.sort((a, b) => _compareByNullableIso(a.declinedAt, b.declinedAt));
  }
  return filtered;
});

// 5-stage taxonomy — mirrors core/vacancy_stage.py's stage() classification.
// `stage` comes precomputed from the backend (single source of truth); this
// is just a folder-name → stage-value lookup, not a reimplementation of the
// classification logic.
bool _folderMatch(VacancyListItem v, String folder) => v.stage == folder;
