import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../repositories/vacancy_repository.dart';
import 'settings_provider.dart';

class RemoteConfig {
  final String llmProvider;
  final String model;
  final String analysisMode;

  const RemoteConfig({
    required this.llmProvider,
    required this.model,
    required this.analysisMode,
  });
}

final remoteConfigProvider = FutureProvider<RemoteConfig>((ref) async {
  final settings = await ref.watch(settingsProvider.future);
  final repo = VacancyRepository(baseUrl: settings.apiUrl);
  final data = await repo.getConfig();
  return RemoteConfig(
    llmProvider: data['llm_provider'] ?? '',
    model: data['model'] ?? '',
    analysisMode: data['analysis_mode'] ?? '',
  );
});
