import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/models/vacancy.dart';
import 'package:career_agent/providers/read_vacancies_provider.dart';
import 'package:career_agent/providers/settings_provider.dart';
import 'package:career_agent/theme/app_theme.dart';
import 'package:career_agent/widgets/vacancy_card.dart';

// Card id click copies the bare number; every source badge shares one colour.

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

void main() {
  testWidgets(
    'clicking the id copies the number without "#" and does not open the card',
    (tester) async {
      String? copied;
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        (call) async {
          if (call.method == 'Clipboard.setData') {
            copied = (call.arguments as Map)['text'] as String?;
          }
          return null;
        },
      );
      addTearDown(
        () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
          SystemChannels.platform,
          null,
        ),
      );
      var cardTapped = false;
      final v = VacancyListItem.fromJson({
        'id': 1488,
        'title': 'Product Manager',
        'company': 'Acme',
        'site': 'dou',
        'url': 'https://example.com/1488',
        'status': 'fetched',
      });
      await tester.pumpWidget(_harness(v, onTap: () => cardTapped = true));
      await tester.pump();
      await tester.tap(find.text('#1488'));
      await tester.pump();
      expect(copied, '1488');
      expect(cardTapped, isFalse);
    },
  );

  test('every source shares the same badge colour', () {
    final colours = {
      for (final s in [
        'djinni',
        'dou',
        'linkedin',
        'work',
        'rabota',
        'robota',
        'other',
        '',
      ])
        SourceColors.forSite(s),
    };
    expect(colours, {AppColors.source});
  });
}
