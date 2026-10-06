import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/screens/analytics_screen.dart';

// The Market and Applied charts both end with a "Total" line (2026-10-06):
// the sum of the bars, so the user does not add them up by eye.

Widget _harness(TagChart chart) => MaterialApp(
      home: Scaffold(body: SingleChildScrollView(child: SizedBox(width: 640, child: chart))),
    );

Widget _sections() => ChartsRow(
      left: const TagChart(
        tagCounts: {'igaming': 50, 'fintech': 30, 'mobile': 10, 'b2c': 5},
        total: 100,
        untagged: 5,
      ),
      right: const TagChart(tagCounts: {'igaming': 3}, total: 3, untagged: 0),
    );

Widget _sized(double width, Widget child) => MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(child: SizedBox(width: width, child: child)),
      ),
    );

void main() {
  // The two charts sit side by side with a divider between them, and stack
  // (still divided) on a narrow window. Both must lay out without exceptions —
  // the side-by-side form uses IntrinsicHeight, which rejects LayoutBuilder.
  testWidgets('wide window: charts side by side, both Totals visible, vertical divider',
      (tester) async {
    await tester.pumpWidget(_sized(1000, _sections()));
    expect(tester.takeException(), isNull);
    expect(find.text('100 (100%)'), findsOneWidget);
    expect(find.text('3 (100%)'), findsOneWidget);
    expect(find.byType(VerticalDivider), findsOneWidget);
    // inside the charts: left has the "untagged" separator + Total line, right only Total
    expect(find.byType(Divider), findsNWidgets(3));
  });

  testWidgets('narrow window: charts stacked, separated by a horizontal divider',
      (tester) async {
    await tester.pumpWidget(_sized(500, _sections()));
    expect(tester.takeException(), isNull);
    expect(find.byType(VerticalDivider), findsNothing);
    expect(find.byKey(const Key('charts-divider')), findsOneWidget);
    expect(find.text('100 (100%)'), findsOneWidget);
    expect(find.text('3 (100%)'), findsOneWidget);
  });

  testWidgets('shows a Total line equal to the sum of the bars', (tester) async {
    await tester.pumpWidget(_harness(const TagChart(
      tagCounts: {'igaming': 5, 'fintech': 3},
      total: 10,
      untagged: 2,
    )));
    expect(find.text('Total'), findsOneWidget);
    expect(find.byKey(const Key('chart-total')), findsOneWidget);
    expect(find.text('10 (100%)'), findsOneWidget);
  });

  testWidgets('Total is shown even when there are no untagged vacancies', (tester) async {
    await tester.pumpWidget(_harness(const TagChart(
      tagCounts: {'igaming': 4},
      total: 4,
      untagged: 0,
    )));
    expect(find.text('4 (100%)'), findsOneWidget);
  });

  testWidgets('empty chart shows only the empty message, no Total line', (tester) async {
    await tester.pumpWidget(_harness(const TagChart(
      tagCounts: {},
      total: 0,
      untagged: 0,
      emptyMessage: 'No applications yet.',
    )));
    expect(find.text('No applications yet.'), findsOneWidget);
    expect(find.text('Total'), findsNothing);
  });
}
