import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/screens/app_shell.dart';

// Nav-rail toggle for the resizable/collapsible inbox list panel
// (2026-07-25) — the only reopen affordance once the panel is collapsed,
// since the panel itself is hidden (no in-panel control would be reachable).

Widget _harness(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  testWidgets('shows the "hide" icon and tooltip when not collapsed', (tester) async {
    await tester.pumpWidget(_harness(
      ListPanelToggleButton(collapsed: false, onTap: () {}),
    ));

    expect(find.byIcon(Icons.view_sidebar), findsOneWidget);
    expect(find.byIcon(Icons.view_sidebar_outlined), findsNothing);
    expect(find.byTooltip('Hide vacancy list'), findsOneWidget);
  });

  testWidgets('shows the "show" icon and tooltip when collapsed', (tester) async {
    await tester.pumpWidget(_harness(
      ListPanelToggleButton(collapsed: true, onTap: () {}),
    ));

    expect(find.byIcon(Icons.view_sidebar_outlined), findsOneWidget);
    expect(find.byIcon(Icons.view_sidebar), findsNothing);
    expect(find.byTooltip('Show vacancy list'), findsOneWidget);
  });

  testWidgets('tapping calls onTap', (tester) async {
    var tapped = false;
    await tester.pumpWidget(_harness(
      ListPanelToggleButton(collapsed: false, onTap: () => tapped = true),
    ));

    await tester.tap(find.byType(ListPanelToggleButton));
    expect(tapped, true);
  });
}
