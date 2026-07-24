import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/models/vacancy.dart';
import 'package:career_agent/providers/read_vacancies_provider.dart';
import 'package:career_agent/providers/settings_provider.dart';
import 'package:career_agent/widgets/vacancy_card.dart';

// Found 2026-07-24: a vacancy with a "New" + "Possible blocker" badge
// overflowed VacancyCard's badge Row on narrow inbox cards (real card width
// ~280px), showing the debug "RIGHT OVERFLOWED" banner. Two fixes: the badge
// cluster now sits in a Wrap instead of a fixed-width Row segment (same
// pattern as the 2026-07-05 detail-screen score-pill overflow fix), and the
// blocker badge's own label shrank "Possible blocker" → "Blocker" — measured
// ~168px wide, the actual single biggest contributor to the overflow.

class _FakeReadVacancies extends ReadVacanciesNotifier {
  @override
  Future<Set<int>> build() async => {};
}

class _FakeSettings extends SettingsNotifier {
  @override
  Future<AppSettings> build() async => const AppSettings();
}

Widget _harness(VacancyListItem vacancy, {double width = 260}) {
  return ProviderScope(
    overrides: [
      readVacanciesProvider.overrideWith(() => _FakeReadVacancies()),
      settingsProvider.overrideWith(() => _FakeSettings()),
    ],
    child: MaterialApp(
      home: Scaffold(
        body: SizedBox(
          width: width,
          child: VacancyCard(vacancy: vacancy, onTap: () {}),
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('badge cluster with every badge active does not overflow a narrow card', (tester) async {
    final vacancy = VacancyListItem(
      id: 823,
      role: 'Senior Outbound SDR Lead',
      company: 'Not Your Average Start-Up',
      site: 'djinni',
      url: 'https://example.com/823',
      status: 'fetched',
      publishedAt: DateTime.now().toUtc().subtract(const Duration(minutes: 59)).toIso8601String(),
      duplicateOf: 100,
      republishedAt: DateTime.now().toUtc().toIso8601String(),
      blockerFlag: true,
      blockerReasons: const [
        'title: "Senior Outbound SDR Lead" does not contain a fitting role term (Product Manager/Owner, Project/Delivery/Program Manager, Business Analyst, Operations Manager, Technical Product/Project Manager)',
      ],
    );

    await tester.pumpWidget(_harness(vacancy, width: 260));
    await tester.pump();

    expect(tester.takeException(), isNull);
  });

  testWidgets('blocker badge has no hover tooltip dumping the full reason text', (tester) async {
    final vacancy = VacancyListItem(
      id: 822,
      role: 'Product Engineer (AI-Native Technical Business/System Analyst)',
      company: 'Top Netics',
      site: 'dou',
      url: 'https://example.com/822',
      status: 'fetched',
      blockerFlag: true,
      blockerReasons: const [
        'title: "Product Engineer (AI-Native Technical Business/System Analyst)" does not contain a fitting role term',
      ],
    );

    await tester.pumpWidget(_harness(vacancy));
    await tester.pump();

    final longMessageTooltips = tester
        .widgetList<Tooltip>(find.byType(Tooltip))
        .where((t) => (t.message ?? '').contains('Possible blocker'));
    expect(longMessageTooltips, isEmpty);
  });
}
