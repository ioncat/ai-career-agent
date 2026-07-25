import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Width bounds for the resizable vacancy-list panel (`vacancy_inbox_screen.dart`).
/// Min keeps the header's controls (filter/refresh/skip-all menu, search box)
/// comfortably clear of the overflow floor found in the 2026-07-24 badge/header
/// overflow saga (tests reproduced breakage around 140-160px for sub-widgets;
/// 280px leaves real margin for the whole panel, not just one card).
const double kListPanelMinWidth = 280;
const double kListPanelMaxWidth = 640;
const double kListPanelDefaultWidth = 360;

class ListPanelState {
  final double width;
  final bool collapsed;

  const ListPanelState({
    this.width = kListPanelDefaultWidth,
    this.collapsed = false,
  });

  ListPanelState copyWith({double? width, bool? collapsed}) {
    return ListPanelState(
      width: width ?? this.width,
      collapsed: collapsed ?? this.collapsed,
    );
  }
}

class ListPanelNotifier extends AsyncNotifier<ListPanelState> {
  static const _keyWidth = 'list_panel_width';
  static const _keyCollapsed = 'list_panel_collapsed';

  @override
  Future<ListPanelState> build() async {
    final prefs = await SharedPreferences.getInstance();
    final width = prefs.getDouble(_keyWidth) ?? kListPanelDefaultWidth;
    return ListPanelState(
      width: width.clamp(kListPanelMinWidth, kListPanelMaxWidth),
      collapsed: prefs.getBool(_keyCollapsed) ?? false,
    );
  }

  /// Persists a new width (call once, e.g. on drag end — not per drag frame).
  Future<void> setWidth(double width) async {
    final clamped = width.clamp(kListPanelMinWidth, kListPanelMaxWidth);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setDouble(_keyWidth, clamped);
    final current = state.valueOrNull ?? const ListPanelState();
    state = AsyncData(current.copyWith(width: clamped));
  }

  Future<void> toggleCollapsed() async {
    final current = state.valueOrNull ?? const ListPanelState();
    final next = !current.collapsed;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_keyCollapsed, next);
    state = AsyncData(current.copyWith(collapsed: next));
  }
}

final listPanelProvider =
    AsyncNotifierProvider<ListPanelNotifier, ListPanelState>(ListPanelNotifier.new);
