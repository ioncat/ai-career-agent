import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/models/vacancy.dart';
import 'package:career_agent/screens/vacancy_inbox_screen.dart';

// SkipConfirmDialog (2026-07-28) — replaces a bare count-only confirm for
// "Skip all {stage}-blocked" with a checklist of the actual vacancies, so a
// pre-filter false-positive can be excluded without aborting the batch.

VacancyListItem _item(
  int id, {
  String role = 'Role',
  String company = 'Co',
  List<String> blockerReasons = const [],
}) =>
    VacancyListItem(
      id: id,
      role: '$role $id',
      company: '$company $id',
      site: 'djinni',
      url: 'https://example.com/$id',
      status: 'inbox',
      blockerReasons: blockerReasons,
    );

Future<List<int>?> _openDialog(
  WidgetTester tester,
  List<VacancyListItem> vacancies,
) async {
  List<int>? result;
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => ElevatedButton(
          onPressed: () async {
            result = await showDialog<List<int>>(
              context: context,
              builder: (context) => SkipConfirmDialog(
                stageLabel: 'title-blocked',
                vacancies: vacancies,
              ),
            );
          },
          child: const Text('open'),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  return result;
}

void main() {
  testWidgets('lists every vacancy with a checkbox, all checked by default',
      (tester) async {
    final vacancies = [_item(1), _item(2), _item(3)];
    await _openDialog(tester, vacancies);

    expect(find.text('Role 1 — Co 1'), findsOneWidget);
    expect(find.text('Role 2 — Co 2'), findsOneWidget);
    expect(find.text('Role 3 — Co 3'), findsOneWidget);
    expect(find.text('Skip 3'), findsOneWidget);

    final checkboxes = tester.widgetList<Checkbox>(find.byType(Checkbox));
    expect(checkboxes.every((c) => c.value == true), isTrue);
  });

  testWidgets('unchecking one vacancy excludes it from the confirmed result',
      (tester) async {
    final vacancies = [_item(1), _item(2), _item(3)];
    List<int>? result;

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () async {
              result = await showDialog<List<int>>(
                context: context,
                builder: (context) => SkipConfirmDialog(
                  stageLabel: 'title-blocked',
                  vacancies: vacancies,
                ),
              );
            },
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Role 2 — Co 2'));
    await tester.pumpAndSettle();

    expect(find.text('Skip 2'), findsOneWidget);
    await tester.tap(find.text('Skip 2'));
    await tester.pumpAndSettle();

    expect(result, [1, 3]);
  });

  testWidgets('Cancel returns an empty list, nothing gets skipped',
      (tester) async {
    final vacancies = [_item(1), _item(2)];
    List<int>? result;

    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () async {
              result = await showDialog<List<int>>(
                context: context,
                builder: (context) => SkipConfirmDialog(
                  stageLabel: 'title-blocked',
                  vacancies: vacancies,
                ),
              );
            },
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();

    expect(result, isEmpty);
  });

  testWidgets('shows blocker reasons under the title when present', (tester) async {
    final vacancies = [
      _item(1, blockerReasons: [
        'igaming: "5+ years of Product Management experience within iGaming."',
      ]),
      _item(2), // no reasons — subtitle should be absent for this row
    ];
    await _openDialog(tester, vacancies);

    expect(
      find.textContaining('igaming: "5+ years of Product Management'),
      findsOneWidget,
    );
  });

  testWidgets('multiple reasons for one vacancy are all shown', (tester) async {
    final vacancies = [
      _item(1, blockerReasons: [
        'title: "Product Owner Lead"',
        'igaming: "5+ років на посаді Product Owner бажано в gambling"',
      ]),
    ];
    await _openDialog(tester, vacancies);

    expect(find.textContaining('title: "Product Owner Lead"'), findsOneWidget);
    expect(find.textContaining('igaming: "5+ років'), findsOneWidget);
  });

  testWidgets('unchecking everything disables the Skip button', (tester) async {
    final vacancies = [_item(1)];
    await _openDialog(tester, vacancies);

    await tester.tap(find.text('Role 1 — Co 1'));
    await tester.pumpAndSettle();

    final button = tester.widget<FilledButton>(find.byType(FilledButton));
    expect(button.onPressed, isNull);
  });
}
