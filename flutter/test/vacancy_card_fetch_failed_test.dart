import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/models/vacancy.dart';
import 'package:career_agent/providers/read_vacancies_provider.dart';
import 'package:career_agent/providers/settings_provider.dart';
import 'package:career_agent/widgets/vacancy_card.dart';

// A vacancy with a failure mark shows the one red pill (notifications phase 1).

class _FakeReadVacancies extends ReadVacanciesNotifier {
  @override
  Future<Set<int>> build() async => {};
}

class _FakeSettings extends SettingsNotifier {
  @override
  Future<AppSettings> build() async => const AppSettings();
}

Widget _harness(VacancyListItem v, {required VoidCallback onTap}) {
  return ProviderScope(
    overrides: [
      readVacanciesProvider.overrideWith(() => _FakeReadVacancies()),
      settingsProvider.overrideWith(() => _FakeSettings()),
    ],
    child: MaterialApp(
      home: Scaffold(
        body: SizedBox(
          width: 300,
          child: VacancyCard(vacancy: v, onTap: onTap),
        ),
      ),
    ),
  );
}

VacancyListItem _vacancy(String status) => VacancyListItem.fromJson({
  'id': 854,
  'title': 'Product Manager',
  'company': 'Acme',
  'site': 'djinni',
  'url': 'https://example.com/854',
  'status': status,
  'analysis_error': 'Fetch failed 5x — giving up: parser unreachable',
  'failure': status == 'fetch_failed'
      ? {
          'kind': 'fetch',
          'target': null,
          'reason': 'Fetch failed 5x — giving up: parser unreachable',
          'at': '2026-10-09T10:00:00Z',
          'retry': 'fetch',
          'code': 'fetch_gave_up',
        }
      : null,
});

void main() {
  testWidgets('fetch_failed card shows the Fetch failed badge', (tester) async {
    await tester.pumpWidget(_harness(_vacancy('fetch_failed'), onTap: () {}));
    await tester.pump();
    expect(find.text('Fetch failed'), findsOneWidget);
  });

  testWidgets('a normal card has no Fetch failed badge', (tester) async {
    await tester.pumpWidget(_harness(_vacancy('fetched'), onTap: () {}));
    await tester.pump();
    expect(find.text('Fetch failed'), findsNothing);
  });
}
