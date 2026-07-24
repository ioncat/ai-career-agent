import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/screens/vacancy_inbox_screen.dart';

// InboxListHeader's "skip all flagged" overflow menu (2026-07-24) —
// standalone bulk actions, deliberately separate from manual multi-select:
// auto-select every visible vacancy at a given pre-filter stage and skip it
// in one click, no long-press/checkbox picking.
//
// Consolidated title-blocked + content-blocked into ONE PopupMenuButton
// (was two separate always-visible IconButtons) after they overflowed this
// row on a narrow detail-pane width — the header already had filter+refresh
// icons plus an Expanded title, and two more unconditional icons pushed the
// total past what was available. Same root mistake as the badge-cluster
// overflow bug earlier the same day, just a different Row.

Widget _harness(Widget child) => MaterialApp(home: Scaffold(body: child));

Widget _narrowHarness(Widget child, double width) => MaterialApp(
      home: Scaffold(body: SizedBox(width: width, child: child)),
    );

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
  testWidgets('skip-all menu hidden when nothing is flagged', (tester) async {
    await tester.pumpWidget(_harness(_header()));

    expect(find.byIcon(Icons.playlist_remove), findsNothing);
  });

  testWidgets('skip-all menu icon shows the combined count badge', (tester) async {
    await tester.pumpWidget(_harness(_header(titleBlockedCount: 4, contentBlockedCount: 9)));

    expect(find.byIcon(Icons.playlist_remove), findsOneWidget);
    expect(find.text('13'), findsOneWidget); // 4 + 9
  });

  testWidgets('menu lists both options with their own counts, only title present when content is zero', (tester) async {
    await tester.pumpWidget(_harness(_header(titleBlockedCount: 4)));

    await tester.tap(find.byIcon(Icons.playlist_remove));
    await tester.pumpAndSettle();

    expect(find.text('Skip 4 title-blocked'), findsOneWidget);
    expect(find.textContaining('content-blocked'), findsNothing);
  });

  testWidgets('tapping the title-blocked menu item fires its own callback, not content\'s', (tester) async {
    var titleTapped = false;
    var contentTapped = false;
    await tester.pumpWidget(_harness(_header(
      titleBlockedCount: 4,
      onSkipAllTitleBlocked: () => titleTapped = true,
      contentBlockedCount: 9,
      onSkipAllContentBlocked: () => contentTapped = true,
    )));

    await tester.tap(find.byIcon(Icons.playlist_remove));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Skip 4 title-blocked'));
    await tester.pumpAndSettle();

    expect(titleTapped, isTrue);
    expect(contentTapped, isFalse);
  });

  testWidgets('tapping the content-blocked menu item fires its own callback, not title\'s', (tester) async {
    var titleTapped = false;
    var contentTapped = false;
    await tester.pumpWidget(_harness(_header(
      titleBlockedCount: 4,
      onSkipAllTitleBlocked: () => titleTapped = true,
      contentBlockedCount: 9,
      onSkipAllContentBlocked: () => contentTapped = true,
    )));

    await tester.tap(find.byIcon(Icons.playlist_remove));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Skip 9 content-blocked'));
    await tester.pumpAndSettle();

    expect(contentTapped, isTrue);
    expect(titleTapped, isFalse);
  });

  testWidgets('header row does not overflow on a narrow detail-pane width with both actions + filter + refresh present', (tester) async {
    // Regression guard for the actual bug found live 2026-07-24: on a
    // narrow window, this row (title + skip-all menu + filter + refresh)
    // overflowed — the debug "RIGHT OVERFLOWED" banner rendered off in the
    // empty detail pane, easy to miss since the vacancy cards themselves
    // (a completely different widget, already fixed earlier the same day)
    // looked fine. Reproduced at a deliberately narrow width standing in
    // for a squeezed detail pane.
    await tester.pumpWidget(_narrowHarness(
      _header(titleBlockedCount: 4, contentBlockedCount: 9),
      160,
    ));
    await tester.pump();

    expect(tester.takeException(), isNull);
  });
}
