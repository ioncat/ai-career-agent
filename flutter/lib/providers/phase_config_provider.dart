import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../repositories/vacancy_repository.dart';
export '../repositories/vacancy_repository.dart' show ConfigDriftException;
import 'settings_provider.dart';

/// Pipeline phases, in pipeline order — mirrors core.config_store.VALID_PHASES.
const List<String> kPhaseOrder = [
  'prefilter',
  'phase1',
  'phase2',
  'phase3',
  'phase3_5',
  'phase4',
];

const Map<String, String> kPhaseLabels = {
  'prefilter': 'Pre-filter — blocker check',
  'phase1': 'Phase 1 — JD Analysis',
  'phase2': 'Phase 2 — Fit Assessment',
  'phase3': 'Phase 3 — CV Draft',
  'phase3_5': 'Phase 3.5 — CV Self-Review',
  'phase4': 'Phase 4 — Cover Message',
};

class PhaseConfig {
  final String provider;
  final String model;
  final String thinkingEffort;
  final bool isOverride;
  final List<String> availableModels;

  const PhaseConfig({
    required this.provider,
    required this.model,
    required this.thinkingEffort,
    required this.isOverride,
    required this.availableModels,
  });

  bool get supportsModelSelection => availableModels.isNotEmpty;
  // Same caveat as RemoteConfig.supportsEffort — blanket-Ollama-disables-effort
  // is a known oversimplification (some Ollama models DO support thinking).
  // Not fixed here — needs the Ollama think-on-unsupported-model behavior
  // researched first (see EPIC-27 design doc's open question).
  bool get supportsEffort => provider != 'ollama_api';

  factory PhaseConfig.fromMap(Map<String, dynamic> data) {
    final rawModels = data['available_models'];
    final models = rawModels is List ? rawModels.whereType<String>().toList() : <String>[];
    return PhaseConfig(
      provider: data['provider'] as String? ?? '',
      model: data['model'] as String? ?? '',
      thinkingEffort: data['thinking_effort'] as String? ?? 'off',
      isOverride: data['is_override'] as bool? ?? false,
      availableModels: models,
    );
  }
}

class PhaseConfigNotifier extends AsyncNotifier<Map<String, PhaseConfig>> {
  @override
  Future<Map<String, PhaseConfig>> build() async {
    final settings = await ref.watch(settingsProvider.future);
    final repo = VacancyRepository(baseUrl: settings.apiUrl);
    final data = await repo.getConfigPhases();
    return _fromMap(data);
  }

  /// Patch one phase against its currently-known provider — on drift (409),
  /// refresh state to the real current config and rethrow, same contract as
  /// RemoteConfigNotifier's global equivalent.
  Future<void> _patchAgainstCurrentProvider(
    String phase,
    VacancyRepository repo,
    Future<Map<String, dynamic>> Function(String expectedProvider) patch,
  ) async {
    final current = state.valueOrNull?[phase];
    try {
      final data = await patch(current?.provider ?? '');
      _mergePhase(phase, PhaseConfig.fromMap(data));
    } on ConfigDriftException {
      final fresh = await repo.getConfigPhases();
      state = AsyncData(_fromMap(fresh));
      rethrow;
    }
  }

  Future<void> patchProvider(String phase, String provider) async {
    final settings = await ref.read(settingsProvider.future);
    final repo = VacancyRepository(baseUrl: settings.apiUrl);
    final data = await repo.patchConfigPhase(phase, provider: provider);
    _mergePhase(phase, PhaseConfig.fromMap(data));
  }

  Future<void> patchModel(String phase, String model) async {
    final settings = await ref.read(settingsProvider.future);
    final repo = VacancyRepository(baseUrl: settings.apiUrl);
    await _patchAgainstCurrentProvider(
      phase,
      repo,
      (expected) => repo.patchConfigPhase(phase, model: model, expectedProvider: expected),
    );
  }

  Future<void> patchEffort(String phase, String effort) async {
    final settings = await ref.read(settingsProvider.future);
    final repo = VacancyRepository(baseUrl: settings.apiUrl);
    await _patchAgainstCurrentProvider(
      phase,
      repo,
      (expected) => repo.patchConfigPhase(phase, thinkingEffort: effort, expectedProvider: expected),
    );
  }

  Future<void> resetToDefault(String phase) async {
    final settings = await ref.read(settingsProvider.future);
    final repo = VacancyRepository(baseUrl: settings.apiUrl);
    final data = await repo.deleteConfigPhase(phase);
    _mergePhase(phase, PhaseConfig.fromMap(data));
  }

  void _mergePhase(String phase, PhaseConfig updated) {
    final current = state.valueOrNull ?? {};
    state = AsyncData({...current, phase: updated});
  }

  static Map<String, PhaseConfig> _fromMap(Map<String, dynamic> data) {
    final phases = data['phases'] as Map<String, dynamic>? ?? {};
    return phases.map((k, v) => MapEntry(k, PhaseConfig.fromMap(v as Map<String, dynamic>)));
  }
}

final phaseConfigProvider =
    AsyncNotifierProvider<PhaseConfigNotifier, Map<String, PhaseConfig>>(
  PhaseConfigNotifier.new,
);
