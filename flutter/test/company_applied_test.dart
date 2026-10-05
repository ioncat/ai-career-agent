import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/models/vacancy.dart';
import 'package:career_agent/providers/read_vacancies_provider.dart';
import 'package:career_agent/providers/settings_provider.dart';
import 'package:career_agent/widgets/vacancy_card.dart';

// "Applied at this company" hint (EPIC-26, 2026-10-05): company_applied_id in
// the model and the weaker "Co. applied #N" card badge. The layout itself was
// not visually checked (no preview for the desktop app) — these tests cover
// presence, suppression and tap behaviour only.

class _FakeReadVacancies extends ReadVacanciesNotifier {
  @override
  Future<Set<int>> build() async => {};
}

class _FakeSettings extends SettingsNotifier {
  @override
  Future<AppSettings> build() async => const AppSettings();
}

Widget _harness(
  VacancyListItem vacancy, {
  void Function(int)? onTapApplied,
  void Function(int)? onTapRelated,
}) {
  return ProviderScope(
    overrides: [
      readVacanciesProvider.overrideWith(() => _FakeReadVacancies()),
      settingsProvider.overrideWith(() => _FakeSettings()),
    ],
    child: MaterialApp(
      home: Scaffold(
        body: SizedBox(
          width: 300,
          child: VacancyCard(
            vacancy: vacancy,
            onTap: () {},
            onTapApplied: onTapApplied,
            onTapRelated: onTapRelated,
          ),
        ),
      ),
    ),
  );
}

VacancyListItem _vacancy(Map<String, dynamic> extra) => VacancyListItem.fromJson({
      'id': 206,
      'title': 'Product Owner',
      'company': 'Dripify',
      'site': 'djinni',
      'url': 'https://example.com/206',
      'status': 'fetched',
      ...extra,
    });

void main() {
  group('model', () {
    test('company_applied_id round-trips through fromJson / toJson', () {
      final v = _vacancy({'company_applied_id': 598});
      expect(v.companyAppliedId, 598);
      expect(v.toJson()['company_applied_id'], 598);
    });

    test('company_applied_id is null when absent or null', () {
      expect(_vacancy({}).companyAppliedId, isNull);
      expect(_vacancy({'company_applied_id': null}).companyAppliedId, isNull);
    });
  });

  group('card badge', () {
    testWidgets('shows "Co. applied #N"', (tester) async {
      await tester.pumpWidget(_harness(_vacancy({'company_applied_id': 598})));
      await tester.pump();
      expect(find.text('Co. applied #598'), findsOneWidget);
      expect(find.textContaining('Applied #'), findsNothing); // the strong badge is a different one
      expect(tester.takeException(), isNull);
    });

    testWidgets('absent when companyAppliedId is null', (tester) async {
      await tester.pumpWidget(_harness(_vacancy({})));
      await tester.pump();
      expect(find.textContaining('Co. applied'), findsNothing);
    });

    testWidgets('hidden when the card already shows "Applied #X" for the same id', (tester) async {
      await tester.pumpWidget(
        _harness(_vacancy({'applied_twin_id': 598, 'company_applied_id': 598})),
      );
      await tester.pump();
      expect(find.text('Applied #598'), findsOneWidget);
      expect(find.textContaining('Co. applied'), findsNothing);
    });

    testWidgets('shown next to "Applied #X" when they point at different vacancies', (tester) async {
      await tester.pumpWidget(
        _harness(_vacancy({'applied_twin_id': 1448, 'company_applied_id': 598})),
      );
      await tester.pump();
      expect(find.text('Applied #1448'), findsOneWidget);
      expect(find.text('Co. applied #598'), findsOneWidget);
    });

    testWidgets('tap opens the vacancy via onTapApplied (same navigation as "Applied #N")',
        (tester) async {
      int? opened;
      await tester.pumpWidget(
        _harness(
          _vacancy({'company_applied_id': 598}),
          onTapApplied: (id) => opened = id,
        ),
      );
      await tester.pump();
      await tester.tap(find.text('Co. applied #598'));
      expect(opened, 598);
    });

    testWidgets('tap falls back to onTapRelated when onTapApplied is not given', (tester) async {
      int? opened;
      await tester.pumpWidget(
        _harness(
          _vacancy({'company_applied_id': 598}),
          onTapRelated: (id) => opened = id,
        ),
      );
      await tester.pump();
      await tester.tap(find.text('Co. applied #598'));
      expect(opened, 598);
    });

    testWidgets('does not overflow a narrow card alongside other badges', (tester) async {
      await tester.pumpWidget(
        _harness(
          _vacancy({
            'applied_twin_id': 1448,
            'company_applied_id': 598,
            'duplicate_of': 1500,
            'blocker_flag': true,
            'blocker_reasons': ['title: no fitting role term'],
          }),
        ),
      );
      await tester.pump();
      expect(tester.takeException(), isNull);
    });
  });
}
