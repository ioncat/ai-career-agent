import 'dart:io';

import 'package:flutter/foundation.dart';

/// Local settings (shared_preferences) must never fail silently. The Windows
/// plugin returns `false` from a write and only prints the reason to the
/// `flutter run` console; every caller here ignored that `false`, so from
/// 2026-07-25 nothing was saved (list cache, read marks, later the
/// notification cursor) and nobody noticed (found 2026-10-09).
///
/// Callers pass the write's result to [reportPrefsWrite]. The first failure of
/// a session is diagnosed and published in [prefsWriteError]; the app shell
/// shows it once as an error toast.
final prefsWriteError = ValueNotifier<String?>(null);

bool _diagnosing = false;

/// Tests point the diagnosis at a temporary folder instead of the real one.
@visibleForTesting
String? settingsDirForTest;

/// [ok] is the bool a shared_preferences setter returned; [what] names the
/// value, for the message.
Future<void> reportPrefsWrite(bool ok, String what) async {
  if (ok || prefsWriteError.value != null || _diagnosing) return;
  _diagnosing = true;
  try {
    prefsWriteError.value =
        'Local settings could not be saved ($what): ${await _diagnose()}';
  } finally {
    _diagnosing = false;
  }
}

/// The settings folder of this app on Windows — the same place the
/// shared_preferences plugin uses: %APPDATA%\<CompanyName>\<ProductName>
/// from windows/runner/Runner.rc.
String? _settingsDir() {
  if (settingsDirForTest != null) return settingsDirForTest;
  if (!Platform.isWindows) return null;
  final appData = Platform.environment['APPDATA'];
  if (appData == null || appData.isEmpty) return null;
  final sep = Platform.pathSeparator;
  return '$appData${sep}com.ioncat${sep}career_agent';
}

/// Tries what the plugin does (open the settings file for writing, create a
/// file next to it) and returns the first error, without changing anything.
Future<String> _diagnose() async {
  final dir = _settingsDir();
  if (dir == null) return 'reason unknown (see the flutter run console)';
  final sep = Platform.pathSeparator;
  try {
    final file = File('$dir${sep}shared_preferences.json');
    if (await file.exists()) {
      final raf = await file.open(mode: FileMode.append);
      await raf.close();
    }
  } catch (e) {
    return 'the settings file cannot be opened for writing: $e';
  }
  try {
    final probe = File('$dir$sep.write_probe');
    await probe.writeAsString('probe', flush: true);
    await probe.delete();
  } catch (e) {
    return 'the settings folder is not writable: $e';
  }
  return 'the file and folder are writable, so the plugin failed for another '
      'reason (see "Error saving preferences to disk" in the flutter run console)';
}
