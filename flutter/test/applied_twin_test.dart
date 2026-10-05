import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/models/vacancy.dart';
import 'package:career_agent/providers/read_vacancies_provider.dart';
import 'package:career_agent/providers/settings_provider.dart';
import 'package:career_agent/repositories/vacancy_repository.dart';
import 'package:career_agent/utils/analyze_guard.dart';
import 'package:career_agent/widgets/vacancy_card.dart';

// "Already applied" detection (EPIC-26): applied_twin_id in the model, the
// "Applied #X" card badge, and the Analyze guard (409 already_applied).

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
      'id': 1700,
      'title': 'Product Manager',
      'company': 'Acme',
      'site': 'dou',
      'url': 'https://example.com/1700',
      'status': 'fetched',
      ...extra,
    });

/// Repository stub: the first analyze() call is refused as already-applied,
/// the forced retry succeeds. Records every call's `force` flag.
class _GuardRepo extends VacancyRepository {
  final List<bool> calls = [];
  _GuardRepo() : super(baseUrl: 'http://localhost');

  @override
  Future<void> analyze(int vacancyId, {bool force = false}) async {
    calls.add(force);
    if (!force) throw const AlreadyAppliedException(1448);
  }
}

void main() {
  group('model', () {
    test('applied_twin_id round-trips through fromJson / toJson', () {
      final v = _vacancy({'applied_twin_id': 1448});
      expect(v.appliedTwinId, 1448);
      expect(v.toJson()['applied_twin_id'], 1448);
    });

    test('applied_twin_id is null when absent or null', () {
      expect(_vacancy({}).appliedTwinId, isNull);
      expect(_vacancy({'applied_twin_id': null}).appliedTwinId, isNull);
    });
  });

  group('409 body parsing', () {
    test('already_applied detail yields the twin id', () {
      expect(
        parseAlreadyAppliedTwinId(
          '{"detail":{"error":"already_applied","applied_twin_id":77}}',
        ),
        77,
      );
    });

    test('plain-string 409 and garbage yield null', () {
      expect(parseAlreadyAppliedTwinId('{"detail":"Already analyzing"}'), isNull);
      expect(parseAlreadyAppliedTwinId('not json'), isNull);
    });
  });

  group('card badge', () {
    testWidgets('shows "Applied #X" without a date', (tester) async {
      await tester.pumpWidget(_harness(_vacancy({'applied_twin_id': 1448})));
      await tester.pump();
      expect(find.text('Applied #1448'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('absent when there is no applied twin', (tester) async {
      await tester.pumpWidget(_harness(_vacancy({'duplicate_of': 1448})));
      await tester.pump();
      expect(find.textContaining('Applied #'), findsNothing);
      expect(find.text('Dup #1448'), findsOneWidget);
    });

    testWidgets('suppresses the Dup badge pointing at the same vacancy', (tester) async {
      await tester.pumpWidget(
        _harness(_vacancy({'applied_twin_id': 1448, 'duplicate_of': 1448})),
      );
      await tester.pump();
      expect(find.text('Applied #1448'), findsOneWidget);
      expect(find.text('Dup #1448'), findsNothing);
    });

    testWidgets('suppresses the Maybe-dup badge pointing at the same vacancy', (tester) async {
      await tester.pumpWidget(
        _harness(_vacancy({'applied_twin_id': 1448, 'possible_duplicate_of': 1448})),
      );
      await tester.pump();
      expect(find.text('Applied #1448'), findsOneWidget);
      expect(find.text('Maybe dup #1448'), findsNothing);
    });

    testWidgets('keeps a Dup badge that points at a different vacancy', (tester) async {
      await tester.pumpWidget(
        _harness(_vacancy({'applied_twin_id': 1448, 'duplicate_of': 1500})),
      );
      await tester.pump();
      expect(find.text('Applied #1448'), findsOneWidget);
      expect(find.text('Dup #1500'), findsOneWidget);
    });

    testWidgets('tap opens the twin via onTapApplied', (tester) async {
      int? opened;
      await tester.pumpWidget(
        _harness(
          _vacancy({'applied_twin_id': 1448}),
          onTapApplied: (id) => opened = id,
        ),
      );
      await tester.pump();
      await tester.tap(find.text('Applied #1448'));
      expect(opened, 1448);
    });

    testWidgets('tap falls back to onTapRelated when onTapApplied is not given', (tester) async {
      int? opened;
      await tester.pumpWidget(
        _harness(
          _vacancy({'applied_twin_id': 1448}),
          onTapRelated: (id) => opened = id,
        ),
      );
      await tester.pump();
      await tester.tap(find.text('Applied #1448'));
      expect(opened, 1448);
    });

    testWidgets('does not overflow a narrow card alongside other badges', (tester) async {
      await tester.pumpWidget(
        _harness(
          _vacancy({
            'applied_twin_id': 1448,
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

  group('analyze guard', () {
    Future<void> pumpButton(
      WidgetTester tester,
      _GuardRepo repo,
      List<bool> results,
    ) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => TextButton(
                onPressed: () async =>
                    results.add(await analyzeWithAppliedGuard(context, repo, 1700)),
                child: const Text('go'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('go'));
      await tester.pumpAndSettle();
    }

    testWidgets('confirm dialog, yes -> retries with force', (tester) async {
      final repo = _GuardRepo();
      final results = <bool>[];
      await pumpButton(tester, repo, results);
      expect(find.textContaining('Already applied as #1448'), findsOneWidget);
      expect(find.textContaining('Analyze anyway?'), findsOneWidget);

      await tester.tap(find.text('Analyze anyway'));
      await tester.pumpAndSettle();
      expect(repo.calls, [false, true]);
      expect(results, [true]);
    });

    testWidgets('confirm dialog, cancel -> nothing queued', (tester) async {
      final repo = _GuardRepo();
      final results = <bool>[];
      await pumpButton(tester, repo, results);
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      expect(repo.calls, [false]);
      expect(results, [false]);
    });
  });
}
