import 'dart:convert';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../utils/prefs_health.dart';

const _kReadKey = 'read_vacancy_ids';

class ReadVacanciesNotifier extends AsyncNotifier<Set<int>> {
  @override
  Future<Set<int>> build() async {
    final prefs = await SharedPreferences.getInstance();
    final json = prefs.getString(_kReadKey);
    if (json == null) return {};
    return (jsonDecode(json) as List).cast<int>().toSet();
  }

  Future<void> markRead(int id) async {
    final current = state.valueOrNull ?? {};
    if (current.contains(id)) return;
    final updated = {...current, id};
    state = AsyncData(updated);
    final prefs = await SharedPreferences.getInstance();
    reportPrefsWrite(
      await prefs.setString(_kReadKey, jsonEncode(updated.toList())),
      'read marks',
    );
  }
}

final readVacanciesProvider =
    AsyncNotifierProvider<ReadVacanciesNotifier, Set<int>>(
        ReadVacanciesNotifier.new);
