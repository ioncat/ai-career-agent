import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../repositories/vacancy_repository.dart';
import 'settings_provider.dart';

class RemoteConfig {
  final String llmProvider;
  final String model;
  final String thinkingEffort;
  final String analysisMode;
  final List<String> availableModels;
  final List<String> validProviders;

  const RemoteConfig({
    required this.llmProvider,
    required this.model,
    required this.thinkingEffort,
    required this.analysisMode,
    required this.availableModels,
    required this.validProviders,
  });

  bool get supportsModelSelection =>
      llmProvider != 'ollama_api' && availableModels.isNotEmpty;

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

  Future<void> patchProvider(String provider) async {
    final settings = await ref.read(settingsProvider.future);
    final repo = VacancyRepository(baseUrl: settings.apiUrl);
    final data = await repo.patchConfig(llmProvider: provider);
    state = AsyncData(_fromMap(data));
  }

  Future<void> patchModel(String model) async {
    final settings = await ref.read(settingsProvider.future);
    final repo = VacancyRepository(baseUrl: settings.apiUrl);
    final data = await repo.patchConfig(model: model);
    state = AsyncData(_fromMap(data));
  }

  Future<void> patchEffort(String effort) async {
    final settings = await ref.read(settingsProvider.future);
    final repo = VacancyRepository(baseUrl: settings.apiUrl);
    final data = await repo.patchConfig(thinkingEffort: effort);
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
      availableModels: models,
      validProviders: providers,
    );
  }
}

final remoteConfigProvider =
    AsyncNotifierProvider<RemoteConfigNotifier, RemoteConfig>(
  RemoteConfigNotifier.new,
);
