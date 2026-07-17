import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/providers/phase_config_provider.dart';
import 'package:career_agent/widgets/phase_llm_config_tile.dart';

PhaseConfig _cfg({
  String provider = 'claude_api',
  String model = 'claude-opus-4-8',
  bool isOverride = false,
}) =>
    PhaseConfig(
      provider: provider,
      model: model,
      thinkingEffort: 'off',
      isOverride: isOverride,
      availableModels: [model],
    );

Widget _harness(Map<String, PhaseConfig> phases) {
  return ProviderScope(
    overrides: [
      phaseConfigProvider.overrideWith(() => _FakePhaseConfigNotifier(phases)),
    ],
    child: const MaterialApp(
      home: Scaffold(body: SingleChildScrollView(child: PhaseRoutingSection())),
    ),
  );
}

class _FakePhaseConfigNotifier extends PhaseConfigNotifier {
  final Map<String, PhaseConfig> _initial;
  _FakePhaseConfigNotifier(this._initial);

  @override
  Future<Map<String, PhaseConfig>> build() async => _initial;
}

void main() {
  testWidgets('collapsed by default — no phase cards visible', (tester) async {
    await tester.pumpWidget(_harness({for (final p in kPhaseOrder) p: _cfg()}));
    await tester.pump();

    expect(find.text('Advanced: Per-Phase Routing'), findsOneWidget);
    expect(find.text(kPhaseLabels['prefilter']!), findsNothing);
  });

  testWidgets('tapping header expands and shows all 6 phase cards', (tester) async {
    await tester.pumpWidget(_harness({for (final p in kPhaseOrder) p: _cfg()}));
    await tester.pump();

    await tester.tap(find.text('Advanced: Per-Phase Routing'));
    await tester.pumpAndSettle();

    for (final phase in kPhaseOrder) {
      expect(find.text(kPhaseLabels[phase]!), findsOneWidget);
    }
    // All unpinned — "Using default" shown once per phase, no reset buttons.
    expect(find.text('Using default'), findsNWidgets(kPhaseOrder.length));
    expect(find.text('Reset to default'), findsNothing);
  });

  testWidgets('overridden phase shows Reset button, others still show default', (tester) async {
    final phases = {for (final p in kPhaseOrder) p: _cfg()};
    phases['prefilter'] = _cfg(provider: 'ollama_api', model: 'gemma3:2b', isOverride: true);

    await tester.pumpWidget(_harness(phases));
    await tester.pump();
    await tester.tap(find.text('Advanced: Per-Phase Routing'));
    await tester.pumpAndSettle();

    expect(find.text('Reset to default'), findsOneWidget);
    expect(find.text('Using default'), findsNWidgets(kPhaseOrder.length - 1));
  });

  testWidgets('ollama-pinned phase hides the effort control', (tester) async {
    final phases = {for (final p in kPhaseOrder) p: _cfg()};
    phases['prefilter'] = _cfg(provider: 'ollama_api', model: 'gemma3:2b', isOverride: true);

    await tester.pumpWidget(_harness(phases));
    await tester.pump();
    await tester.tap(find.text('Advanced: Per-Phase Routing'));
    await tester.pumpAndSettle();

    // Effort segmented button uses 'Off'/'Low'/... labels — claude_api phases
    // show it (5 of them), the ollama-pinned prefilter does not.
    expect(find.text('Off'), findsNWidgets(kPhaseOrder.length - 1));
  });
}
