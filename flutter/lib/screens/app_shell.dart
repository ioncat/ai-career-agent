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
import 'settings_screen.dart';

class AppShell extends ConsumerStatefulWidget {
  const AppShell({super.key});

  @override
  ConsumerState<AppShell> createState() => _AppShellState();
}

class _AppShellState extends ConsumerState<AppShell> {
  int _selectedIndex = 0;

  static const _folders = ['inbox', 'in_progress', 'applied', 'archive'];

  static const _destinations = [
    (Icons.inbox_outlined, 'Inbox'),
    (Icons.work_outline, 'In Progress'),
    (Icons.check_circle_outline, 'Applied'),
    (Icons.archive_outlined, 'Archive'),
    (Icons.settings_outlined, 'Settings'),
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
          // 2px polling progress bar at very top
          if (listState != null)
            PollingProgressBar(
              status: listState.status,
              pollIntervalSeconds: settings?.pollIntervalSeconds ?? 30,
              lastUpdatedAt: listState.lastUpdatedAt,
            ),
          Expanded(
            child: Row(
              children: [
                NavigationRail(
                  selectedIndex: _selectedIndex,
                  onDestinationSelected: (i) =>
                      setState(() => _selectedIndex = i),
                  leading: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    child: Column(
                      children: [
                        const Icon(Icons.work, size: 28),
                        const SizedBox(height: 4),
                        Text('Career\nAgent',
                            textAlign: TextAlign.center,
                            style: Theme.of(context).textTheme.labelSmall),
                      ],
                    ),
                  ),
                  trailing: Padding(
                    padding: const EdgeInsets.only(bottom: 16),
                    child: BackendStatusDot(status: health),
                  ),
                  destinations: _destinations.asMap().entries.map((e) {
                    final i = e.key;
                    final (icon, label) = e.value;
                    // Inbox badge
                    final showBadge = i == 0 && inboxCount > 0;
                    return NavigationRailDestination(
                      icon: Badge(
                        isLabelVisible: showBadge,
                        label: Text('$inboxCount'),
                        child: Icon(icon),
                      ),
                      selectedIcon: Icon(icon),
                      label: Text(label),
                    );
                  }).toList(),
                ),
                const VerticalDivider(width: 1, thickness: 1),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
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
                            : const SettingsScreen(),
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
