import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/vacancy.dart';
import '../repositories/vacancy_repository.dart';
import 'settings_provider.dart';

enum PollingStatus { idle, polling, found, empty, error }

class PollingState {
  final List<VacancyListItem> vacancies;
  final PollingStatus status;
  final int newCount;
  final DateTime? lastUpdatedAt;
  final String? errorMessage;

  const PollingState({
    this.vacancies = const [],
    this.status = PollingStatus.idle,
    this.newCount = 0,
    this.lastUpdatedAt,
    this.errorMessage,
  });

  PollingState copyWith({
    List<VacancyListItem>? vacancies,
    PollingStatus? status,
    int? newCount,
    DateTime? lastUpdatedAt,
    String? errorMessage,
  }) {
    return PollingState(
      vacancies: vacancies ?? this.vacancies,
      status: status ?? this.status,
      newCount: newCount ?? this.newCount,
      lastUpdatedAt: lastUpdatedAt ?? this.lastUpdatedAt,
      errorMessage: errorMessage ?? this.errorMessage,
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

    return _fetchAll(settings.apiUrl);
  }

  Future<PollingState> _fetchAll(String apiUrl) async {
    final repo = VacancyRepository(baseUrl: apiUrl);
    final items = await repo.listVacancies();
    return PollingState(
      vacancies: items,
      status: PollingStatus.idle,
      lastUpdatedAt: DateTime.now(),
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

      final existingIds = current?.vacancies.map((v) => v.id).toSet() ?? {};
      final newAnalyzed = items
          .where((v) => !existingIds.contains(v.id) && v.status == 'analyzed')
          .length;

      state = AsyncData(PollingState(
        vacancies: items,
        status: newAnalyzed > 0 ? PollingStatus.found : PollingStatus.empty,
        newCount: newAnalyzed,
        lastUpdatedAt: DateTime.now(),
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

// Filter: vacancies by folder/status
final folderVacanciesProvider =
    Provider.family<List<VacancyListItem>, String>((ref, folder) {
  final state = ref.watch(vacancyListProvider).valueOrNull;
  if (state == null) return [];
  return state.vacancies.where((v) => _folderMatch(v.status, folder)).toList();
});

bool _folderMatch(String status, String folder) {
  switch (folder) {
    case 'inbox':
      return status == 'analyzed';
    case 'in_progress':
      return status == 'cv_generated';
    case 'applied':
      return status == 'applied';
    case 'archive':
      return status == 'declined';
    default:
      return false;
  }
}
