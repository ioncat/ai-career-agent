import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/screens/vacancy_inbox_screen.dart';

// InboxFilterPanel's "Title blocked" chip (2026-07-24) — filters to vacancies
// flagged by Stage 1 (title/domain, deterministic) specifically, not "any
// blocker" (which would also include Stage 2 LLM content blocks). Backed by
// the real `blockerStage` field, not string-matching blockerReasons.

Widget _harness(Widget child) => MaterialApp(home: Scaffold(body: child));

InboxFilterPanel _panel({
  bool starredOnly = false,
  bool blockedOnly = false,
  VoidCallback? onToggleStarred,
  VoidCallback? onToggleBlocked,
  bool hasActiveFilters = false,
}) {
  return InboxFilterPanel(
    availableStatuses: const {},
    selectedStatuses: const {},
    onStatusToggle: (_) {},
    availableSites: const {},
    selectedSites: const {},
    onSiteToggle: (_) {},
    starredOnly: starredOnly,
    onToggleStarred: onToggleStarred ?? () {},
    blockedOnly: blockedOnly,
    onToggleBlocked: onToggleBlocked ?? () {},
    onPickFrom: () {},
    onPickTo: () {},
    onClearDates: () {},
    hasActiveFilters: hasActiveFilters,
    onClearAll: () {},
  );
}

void main() {
  testWidgets('renders a "Title blocked" chip, unselected by default', (tester) async {
    await tester.pumpWidget(_harness(_panel()));

    final chip = tester.widget<FilterChip>(find.ancestor(
      of: find.text('Title blocked'),
      matching: find.byType(FilterChip),
    ));
    expect(chip.selected, isFalse);
  });

  testWidgets('tapping the chip fires onToggleBlocked', (tester) async {
    var toggled = false;
    await tester.pumpWidget(_harness(_panel(onToggleBlocked: () => toggled = true)));

    await tester.tap(find.text('Title blocked'));
    expect(toggled, isTrue);
  });

  testWidgets('chip reflects selected state independently of Starred', (tester) async {
    await tester.pumpWidget(_harness(_panel(blockedOnly: true, starredOnly: false)));

    final blockedChip = tester.widget<FilterChip>(find.ancestor(
      of: find.text('Title blocked'),
      matching: find.byType(FilterChip),
    ));
    final starredChip = tester.widget<FilterChip>(find.ancestor(
      of: find.text('Starred'),
      matching: find.byType(FilterChip),
    ));
    expect(blockedChip.selected, isTrue);
    expect(starredChip.selected, isFalse);
  });
}
