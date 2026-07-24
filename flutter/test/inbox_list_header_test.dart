import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/screens/vacancy_inbox_screen.dart';

// InboxListHeader's "skip all" buttons (2026-07-24) — standalone bulk
// actions, deliberately separate from manual multi-select: auto-select
// every visible vacancy at a given pre-filter stage and skip it in one
// click, no long-press/checkbox picking. Split into two (title vs content)
// rather than one "skip everything" button — Stage 1 (title, deterministic)
// is safe to bulk-clear; Stage 2 (content, LLM-judged) gets its own
// separate action so it's never silently swept up by the same click.

Widget _harness(Widget child) => MaterialApp(home: Scaffold(body: child));

InboxListHeader _header({
  int titleBlockedCount = 0,
  VoidCallback? onSkipAllTitleBlocked,
  int contentBlockedCount = 0,
  VoidCallback? onSkipAllContentBlocked,
}) {
  return InboxListHeader(
    title: 'Inbox',
    visibleCount: 10,
    totalCount: 10,
    onRefresh: () {},
    filterCount: 0,
    filterExpanded: false,
    onToggleFilter: () {},
    titleBlockedCount: titleBlockedCount,
    onSkipAllTitleBlocked: onSkipAllTitleBlocked,
    contentBlockedCount: contentBlockedCount,
    onSkipAllContentBlocked: onSkipAllContentBlocked,
  );
}

void main() {
  testWidgets('both skip-all buttons hidden when nothing is flagged', (tester) async {
    await tester.pumpWidget(_harness(_header()));

    expect(find.byIcon(Icons.title), findsNothing);
    expect(find.byIcon(Icons.psychology_outlined), findsNothing);
  });

  testWidgets('title-blocked button shows its own count and fires its own callback, independent of content', (tester) async {
    var titleTapped = false;
    var contentTapped = false;
    await tester.pumpWidget(_harness(_header(
      titleBlockedCount: 4,
      onSkipAllTitleBlocked: () => titleTapped = true,
      contentBlockedCount: 9,
      onSkipAllContentBlocked: () => contentTapped = true,
    )));

    expect(find.byIcon(Icons.title), findsOneWidget);
    expect(find.text('4'), findsOneWidget);
    expect(find.text('9'), findsOneWidget);

    await tester.tap(find.byIcon(Icons.title));
    expect(titleTapped, isTrue);
    expect(contentTapped, isFalse);
  });

  testWidgets('content-blocked button fires its own callback, independent of title', (tester) async {
    var titleTapped = false;
    var contentTapped = false;
    await tester.pumpWidget(_harness(_header(
      titleBlockedCount: 4,
      onSkipAllTitleBlocked: () => titleTapped = true,
      contentBlockedCount: 9,
      onSkipAllContentBlocked: () => contentTapped = true,
    )));

    await tester.tap(find.byIcon(Icons.psychology_outlined));
    expect(contentTapped, isTrue);
    expect(titleTapped, isFalse);
  });

  testWidgets('only content button shows when only content-blocked vacancies exist', (tester) async {
    await tester.pumpWidget(_harness(_header(contentBlockedCount: 3)));

    expect(find.byIcon(Icons.title), findsNothing);
    expect(find.byIcon(Icons.psychology_outlined), findsOneWidget);
    expect(find.text('3'), findsOneWidget);
  });

  testWidgets('title-blocked button disabled (null callback) while a batch is running', (tester) async {
    await tester.pumpWidget(_harness(_header(
      titleBlockedCount: 4,
      onSkipAllTitleBlocked: null, // caller passes null while _batchRunning
    )));

    final button = tester.widget<IconButton>(find.ancestor(
      of: find.byIcon(Icons.title),
      matching: find.byType(IconButton),
    ));
    expect(button.onPressed, isNull);
  });
}
