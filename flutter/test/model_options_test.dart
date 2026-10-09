import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/utils/model_options.dart';

Widget _dropdown(List<String> available, String? selected) {
  final o = modelDropdownOptions(available, selected);
  return MaterialApp(
    home: Scaffold(
      body: DropdownButton<String>(
        value: selected,
        items: [
          for (final m in o.items) DropdownMenuItem(value: m, child: Text(m)),
        ],
        onChanged: (_) {},
      ),
    ),
  );
}

void main() {
  test('duplicates are dropped, order kept', () {
    final o = modelDropdownOptions([
      'gemma4:e2b',
      'gemma4:e2b',
      'qwen3:8b',
    ], 'gemma4:e2b');
    expect(o.items, ['gemma4:e2b', 'qwen3:8b']);
    expect(o.selectedMissing, isFalse);
  });

  test('a selected value missing from the list is added and flagged', () {
    final o = modelDropdownOptions(['qwen3:8b'], 'gemma4:e2b');
    expect(o.items, ['qwen3:8b', 'gemma4:e2b']);
    expect(o.selectedMissing, isTrue);
  });

  test('no selection and an empty list stay empty', () {
    final o = modelDropdownOptions(const [], null);
    expect(o.items, isEmpty);
    expect(o.selectedMissing, isFalse);
  });

  testWidgets('a duplicated model no longer breaks the dropdown', (
    tester,
  ) async {
    await tester.pumpWidget(
      _dropdown(['gemma4:e2b', 'gemma4:e2b', 'qwen3:8b'], 'gemma4:e2b'),
    );
    expect(tester.takeException(), isNull);
    expect(find.text('gemma4:e2b'), findsOneWidget);
  });

  testWidgets('a value not in the list no longer breaks the dropdown', (
    tester,
  ) async {
    await tester.pumpWidget(_dropdown(['qwen3:8b'], 'gemma4:e2b'));
    expect(tester.takeException(), isNull);
  });
}
