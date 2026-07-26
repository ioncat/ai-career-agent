import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/models/vacancy.dart';
import 'package:career_agent/screens/vacancy_inbox_screen.dart';

// "Today" / "Earlier" section headers (2026-07-24, revised 2026-07-25) —
// purely visual markers around the boundary between today's vacancies and
// older ones. List is already sorted newest-first, no re-sorting/grouping.
// When nothing is from today, a bare "Earlier" header at the very top read
// as unexplained — revised to always show "Today" first, with an explicit
// "Nothing for today" note when that section is empty.

Widget _harness(Widget child) => ProviderScope(
      child: MaterialApp(home: Scaffold(body: child)),
    );

String _utc(DateTime local) => local.toUtc().toIso8601String();

VacancyListItem _item(int id, {String? publishedAt, String? updatedAt}) => VacancyListItem(
      id: id,
      role: 'Role $id',
      company: 'Company $id',
      site: 'djinni',
      url: 'https://example.com/$id',
      status: 'inbox',
      publishedAt: publishedAt,
      updatedAt: updatedAt,
    );

void main() {
  testWidgets('shows no section headers when every vacancy is from today', (tester) async {
    final now = DateTime.now();
    final vacancies = [
      _item(1, publishedAt: _utc(now)),
      _item(2, publishedAt: _utc(now.subtract(const Duration(hours: 1)))),
    ];

    await tester.pumpWidget(_harness(InboxVacancyList(
      vacancies: vacancies,
      selectedId: null,
      onSelect: (_) {},
    )));

    expect(find.text('Today'), findsNothing);
    expect(find.text('Earlier'), findsNothing);
    expect(find.text('Nothing for today'), findsNothing);
  });

  testWidgets('shows Today + Nothing-for-today note + Earlier when nothing is from today',
      (tester) async {
    final now = DateTime.now();
    final yesterday = now.subtract(const Duration(days: 1));
    final vacancies = [
      _item(1, publishedAt: _utc(yesterday)),
      _item(2, publishedAt: _utc(yesterday.subtract(const Duration(hours: 2)))),
    ];

    await tester.pumpWidget(_harness(InboxVacancyList(
      vacancies: vacancies,
      selectedId: null,
      onSelect: (_) {},
    )));

    expect(find.text('Today'), findsOneWidget);
    expect(find.text('Nothing for today'), findsOneWidget);
    expect(find.text('Earlier'), findsOneWidget);

    final todayTop = tester.getTopLeft(find.text('Today')).dy;
    final noteTop = tester.getTopLeft(find.text('Nothing for today')).dy;
    final earlierTop = tester.getTopLeft(find.text('Earlier')).dy;
    final item1Top = tester.getTopLeft(find.text('Role 1')).dy;
    expect(todayTop, lessThan(noteTop));
    expect(noteTop, lessThan(earlierTop));
    expect(earlierTop, lessThan(item1Top));
  });

  testWidgets('shows Today header (no note) and Earlier header for a mixed list, keeps all cards',
      (tester) async {
    final now = DateTime.now();
    final startOfToday = DateTime(now.year, now.month, now.day);
    final yesterday = startOfToday.subtract(const Duration(hours: 2));
    final twoDaysAgo = startOfToday.subtract(const Duration(days: 2));

    final vacancies = [
      _item(1, publishedAt: _utc(now)),
      _item(2, publishedAt: _utc(now.subtract(const Duration(hours: 3)))),
      _item(3, publishedAt: _utc(yesterday)),
      _item(4, publishedAt: _utc(twoDaysAgo)),
    ];

    await tester.pumpWidget(_harness(InboxVacancyList(
      vacancies: vacancies,
      selectedId: null,
      onSelect: (_) {},
    )));

    expect(find.text('Today'), findsOneWidget);
    expect(find.text('Nothing for today'), findsNothing);
    expect(find.text('Earlier'), findsOneWidget);
    expect(find.text('Role 1'), findsOneWidget);
    expect(find.text('Role 2'), findsOneWidget);
    expect(find.text('Role 3'), findsOneWidget);
    expect(find.text('Role 4'), findsOneWidget);

    final todayTop = tester.getTopLeft(find.text('Today')).dy;
    final item1Top = tester.getTopLeft(find.text('Role 1')).dy;
    final item2Top = tester.getTopLeft(find.text('Role 2')).dy;
    final earlierTop = tester.getTopLeft(find.text('Earlier')).dy;
    final item3Top = tester.getTopLeft(find.text('Role 3')).dy;

    // Today header before item 1; Earlier header strictly between item 2 and item 3.
    expect(todayTop, lessThan(item1Top));
    expect(item2Top, lessThan(earlierTop));
    expect(earlierTop, lessThan(item3Top));
  });

  testWidgets('vacancies with no publishedAt never trigger section headers on their own',
      (tester) async {
    final vacancies = [
      _item(1, publishedAt: null),
      _item(2, publishedAt: null),
    ];

    await tester.pumpWidget(_harness(InboxVacancyList(
      vacancies: vacancies,
      selectedId: null,
      onSelect: (_) {},
    )));

    expect(find.text('Today'), findsNothing);
    expect(find.text('Earlier'), findsNothing);
    expect(find.text('Nothing for today'), findsNothing);
  });

  testWidgets('todayDividerBasis:null suppresses headers even with a clear today/earlier mix',
      (tester) async {
    // A folder with no divider concept (e.g. Applied/Archive) passes null —
    // verifies that wins even when publishedAt data would otherwise trigger
    // a divider under the default basis.
    final now = DateTime.now();
    final vacancies = [
      _item(1, publishedAt: _utc(now)),
      _item(2, publishedAt: _utc(now.subtract(const Duration(days: 2)))),
    ];

    await tester.pumpWidget(_harness(InboxVacancyList(
      vacancies: vacancies,
      selectedId: null,
      onSelect: (_) {},
      todayDividerBasis: null,
    )));

    expect(find.text('Today'), findsNothing);
    expect(find.text('Earlier'), findsNothing);
    expect(find.text('Nothing for today'), findsNothing);
    expect(find.text('Role 1'), findsOneWidget);
    expect(find.text('Role 2'), findsOneWidget);
  });

  testWidgets('todayDividerBasis:updatedAt checks updatedAt instead of publishedAt',
      (tester) async {
    // Analyzed/Processed sort by updated_at (2026-07-26) — the divider must
    // scan that same field, not publishedAt, or the boundary lands wrong.
    final now = DateTime.now();
    final startOfToday = DateTime(now.year, now.month, now.day);
    final yesterday = startOfToday.subtract(const Duration(hours: 2));

    final vacancies = [
      // publishedAt says "old", but updatedAt (analyzed) says "today".
      _item(1, publishedAt: _utc(yesterday), updatedAt: _utc(now)),
      // publishedAt says "today", but updatedAt (analyzed) says "earlier".
      _item(2, publishedAt: _utc(now), updatedAt: _utc(yesterday)),
    ];

    await tester.pumpWidget(_harness(InboxVacancyList(
      vacancies: vacancies,
      selectedId: null,
      onSelect: (_) {},
      todayDividerBasis: TodayDividerBasis.updatedAt,
    )));

    expect(find.text('Today'), findsOneWidget);
    expect(find.text('Earlier'), findsOneWidget);
    final todayTop = tester.getTopLeft(find.text('Today')).dy;
    final item1Top = tester.getTopLeft(find.text('Role 1')).dy;
    final earlierTop = tester.getTopLeft(find.text('Earlier')).dy;
    final item2Top = tester.getTopLeft(find.text('Role 2')).dy;
    expect(todayTop, lessThan(item1Top));
    expect(item1Top, lessThan(earlierTop));
    expect(earlierTop, lessThan(item2Top));
  });
}
