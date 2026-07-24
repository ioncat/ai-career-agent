import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../repositories/vacancy_repository.dart';
export '../repositories/vacancy_repository.dart' show ConfigDriftException;
import 'phase_config_provider.dart';
import 'settings_provider.dart';

class RemoteConfig {
  final String llmProvider;
  final String model;
  final String thinkingEffort;
  final String analysisMode;
  final bool autoCheckTitle;
  final List<String> availableModels;
  final List<String> validProviders;

  const RemoteConfig({
    required this.llmProvider,
    required this.model,
    required this.thinkingEffort,
    required this.analysisMode,
    required this.autoCheckTitle,
    required this.availableModels,
    required this.validProviders,
  });

  // Any provider with a fetched model list gets a dropdown — including Ollama,
  // whose models come from GET /api/tags (refresh button / auto-fetch).
  bool get supportsModelSelection => availableModels.isNotEmpty;

  // Ollama has no extended-thinking effort control.
  bool get supportsEffort => llmProvider != 'ollama_api';
}

class RemoteConfigNotifier extends AsyncNotifier<RemoteConfig> {
  @override
  Future<RemoteConfig> build() async {
    final settings = await ref.watch(settingsProvider.future);
    final repo = VacancyRepository(baseUrl: settings.apiUrl);
    final data = await repo.getConfig();
    return _fromMap(data);
  }

  /// Switching provider now also loads that provider's saved phase pins on
  /// the backend (2026-07-24 redesign) — invalidate phaseConfigProvider so
  /// the per-phase UI reflects them instead of showing stale data from
  /// whichever provider was active a moment ago.
  Future<void> patchProvider(String provider) async {
    final settings = await ref.read(settingsProvider.future);
    final repo = VacancyRepository(baseUrl: settings.apiUrl);
    final data = await repo.patchConfig(llmProvider: provider);
    state = AsyncData(_fromMap(data));
    ref.invalidate(phaseConfigProvider);
  }

  /// Persist the CURRENT full state (this provider's model/effort + every
  /// phase pin) under the active provider's key — the Settings Save
  /// button's real job for AI Provider state.
  Future<void> saveSnapshot() async {
    final settings = await ref.read(settingsProvider.future);
    final repo = VacancyRepository(baseUrl: settings.apiUrl);
    await repo.saveConfigSnapshot();
  }

  /// Patch model/effort against a provider the backend might have already
  /// left — on drift (409), refresh state to the real current config and
  /// rethrow so the UI can show what happened, instead of silently applying
  /// the change to the wrong provider or failing invisibly.
  Future<void> _patchAgainstCurrentProvider(
    Future<Map<String, dynamic>> Function(String expectedProvider) patch,
  ) async {
    final current = state.valueOrNull;
    try {
      final data = await patch(current?.llmProvider ?? '');
      state = AsyncData(_fromMap(data));
    } on ConfigDriftException {
      final settings = await ref.read(settingsProvider.future);
      final repo = VacancyRepository(baseUrl: settings.apiUrl);
      final fresh = await repo.getConfig();
      state = AsyncData(_fromMap(fresh));
      rethrow;
    }
  }

  Future<void> patchModel(String model) async {
    final settings = await ref.read(settingsProvider.future);
    final repo = VacancyRepository(baseUrl: settings.apiUrl);
    await _patchAgainstCurrentProvider(
      (expected) => repo.patchConfig(model: model, expectedProvider: expected),
    );
  }

  /// Force-refresh available models for the active provider, then merge the
  /// fresh list into the current config (keeps provider/model/effort as-is).
  Future<void> refreshModels() async {
    final current = state.valueOrNull;
    if (current == null) return;
    final settings = await ref.read(settingsProvider.future);
    final repo = VacancyRepository(baseUrl: settings.apiUrl);
    final data = await repo.refreshModels();
    final raw = data['available_models'];
    final models = raw is List ? raw.whereType<String>().toList() : <String>[];
    state = AsyncData(RemoteConfig(
      llmProvider: current.llmProvider,
      model: current.model,
      thinkingEffort: current.thinkingEffort,
      analysisMode: current.analysisMode,
      autoCheckTitle: current.autoCheckTitle,
      availableModels: models,
      validProviders: current.validProviders,
    ));
  }

  Future<void> patchEffort(String effort) async {
    final settings = await ref.read(settingsProvider.future);
    final repo = VacancyRepository(baseUrl: settings.apiUrl);
    await _patchAgainstCurrentProvider(
      (expected) => repo.patchConfig(thinkingEffort: effort, expectedProvider: expected),
    );
  }

  /// Stage 1 pre-filter (title/domain, deterministic — no LLM) auto-trigger
  /// on/off. Independent of provider/model/effort — no drift-guard needed,
  /// this flag never affects which provider is active.
  Future<void> patchAutoCheckTitle(bool enabled) async {
    final settings = await ref.read(settingsProvider.future);
    final repo = VacancyRepository(baseUrl: settings.apiUrl);
    final data = await repo.patchConfig(autoCheckTitle: enabled);
    state = AsyncData(_fromMap(data));
  }

  static RemoteConfig _fromMap(Map<String, dynamic> data) {
    final rawModels = data['available_models'];
    final models = rawModels is List
        ? rawModels.whereType<String>().toList()
        : <String>[];
    final rawProviders = data['valid_providers'];
    final providers = rawProviders is List
        ? rawProviders.whereType<String>().toList()
        : <String>[];
    return RemoteConfig(
      llmProvider: data['llm_provider'] as String? ?? '',
      model: data['model'] as String? ?? '',
      thinkingEffort: data['thinking_effort'] as String? ?? 'off',
      analysisMode: data['analysis_mode'] as String? ?? '',
      autoCheckTitle: data['auto_check_title'] as bool? ?? true,
      availableModels: models,
      validProviders: providers,
    );
  }
}

final remoteConfigProvider =
    AsyncNotifierProvider<RemoteConfigNotifier, RemoteConfig>(
  RemoteConfigNotifier.new,
);
