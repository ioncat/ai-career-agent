import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/health.dart';
import '../repositories/health_repository.dart';
import 'settings_provider.dart';

class HealthNotifier extends AsyncNotifier<HealthStatus> {
  Timer? _timer;

  @override
  Future<HealthStatus> build() async {
    final settings = await ref.watch(settingsProvider.future);
    final repo = HealthRepository(baseUrl: settings.apiUrl);

    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 60), (_) => _check());

    ref.onDispose(() => _timer?.cancel());

    return repo.check();
  }

  Future<void> _check() async {
    final settings = ref.read(settingsProvider).valueOrNull;
    if (settings == null) return;
    state = const AsyncData(HealthStatus.checking);
    final repo = HealthRepository(baseUrl: settings.apiUrl);
    state = AsyncData(await repo.check());
  }
}

final healthProvider =
    AsyncNotifierProvider<HealthNotifier, HealthStatus>(HealthNotifier.new);
