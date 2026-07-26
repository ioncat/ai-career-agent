import 'dart:async';
import 'dart:convert';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/vacancy.dart';
import '../repositories/vacancy_repository.dart';
import '../utils/backend_time.dart';
import 'settings_provider.dart';

enum PollingStatus { idle, polling, found, empty, error }

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
      await prefs.setString(_kCacheKey, json);
      await prefs.setString(_kCacheTimestampKey, DateTime.now().toIso8601String());
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

// Folders where "freshest" means our own last action on the vacancy
// (analysis finished / CV+cover generated), not how recently the JD itself
// was posted — sorted by updated_at instead of the backend's default
// published_at order. Inbox/Applied/Archive keep published_at (explicit
// user decision, 2026-07-26): Inbox is about JD freshness on the market,
// Applied/Archive are terminal states where "when we acted on it" is less
// useful than "which JD is newest" for browsing.
const kUpdatedAtSortedFolders = {'analyzed', 'processed'};

final folderVacanciesProvider =
    Provider.family<List<VacancyListItem>, String>((ref, folder) {
  final state = ref.watch(vacancyListProvider).valueOrNull;
  if (state == null) return [];
  final filtered = state.vacancies.where((v) => _folderMatch(v, folder)).toList();
  if (kUpdatedAtSortedFolders.contains(folder)) {
    filtered.sort((a, b) {
      final aTime = a.updatedAt != null ? parseBackendUtc(a.updatedAt!) : null;
      final bTime = b.updatedAt != null ? parseBackendUtc(b.updatedAt!) : null;
      if (aTime == null && bTime == null) return 0;
      if (aTime == null) return 1;
      if (bTime == null) return -1;
      return bTime.compareTo(aTime); // descending — most recently updated first
    });
  }
  return filtered;
});

// 5-stage taxonomy — mirrors core/vacancy_stage.py's stage() classification.
// `stage` comes precomputed from the backend (single source of truth); this
// is just a folder-name → stage-value lookup, not a reimplementation of the
// classification logic.
bool _folderMatch(VacancyListItem v, String folder) => v.stage == folder;
