import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/models/vacancy.dart';
import 'package:career_agent/screens/vacancy_inbox_screen.dart';

// "Today / Earlier" divider (2026-07-24, explicit user ask) — purely visual
// marker at the boundary between today's vacancies and older ones. List is
// already sorted newest-first; the divider is inserted at the first index
// whose publishedAt falls before local midnight, no re-sorting/grouping.

Widget _harness(Widget child) => ProviderScope(
      child: MaterialApp(home: Scaffold(body: child)),
    );

String _utc(DateTime local) => local.toUtc().toIso8601String();

VacancyListItem _item(int id, {String? publishedAt}) => VacancyListItem(
      id: id,
      role: 'Role $id',
      company: 'Company $id',
      site: 'djinni',
      url: 'https://example.com/$id',
      status: 'inbox',
      publishedAt: publishedAt,
    );

void main() {
  testWidgets('shows no divider when every vacancy is from today', (tester) async {
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

    expect(find.text('Earlier'), findsNothing);
  });

  testWidgets('places divider before the first item when nothing is from today', (tester) async {
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

    expect(find.text('Earlier'), findsOneWidget);
    final dividerTop = tester.getTopLeft(find.text('Earlier')).dy;
    final item1Top = tester.getTopLeft(find.text('Role 1')).dy;
    expect(dividerTop, lessThan(item1Top));
  });

  testWidgets('inserts divider between today and earlier vacancies, keeps all cards', (tester) async {
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

    expect(find.text('Earlier'), findsOneWidget);
    expect(find.text('Role 1'), findsOneWidget);
    expect(find.text('Role 2'), findsOneWidget);
    expect(find.text('Role 3'), findsOneWidget);
    expect(find.text('Role 4'), findsOneWidget);

    // Divider must sit strictly between item 2 (today) and item 3 (earlier).
    final dividerTop = tester.getTopLeft(find.text('Earlier')).dy;
    final item2Top = tester.getTopLeft(find.text('Role 2')).dy;
    final item3Top = tester.getTopLeft(find.text('Role 3')).dy;
    expect(item2Top, lessThan(dividerTop));
    expect(dividerTop, lessThan(item3Top));
  });

  testWidgets('vacancies with no publishedAt never trigger a divider on their own', (tester) async {
    final vacancies = [
      _item(1, publishedAt: null),
      _item(2, publishedAt: null),
    ];

    await tester.pumpWidget(_harness(InboxVacancyList(
      vacancies: vacancies,
      selectedId: null,
      onSelect: (_) {},
    )));

    expect(find.text('Earlier'), findsNothing);
  });
}
