import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:career_agent/providers/list_panel_provider.dart';

// Resizable + collapsible inbox list panel (2026-07-25) — width persists via
// SharedPreferences, clamped to [kListPanelMinWidth, kListPanelMaxWidth].
// Collapsed state persists separately; the only reopen affordance is the
// nav-rail toggle (app_shell.dart), not anything inside the panel itself.

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('defaults to kListPanelDefaultWidth, not collapsed, when nothing stored', () async {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final state = await container.read(listPanelProvider.future);
    expect(state.width, kListPanelDefaultWidth);
    expect(state.collapsed, false);
  });

  test('setWidth clamps below the minimum', () async {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    await container.read(listPanelProvider.future);

    await container.read(listPanelProvider.notifier).setWidth(50);
    final state = container.read(listPanelProvider).value!;
    expect(state.width, kListPanelMinWidth);
  });

  test('setWidth clamps above the maximum', () async {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    await container.read(listPanelProvider.future);

    await container.read(listPanelProvider.notifier).setWidth(2000);
    final state = container.read(listPanelProvider).value!;
    expect(state.width, kListPanelMaxWidth);
  });

  test('setWidth within range is stored as-is and persists across containers', () async {
    final container1 = ProviderContainer();
    await container1.read(listPanelProvider.future);
    await container1.read(listPanelProvider.notifier).setWidth(420);
    container1.dispose();

    final container2 = ProviderContainer();
    addTearDown(container2.dispose);
    final state = await container2.read(listPanelProvider.future);
    expect(state.width, 420);
  });

  test('toggleCollapsed flips state and persists across containers', () async {
    final container1 = ProviderContainer();
    await container1.read(listPanelProvider.future);
    expect(container1.read(listPanelProvider).value!.collapsed, false);

    await container1.read(listPanelProvider.notifier).toggleCollapsed();
    expect(container1.read(listPanelProvider).value!.collapsed, true);
    container1.dispose();

    final container2 = ProviderContainer();
    addTearDown(container2.dispose);
    final state = await container2.read(listPanelProvider.future);
    expect(state.collapsed, true);

    await container2.read(listPanelProvider.notifier).toggleCollapsed();
    expect(container2.read(listPanelProvider).value!.collapsed, false);
  });
}
