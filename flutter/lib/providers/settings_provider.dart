import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AppSettings {
  final String apiUrl;
  final int pollIntervalSeconds;
  final bool notificationsEnabled;
  final String? sinceTimestamp;

  const AppSettings({
    this.apiUrl = 'http://localhost:8080',
    this.pollIntervalSeconds = 30,
    this.notificationsEnabled = true,
    this.sinceTimestamp,
  });

  AppSettings copyWith({
    String? apiUrl,
    int? pollIntervalSeconds,
    bool? notificationsEnabled,
    String? sinceTimestamp,
  }) {
    return AppSettings(
      apiUrl: apiUrl ?? this.apiUrl,
      pollIntervalSeconds: pollIntervalSeconds ?? this.pollIntervalSeconds,
      notificationsEnabled: notificationsEnabled ?? this.notificationsEnabled,
      sinceTimestamp: sinceTimestamp ?? this.sinceTimestamp,
    );
  }
}

class SettingsNotifier extends AsyncNotifier<AppSettings> {
  static const _keyApiUrl = 'api_url';
  static const _keyPollInterval = 'poll_interval_seconds';
  static const _keyNotifications = 'notifications_enabled';
  static const _keySince = 'since_timestamp';

  @override
  Future<AppSettings> build() async {
    final prefs = await SharedPreferences.getInstance();
    return AppSettings(
      apiUrl: prefs.getString(_keyApiUrl) ?? 'http://localhost:8080',
      pollIntervalSeconds: prefs.getInt(_keyPollInterval) ?? 30,
      notificationsEnabled: prefs.getBool(_keyNotifications) ?? true,
      sinceTimestamp: prefs.getString(_keySince),
    );
  }

  Future<void> updateApiUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyApiUrl, url);
    state = AsyncData(state.requireValue.copyWith(apiUrl: url));
  }

  Future<void> updatePollInterval(int seconds) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_keyPollInterval, seconds);
    state = AsyncData(state.requireValue.copyWith(pollIntervalSeconds: seconds));
  }

  Future<void> updateNotifications(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_keyNotifications, enabled);
    state = AsyncData(state.requireValue.copyWith(notificationsEnabled: enabled));
  }

  Future<void> updateSinceTimestamp(String ts) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keySince, ts);
    state = AsyncData(state.requireValue.copyWith(sinceTimestamp: ts));
  }
}

final settingsProvider =
    AsyncNotifierProvider<SettingsNotifier, AppSettings>(SettingsNotifier.new);
