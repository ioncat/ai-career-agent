import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/screens/vacancy_inbox_screen.dart';

// InboxBatchActionBar — Mass Action's action bar (BACKLOG "Batch Analysis
// Mode", extended 2026-07-24 to Check Blockers + a "2 primary buttons +
// overflow menu" layout instead of a flat button-per-action row, which
// doesn't scale on the 360px inbox panel).

Widget _harness(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  testWidgets('selection state shows count, Skip and Analyze buttons, and an overflow menu', (tester) async {
    await tester.pumpWidget(_harness(InboxBatchActionBar(
      count: 3,
      running: false,
      runningLabel: '',
      done: 0,
      total: 0,
      onAnalyze: () {},
      onCheckBlockers: () {},
      onSkip: () {},
      onCancel: () {},
    )));

    expect(find.text('3 selected'), findsOneWidget);
    expect(find.text('Skip'), findsOneWidget);
    expect(find.text('Analyze'), findsOneWidget);
    // Check blockers lives in the overflow menu, not as its own button —
    // not visible until the menu is opened.
    expect(find.text('Check blockers'), findsNothing);
    expect(find.byIcon(Icons.more_horiz), findsOneWidget);
  });

  testWidgets('overflow menu opens and Check blockers tap fires its callback', (tester) async {
    var tapped = false;
    await tester.pumpWidget(_harness(InboxBatchActionBar(
      count: 1,
      running: false,
      runningLabel: '',
      done: 0,
      total: 0,
      onAnalyze: () {},
      onCheckBlockers: () => tapped = true,
      onSkip: () {},
      onCancel: () {},
    )));

    await tester.tap(find.byIcon(Icons.more_horiz));
    await tester.pumpAndSettle();
    expect(find.text('Check blockers'), findsOneWidget);

    await tester.tap(find.text('Check blockers'));
    await tester.pumpAndSettle();
    expect(tapped, isTrue);
  });

  testWidgets('Skip and Analyze buttons fire their own callbacks', (tester) async {
    var skipped = false;
    var analyzed = false;
    await tester.pumpWidget(_harness(InboxBatchActionBar(
      count: 2,
      running: false,
      runningLabel: '',
      done: 0,
      total: 0,
      onAnalyze: () => analyzed = true,
      onCheckBlockers: () {},
      onSkip: () => skipped = true,
      onCancel: () {},
    )));

    await tester.tap(find.text('Skip'));
    await tester.tap(find.text('Analyze'));
    expect(skipped, isTrue);
    expect(analyzed, isTrue);
  });

  testWidgets('running state shows progress instead of action buttons', (tester) async {
    await tester.pumpWidget(_harness(const InboxBatchActionBar(
      count: 5,
      running: true,
      runningLabel: 'Skip',
      done: 2,
      total: 5,
    )));

    expect(find.text('Skip: 2/5'), findsOneWidget);
    expect(find.text('Skip'), findsNothing); // no button label while running
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
  });
}
