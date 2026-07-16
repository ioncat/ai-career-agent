import 'dart:convert';
import 'dart:io';
import 'dart:ui';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/health.dart';
import '../providers/health_provider.dart';
import '../providers/notification_provider.dart';
import '../providers/settings_provider.dart';
import '../providers/vacancy_list_provider.dart';
import '../repositories/vacancy_repository.dart';
import '../services/notification_service.dart';
import '../widgets/backend_status_dot.dart';
import '../widgets/polling_progress_bar.dart';
import '../widgets/processing_wrapper.dart' show SnakePainter;
import '../widgets/status_line.dart';
import 'vacancy_inbox_screen.dart';
import 'settings_screen.dart';

// Nav destinations — 5-stage taxonomy (mirrors core/vacancy_stage.py) + Settings.
// Order must match _AppShellState._folders below (index-aligned).
const _kNavItems = [
  _NavItem(Icons.work,             Icons.work_outline,            'Inbox'),
  _NavItem(Icons.fact_check,       Icons.fact_check_outlined,      'Analyzed'),
  _NavItem(Icons.description,      Icons.description_outlined,     'Processed'),
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

  static const _folders = ['inbox', 'analyzed', 'processed', 'applied', 'archive'];

  Future<void> _importJd() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['md', 'txt'],
      allowMultiple: false,
    );
    if (result == null || result.files.isEmpty) return;
    final file = result.files.first;
    var bytes = file.bytes;
    if (bytes == null && file.path != null) {
      bytes = await File(file.path!).readAsBytes();
    }
    if (bytes == null) return;

    final content = utf8.decode(bytes, allowMalformed: true);
    final settings = ref.read(settingsProvider).valueOrNull;
    if (settings == null) return;
    final repo = VacancyRepository(baseUrl: settings.apiUrl);

    if (!mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      final (:vacancyId, :title) = await repo.importJd(
        content: content,
        filename: file.name,
        userId: 1,
      );
      ref.read(vacancyListProvider.notifier).refresh();
      if (!mounted) return;
      messenger.showSnackBar(SnackBar(
        content: Text('Imported: $title (#$vacancyId)'),
        duration: const Duration(seconds: 5),
      ));
    } catch (e) {
      if (!mounted) return;
      messenger.showSnackBar(SnackBar(
        content: Text('Import failed: $e'),
        backgroundColor: Theme.of(context).colorScheme.error,
        duration: const Duration(seconds: 4),
      ));
    }
  }

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
      if (newState.status == PollingStatus.found &&
          newState.newAnalyzedCount > 0 &&
          (settings?.notificationsEnabled ?? true)) {
        NotificationService.showNewVacancies(newState.newAnalyzedCount);
      }
    });

    // Pipeline event notifications — show SnackBar + OS notification for each fresh event
    ref.listen<AsyncValue<NotificationState>>(notificationProvider,
        (prev, next) {
      final state = next.valueOrNull;
      if (state == null || state.fresh.isEmpty) return;
      if (!(settings?.notificationsEnabled ?? true)) return;

      for (final n in state.fresh) {
        // OS-level desktop notification
        NotificationService.showPipelineEvent(n);

        // In-app SnackBar (non-blocking)
        if (context.mounted) {
          final color = n.isFailure
              ? Theme.of(context).colorScheme.error
              : Theme.of(context).colorScheme.primary;
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                n.title.isNotEmpty ? n.title : n.event,
                style: const TextStyle(fontSize: 13),
              ),
              backgroundColor: color.withValues(alpha: 0.9),
              duration: const Duration(seconds: 4),
              behavior: SnackBarBehavior.floating,
              margin: const EdgeInsets.all(16),
            ),
          );
        }
      }
    });

    final inboxCount = ref.watch(folderVacanciesProvider('inbox')).length;
    final notifState = ref.watch(notificationProvider).valueOrNull;
    final unreadNotifCount = notifState?.unreadCount ?? 0;

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
                            unreadNotifCount: unreadNotifCount,
                            onSelected: (i) => setState(() => _selectedIndex = i),
                            onAddVacancy: _importJd,
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
                                    health: health,
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
  final int unreadNotifCount;
  final ValueChanged<int> onSelected;
  final VoidCallback onAddVacancy;

  const _AppNavRail({
    required this.selectedIndex,
    required this.inboxCount,
    required this.unreadNotifCount,
    required this.onSelected,
    required this.onAddVacancy,
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
            // Main nav items: Inbox, Analyzed, Processed, Applied, Archive (indices 0–4)
            ..._kNavItems.take(5).toList().asMap().entries.map((e) {
              final i = e.key;
              return _NavRailItem(
                item: e.value,
                selected: selectedIndex == i,
                badgeCount: i == 0 ? inboxCount : 0,
                onTap: () => onSelected(i),
              );
            }),
            // Add vacancy button — in the same group as nav items
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
              child: _AddVacancyButton(onTap: onAddVacancy),
            ),
            const Spacer(),
            // Settings (index 5) — at the bottom, rarely used
            _NavRailItem(
              item: _kNavItems[5],
              selected: selectedIndex == 5,
              badgeCount: unreadNotifCount,
              onTap: () => onSelected(5),
            ),
            const SizedBox(height: 12),
          ],
        ),
      ),
    );
  }
}

// ── Add Vacancy button with snake-on-hover ────────────────────────────────────

class _AddVacancyButton extends StatefulWidget {
  final VoidCallback onTap;
  const _AddVacancyButton({required this.onTap});

  @override
  State<_AddVacancyButton> createState() => _AddVacancyButtonState();
}

class _AddVacancyButtonState extends State<_AddVacancyButton>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  bool _hovered = false;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2200),
    );
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;

    return Tooltip(
      message: 'Add new vacancy',
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        onEnter: (_) {
          setState(() => _hovered = true);
          _ctrl.repeat();
        },
        onExit: (_) {
          setState(() => _hovered = false);
          _ctrl.stop();
        },
        child: GestureDetector(
          onTap: widget.onTap,
          child: Stack(
            children: [
              AnimatedContainer(
                duration: const Duration(milliseconds: 180),
                width: double.infinity,
                padding: const EdgeInsets.symmetric(vertical: 10),
                decoration: BoxDecoration(
                  color: _hovered
                      ? cs.primaryContainer.withValues(alpha: 0.4)
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(8),
                  border: _hovered
                      ? null
                      : Border.all(
                          color: cs.outlineVariant.withValues(alpha: 0.7),
                          width: 1.5,
                        ),
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.note_add_outlined,
                      color: _hovered ? cs.primary : cs.onSurfaceVariant,
                      size: 22,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Add',
                      style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                        color: _hovered ? cs.primary : cs.onSurfaceVariant,
                        fontFamily: 'Hanken Grotesk',
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
              if (_hovered)
                Positioned.fill(
                  child: IgnorePointer(
                    child: AnimatedBuilder(
                      animation: _ctrl,
                      builder: (_, _) => CustomPaint(
                        painter: SnakePainter(
                          progress: _ctrl.value,
                          color: cs.primary,
                          radius: 8,
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

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
        mouseCursor: SystemMouseCursors.click,
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
                label: Text(badgeCount > 99 ? '99+' : '$badgeCount'),
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
  final HealthStatus health;
  final ColorScheme cs;

  const _StatusHeader({
    required this.listState,
    required this.settings,
    required this.health,
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
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          BackendStatusDot(status: health),
          const SizedBox(width: 8),
          StatusLine(
            status: listState.status,
            pollIntervalSeconds: settings.pollIntervalSeconds,
            lastUpdatedAt: listState.lastUpdatedAt,
            newCount: listState.newCount,
            fromCache: listState.fromCache,
          ),
        ],
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
