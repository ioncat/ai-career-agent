import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/screens/vacancy_inbox_screen.dart';

// InboxListHeader's "Skip all with blockers" button (2026-07-24) — a
// standalone bulk action, deliberately separate from manual multi-select:
// auto-selects everything visible with a pre-filter blocker flag and skips
// it in one click, no long-press/checkbox picking.

Widget _harness(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  testWidgets('skip-all-blocked button hidden when nothing is flagged', (tester) async {
    await tester.pumpWidget(_harness(InboxListHeader(
      title: 'Inbox',
      visibleCount: 10,
      totalCount: 10,
      onRefresh: () {},
      filterCount: 0,
      filterExpanded: false,
      onToggleFilter: () {},
      blockedCount: 0,
      onSkipAllBlocked: null,
    )));

    expect(find.byIcon(Icons.playlist_remove), findsNothing);
  });

  testWidgets('skip-all-blocked button shows a count badge and fires its callback', (tester) async {
    var tapped = false;
    await tester.pumpWidget(_harness(InboxListHeader(
      title: 'Inbox',
      visibleCount: 10,
      totalCount: 10,
      onRefresh: () {},
      filterCount: 0,
      filterExpanded: false,
      onToggleFilter: () {},
      blockedCount: 4,
      onSkipAllBlocked: () => tapped = true,
    )));

    expect(find.byIcon(Icons.playlist_remove), findsOneWidget);
    expect(find.text('4'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.playlist_remove));
    expect(tapped, isTrue);
  });

  testWidgets('skip-all-blocked button disabled (null callback) while a batch is running', (tester) async {
    await tester.pumpWidget(_harness(InboxListHeader(
      title: 'Inbox',
      visibleCount: 10,
      totalCount: 10,
      onRefresh: () {},
      filterCount: 0,
      filterExpanded: false,
      onToggleFilter: () {},
      blockedCount: 4,
      onSkipAllBlocked: null, // caller passes null while _batchRunning
    )));

    final button = tester.widget<IconButton>(find.ancestor(
      of: find.byIcon(Icons.playlist_remove),
      matching: find.byType(IconButton),
    ));
    expect(button.onPressed, isNull);
  });
}
