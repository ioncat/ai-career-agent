import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:career_agent/main.dart';

void main() {
  testWidgets('app smoke test — builds without crash', (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: CareerAgentApp()));
    await tester.pump();
    expect(find.byType(CareerAgentApp), findsOneWidget);
  });
}
