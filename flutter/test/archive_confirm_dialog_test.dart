import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/models/vacancy.dart';
import 'package:career_agent/screens/vacancy_inbox_screen.dart';

// ArchiveConfirmDialog (2026-08-25) — the Delete-key keyboard path's confirm
// step. Enter must confirm (bound explicitly in the widget, not a default
// AlertDialog behavior), mirroring clicking the Archive button.

VacancyListItem _item({String role = 'Product Manager', String company = 'Acme'}) =>
    VacancyListItem(
      id: 1,
      role: role,
      company: company,
      site: 'djinni',
      url: 'https://example.com/1',
      status: 'inbox',
    );

Future<bool?> _openDialog(WidgetTester tester, VacancyListItem vacancy) async {
  bool? result;
  await tester.pumpWidget(MaterialApp(
    home: Scaffold(
      body: Builder(
        builder: (context) => ElevatedButton(
          onPressed: () async {
            result = await showDialog<bool>(
              context: context,
              builder: (context) => ArchiveConfirmDialog(vacancy: vacancy),
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
  testWidgets('shows role and company of the vacancy being archived', (tester) async {
    await _openDialog(tester, _item(role: 'Senior PM', company: 'Widgets Inc'));
    expect(find.textContaining('Senior PM'), findsOneWidget);
    expect(find.textContaining('Widgets Inc'), findsOneWidget);
  });

  testWidgets('Enter key confirms (pops true)', (tester) async {
    await _openDialog(tester, _item());
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
  });

  testWidgets('Space key confirms (pops true)', (tester) async {
    bool? result;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () async {
              result = await showDialog<bool>(
                context: context,
                builder: (context) => ArchiveConfirmDialog(vacancy: _item()),
              );
            },
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.space);
    await tester.pumpAndSettle();
    expect(result, isTrue);
  });

  testWidgets('Escape key cancels (pops false, not true)', (tester) async {
    bool? result;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () async {
              result = await showDialog<bool>(
                context: context,
                builder: (context) => ArchiveConfirmDialog(vacancy: _item()),
              );
            },
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(result, isFalse);
  });

  testWidgets('clicking Cancel pops false', (tester) async {
    bool? result;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () async {
              result = await showDialog<bool>(
                context: context,
                builder: (context) => ArchiveConfirmDialog(vacancy: _item()),
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
    expect(result, isFalse);
  });

  testWidgets('clicking Archive pops true', (tester) async {
    bool? result;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () async {
              result = await showDialog<bool>(
                context: context,
                builder: (context) => ArchiveConfirmDialog(vacancy: _item()),
              );
            },
            child: const Text('open'),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Archive'));
    await tester.pumpAndSettle();
    expect(result, isTrue);
  });
}
