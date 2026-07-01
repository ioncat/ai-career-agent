import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/vacancy.dart';
import '../providers/settings_provider.dart';
import '../repositories/vacancy_repository.dart';

final vacancyCvProvider = FutureProvider.family<VacancyCv, int>((ref, vacancyId) async {
  final settings = await ref.watch(settingsProvider.future);
  final repo = VacancyRepository(baseUrl: settings.apiUrl);
  return repo.getCv(vacancyId);
});
