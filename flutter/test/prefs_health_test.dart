import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/utils/prefs_health.dart';

void main() {
  late Directory tmp;
  setUp(() {
    prefsWriteError.value = null;
    tmp = Directory.systemTemp.createTempSync('prefs_health_');
    settingsDirForTest = tmp.path;
  });
  tearDown(() {
    settingsDirForTest = null;
    tmp.deleteSync(recursive: true);
  });

  test('a successful write publishes nothing', () async {
    await reportPrefsWrite(true, 'x');
    expect(prefsWriteError.value, isNull);
  });

  test(
    'the first failed write publishes one message naming the value',
    () async {
      await reportPrefsWrite(false, 'notification cursor');
      expect(prefsWriteError.value, contains('notification cursor'));
      final first = prefsWriteError.value;
      await reportPrefsWrite(false, 'read marks');
      expect(
        prefsWriteError.value,
        first,
        reason: 'only the first failure is shown',
      );
    },
  );

  test('a writable folder is reported as a plugin-side failure', () async {
    await reportPrefsWrite(false, 'x');
    expect(prefsWriteError.value, contains('flutter run console'));
    expect(tmp.listSync(), isEmpty, reason: 'the probe file is removed');
  });

  test('a missing folder is reported as not writable', () async {
    settingsDirForTest = '${tmp.path}${Platform.pathSeparator}missing';
    await reportPrefsWrite(false, 'x');
    expect(prefsWriteError.value, contains('not writable'));
  });
}
