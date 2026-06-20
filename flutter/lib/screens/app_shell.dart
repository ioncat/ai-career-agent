import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/health.dart';
import '../providers/health_provider.dart';
import '../providers/settings_provider.dart';
import '../providers/vacancy_list_provider.dart';
import '../widgets/backend_status_dot.dart';
import '../widgets/polling_progress_bar.dart';
import '../widgets/status_line.dart';
import 'vacancy_inbox_screen.dart';

class AppShell extends ConsumerStatefulWidget {
  const AppShell({super.key});

  @override
  ConsumerState<AppShell> createState() => _AppShellState();
}

class _AppShellState extends ConsumerState<AppShell> {
  int _selectedIndex = 0;

  static const _folders = ['inbox', 'in_progress', 'applied', 'archive'];
  static const _labels = ['Inbox', 'In Progress', 'Applied', 'Archive'];
  static const _icons = [
    Icons.inbox_outlined,
    Icons.work_outline,
    Icons.check_circle_outline,
    Icons.archive_outlined,
  ];

  @override
  Widget build(BuildContext context) {
    final healthAsync = ref.watch(healthProvider);
    final health = healthAsync.valueOrNull ?? HealthStatus.checking;
    final listAsync = ref.watch(vacancyListProvider);
    final listState = listAsync.valueOrNull;
    final settingsAsync = ref.watch(settingsProvider);
    final settings = settingsAsync.valueOrNull;

    final inboxCount = ref.watch(folderVacanciesProvider('inbox')).length;

    return Scaffold(
      body: Column(
        children: [
          // Polling progress bar — 2px at very top
          if (listState != null)
            PollingProgressBar(
              status: listState.status,
              pollIntervalSeconds: settings?.pollIntervalSeconds ?? 30,
              lastUpdatedAt: listState.lastUpdatedAt,
            ),
          Expanded(
            child: Row(
              children: [
                // NavigationRail
                NavigationRail(
                  selectedIndex: _selectedIndex,
                  onDestinationSelected: (i) {
                    if (i < _folders.length) {
                      setState(() => _selectedIndex = i);
                    } else {
                      // Settings
                      setState(() => _selectedIndex = i);
                    }
                  },
                  leading: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    child: Column(
                      children: [
                        const Icon(Icons.work, size: 28),
                        const SizedBox(height: 4),
                        Text('Career\nAgent',
                            textAlign: TextAlign.center,
                            style:
                                Theme.of(context).textTheme.labelSmall),
                      ],
                    ),
                  ),
                  trailing: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      BackendStatusDot(status: health),
                      const SizedBox(height: 8),
                      IconButton(
                        icon: const Icon(Icons.settings_outlined, size: 20),
                        tooltip: 'Settings',
                        onPressed: () {},
                      ),
                    ],
                  ),
                  destinations: [
                    ..._folders.asMap().entries.map((e) {
                      final i = e.key;
                      final count = i == 0 ? inboxCount : 0;
                      return NavigationRailDestination(
                        icon: Badge(
                          isLabelVisible: i == 0 && count > 0,
                          label: Text('$count'),
                          child: Icon(_icons[i]),
                        ),
                        selectedIcon: Icon(_icons[i]),
                        label: Text(_labels[i]),
                      );
                    }),
                  ],
                ),
                const VerticalDivider(width: 1, thickness: 1),
                // Main content
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Status line
                      if (listState != null && settings != null)
                        Padding(
                          padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
                          child: StatusLine(
                            status: listState.status,
                            pollIntervalSeconds: settings.pollIntervalSeconds,
                            lastUpdatedAt: listState.lastUpdatedAt,
                            newCount: listState.newCount,
                          ),
                        ),
                      const Divider(height: 1),
                      Expanded(
                        child: _selectedIndex < _folders.length
                            ? VacancyInboxScreen(
                                folder: _folders[_selectedIndex])
                            : const Center(child: Text('Settings')),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
