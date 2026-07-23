import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/models/vacancy.dart';
import 'package:career_agent/providers/read_vacancies_provider.dart';
import 'package:career_agent/providers/settings_provider.dart';
import 'package:career_agent/widgets/vacancy_card.dart';

VacancyListItem _vacancy({int id = 1}) => VacancyListItem(
      id: id,
      role: 'Product Manager',
      company: 'Acme',
      site: 'djinni',
      url: 'https://example.com/$id',
      status: 'fetched',
    );

class _FakeReadVacancies extends ReadVacanciesNotifier {
  @override
  Future<Set<int>> build() async => {};
}

class _FakeSettings extends SettingsNotifier {
  @override
  Future<AppSettings> build() async => const AppSettings();
}

Widget _harness({
  required bool multiSelectMode,
  bool checked = false,
  VoidCallback? onCheckToggle,
  VoidCallback? onTap,
  VoidCallback? onLongPress,
}) {
  return ProviderScope(
    overrides: [
      readVacanciesProvider.overrideWith(() => _FakeReadVacancies()),
      settingsProvider.overrideWith(() => _FakeSettings()),
    ],
    child: MaterialApp(
      home: Scaffold(
        body: VacancyCard(
          vacancy: _vacancy(),
          onTap: onTap ?? () {},
          multiSelectMode: multiSelectMode,
          checked: checked,
          onCheckToggle: onCheckToggle,
          onLongPress: onLongPress,
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('no checkbox outside multi-select mode', (tester) async {
    await tester.pumpWidget(_harness(multiSelectMode: false));
    await tester.pump();

    expect(find.byIcon(Icons.check_box_outline_blank), findsNothing);
    expect(find.byIcon(Icons.check_box), findsNothing);
  });

  testWidgets('shows unchecked box in multi-select mode when not checked', (tester) async {
    await tester.pumpWidget(_harness(multiSelectMode: true, checked: false));
    await tester.pump();

    expect(find.byIcon(Icons.check_box_outline_blank), findsOneWidget);
    expect(find.byIcon(Icons.check_box), findsNothing);
  });

  testWidgets('shows checked box when checked=true', (tester) async {
    await tester.pumpWidget(_harness(multiSelectMode: true, checked: true));
    await tester.pump();

    expect(find.byIcon(Icons.check_box), findsOneWidget);
    expect(find.byIcon(Icons.check_box_outline_blank), findsNothing);
  });

  testWidgets('tapping card in multi-select mode calls onCheckToggle, not onTap', (tester) async {
    var toggled = false;
    var tapped = false;
    await tester.pumpWidget(_harness(
      multiSelectMode: true,
      onCheckToggle: () => toggled = true,
      onTap: () => tapped = true,
    ));
    await tester.pump();

    await tester.tap(find.byType(VacancyCard));
    await tester.pump();

    expect(toggled, isTrue);
    expect(tapped, isFalse);
  });

  testWidgets('tapping card outside multi-select mode calls onTap', (tester) async {
    var tapped = false;
    await tester.pumpWidget(_harness(
      multiSelectMode: false,
      onTap: () => tapped = true,
    ));
    await tester.pump();

    await tester.tap(find.byType(VacancyCard));
    await tester.pump();

    expect(tapped, isTrue);
  });

  testWidgets('long-press triggers onLongPress callback', (tester) async {
    var longPressed = false;
    await tester.pumpWidget(_harness(
      multiSelectMode: false,
      onLongPress: () => longPressed = true,
    ));
    await tester.pump();

    await tester.longPress(find.byType(VacancyCard));
    await tester.pump();

    expect(longPressed, isTrue);
  });
}
