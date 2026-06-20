import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/vacancy.dart';
import '../repositories/vacancy_repository.dart';
import 'settings_provider.dart';

final vacancyDetailProvider =
    FutureProvider.family<VacancyAnalysis, int>((ref, vacancyId) async {
  final settings = await ref.watch(settingsProvider.future);
  final repo = VacancyRepository(baseUrl: settings.apiUrl);
  return repo.getAnalysis(vacancyId);
});
