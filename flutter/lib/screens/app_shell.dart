import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/health.dart';
import '../providers/health_provider.dart';
import '../providers/settings_provider.dart';
import '../providers/vacancy_list_provider.dart';
import '../services/notification_service.dart';
import '../widgets/backend_status_dot.dart';
import '../widgets/polling_progress_bar.dart';
import '../widgets/status_line.dart';
import 'vacancy_inbox_screen.dart';
import 'settings_screen.dart';

// Nav destinations
const _kNavItems = [
  _NavItem(Icons.work,             Icons.work_outline,            'Inbox'),
  _NavItem(Icons.pending_actions,  Icons.pending_actions_outlined, 'In Prog.'),
  _NavItem(Icons.check_circle,     Icons.check_circle_outline,    'Applied'),
  _NavItem(Icons.archive,          Icons.archive_outlined,         'Archive'),
  _NavItem(Icons.settings,         Icons.settings_outlined,        'Settings'),
];

// Canvas gradient (matches DESIGN.md decorative background)
const _kCanvasGradient = LinearGradient(
  begin: Alignment.topRight,
  end: Alignment.bottomLeft,
  colors: [Color(0xFFF2ECF4), Color(0xFFDED8E0)],
);

class AppShell extends ConsumerStatefulWidget {
  const AppShell({super.key});

  @override
  ConsumerState<AppShell> createState() => _AppShellState();
}

class _AppShellState extends ConsumerState<AppShell> {
  int _selectedIndex = 0;

  static const _folders = ['inbox', 'in_progress', 'applied', 'archive'];


  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final healthAsync = ref.watch(healthProvider);
    final health = healthAsync.valueOrNull ?? HealthStatus.checking;
    final listAsync = ref.watch(vacancyListProvider);
    final listState = listAsync.valueOrNull;
    final settingsAsync = ref.watch(settingsProvider);
    final settings = settingsAsync.valueOrNull;

    ref.listen<AsyncValue<PollingState>>(vacancyListProvider, (prev, next) {
      final newState = next.valueOrNull;
      if (newState == null) return;
      if (newState.status == PollingStatus.found && newState.newCount > 0) {
        final notificationsEnabled = settings?.notificationsEnabled ?? true;
        if (notificationsEnabled) {
          NotificationService.showNewVacancies(newState.newCount);
        }
      }
    });

    final inboxCount = ref.watch(folderVacanciesProvider('inbox')).length;

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: Container(
        decoration: const BoxDecoration(gradient: _kCanvasGradient),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1440),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: _FloatingContentBlock(
                cs: cs,
                child: Column(
                  children: [
                    // 2px progress bar — flush to top of content block
                    if (listState != null)
                      PollingProgressBar(
                        status: listState.status,
                        pollIntervalSeconds: settings?.pollIntervalSeconds ?? 30,
                        lastUpdatedAt: listState.lastUpdatedAt,
                      ),
                    Expanded(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          // Navigation rail (80px)
                          _AppNavRail(
                            selectedIndex: _selectedIndex,
                            inboxCount: inboxCount,
                            health: health,
                            onSelected: (i) => setState(() => _selectedIndex = i),
                          ),
                          // Thin divider
                          VerticalDivider(
                            width: 1, thickness: 1,
                            color: cs.outlineVariant.withValues(alpha: 0.2),
                          ),
                          // Main content
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                // Status line — shown only on vacancy screens
                                if (listState != null &&
                                    settings != null &&
                                    _selectedIndex < _folders.length)
                                  _StatusHeader(
                                    listState: listState,
                                    settings: settings,
                                    cs: cs,
                                  ),
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
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ── Floating glassmorphic content block ────────────────────────────────────────

class _FloatingContentBlock extends StatelessWidget {
  final ColorScheme cs;
  final Widget child;

  const _FloatingContentBlock({required this.cs, required this.child});

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
        child: Container(
          decoration: BoxDecoration(
            color: cs.surface.withValues(alpha: 0.92),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: cs.outlineVariant.withValues(alpha: 0.3),
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.08),
                blurRadius: 24,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: child,
        ),
      ),
    );
  }
}

// ── Custom navigation rail ────────────────────────────────────────────────────

class _AppNavRail extends StatelessWidget {
  final int selectedIndex;
  final int inboxCount;
  final HealthStatus health;
  final ValueChanged<int> onSelected;

  const _AppNavRail({
    required this.selectedIndex,
    required this.inboxCount,
    required this.health,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;

    return SizedBox(
      width: 80,
      child: Container(
        color: cs.surfaceContainer,
        child: Column(
          children: [
            const SizedBox(height: 24),
            // Brand avatar
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: cs.primaryContainer,
                shape: BoxShape.circle,
              ),
              alignment: Alignment.center,
              child: Text(
                'CA',
                style: TextStyle(
                  color: cs.onPrimaryContainer,
                  fontWeight: FontWeight.w700,
                  fontSize: 13,
                ),
              ),
            ),
            const SizedBox(height: 16),
            // Nav items
            ..._kNavItems.asMap().entries.map((e) {
              final i = e.key;
              final item = e.value;
              final selected = selectedIndex == i;
              final showBadge = i == 0 && inboxCount > 0;
              return _NavRailItem(
                item: item,
                selected: selected,
                badgeCount: showBadge ? inboxCount : 0,
                onTap: () => onSelected(i),
              );
            }),
            const Spacer(),
            // Backend status dot
            Padding(
              padding: const EdgeInsets.only(bottom: 20),
              child: BackendStatusDot(status: health),
            ),
          ],
        ),
      ),
    );
  }
}

class _NavRailItem extends StatelessWidget {
  final _NavItem item;
  final bool selected;
  final int badgeCount;
  final VoidCallback onTap;

  const _NavRailItem({
    required this.item,
    required this.selected,
    required this.badgeCount,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          width: double.infinity,
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            color: selected ? cs.surfaceContainerHighest : Colors.transparent,
            borderRadius: BorderRadius.circular(8),
            border: selected
                ? Border(
                    left: BorderSide(color: cs.primary, width: 3),
                  )
                : null,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Badge(
                isLabelVisible: badgeCount > 0,
                label: Text('$badgeCount'),
                child: Icon(
                  selected ? item.iconFilled : item.iconOutlined,
                  color: selected ? cs.primary : cs.onSurfaceVariant,
                  size: 22,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                item.label,
                style: TextStyle(
                  fontSize: 10,
                  fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                  color: selected ? cs.primary : cs.onSurfaceVariant,
                  fontFamily: 'Hanken Grotesk',
                ),
                textAlign: TextAlign.center,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ── Status header bar above list content ─────────────────────────────────────

class _StatusHeader extends StatelessWidget {
  final PollingState listState;
  final dynamic settings;
  final ColorScheme cs;

  const _StatusHeader({
    required this.listState,
    required this.settings,
    required this.cs,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 6, 16, 6),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(
            color: cs.outlineVariant.withValues(alpha: 0.2),
          ),
        ),
      ),
      child: StatusLine(
        status: listState.status,
        pollIntervalSeconds: settings.pollIntervalSeconds,
        lastUpdatedAt: listState.lastUpdatedAt,
        newCount: listState.newCount,
        fromCache: listState.fromCache,
      ),
    );
  }
}

// ── Data classes ──────────────────────────────────────────────────────────────

class _NavItem {
  final IconData iconFilled;
  final IconData iconOutlined;
  final String label;

  const _NavItem(this.iconFilled, this.iconOutlined, this.label);
}
