import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/vacancy.dart';
import '../providers/list_panel_provider.dart';
import '../providers/read_vacancies_provider.dart';
import '../providers/settings_provider.dart';
import '../providers/vacancy_list_provider.dart';
import '../repositories/vacancy_repository.dart';
import '../utils/backend_time.dart';
import '../widgets/processing_wrapper.dart';
import '../widgets/vacancy_card.dart';
import 'vacancy_detail_screen.dart';

// ─── Screen ──────────────────────────────────────────────────────────────────

class VacancyInboxScreen extends ConsumerStatefulWidget {
  final String folder;

  const VacancyInboxScreen({super.key, required this.folder});

  @override
  ConsumerState<VacancyInboxScreen> createState() => _VacancyInboxScreenState();
}

class _VacancyInboxScreenState extends ConsumerState<VacancyInboxScreen> {
  VacancyListItem? _selected;
  bool _crossFolderNav = false;
  final _searchController = TextEditingController();
  String _searchQuery = '';

  // ── Mass actions (BACKLOG "Batch Analysis Mode") ──────────────────────────
  bool _multiSelectMode = false;
  final Set<int> _selectedIds = {};
  bool _batchRunning = false;
  int _batchDone = 0;
  int _batchTotal = 0;
  String _batchLabel = '';

  // Live width while the divider is being dragged — kept as local State so
  // resize is smooth (no SharedPreferences write per drag frame); only
  // committed to listPanelProvider (persisted) on drag end.
  double? _dragWidth;

  VacancyRepository get _repo {
    final apiUrl = ref.read(settingsProvider).valueOrNull?.apiUrl ?? 'http://localhost:8080';
    return VacancyRepository(baseUrl: apiUrl);
  }

  void _enterMultiSelect(int firstId) {
    setState(() {
      _multiSelectMode = true;
      _selectedIds
        ..clear()
        ..add(firstId);
    });
  }

  /// Header button entry point (2026-07-25) — long-press-to-enter was found
  /// unintuitive on desktop ("без прочтения документации никогда не
  /// додумаешься"). Kept long-press too (good pattern for the mobile port,
  /// EPIC-28) rather than removing it — this is just a second, discoverable
  /// way in. Unlike long-press, nothing is pre-selected; unlike exiting,
  /// toggling off clears any in-progress selection.
  void _toggleMultiSelectMode() {
    setState(() {
      _multiSelectMode = !_multiSelectMode;
      if (!_multiSelectMode) _selectedIds.clear();
    });
  }

  void _toggleCheck(int id) {
    setState(() {
      if (_selectedIds.contains(id)) {
        _selectedIds.remove(id);
      } else {
        _selectedIds.add(id);
      }
    });
  }

  void _exitMultiSelect() {
    setState(() {
      _multiSelectMode = false;
      _selectedIds.clear();
    });
  }

  /// Runs one action per selected vacancy, strictly sequential — never
  /// parallel. Local Ollama prefilter calls corrupt each other under
  /// concurrent load (found 2026-07-17: 18-24 min stalls instead of ~15-30s),
  /// and even for the cheap actions (analyze/decline) sequential keeps this
  /// simple and gives honest per-item progress instead of a burst of
  /// simultaneous requests.
  /// `ids` defaults to the manual multi-select set; pass an explicit list to
  /// drive a batch without ever entering multi-select mode (e.g. "Skip all
  /// with blockers" — auto-selects everything flagged, no manual picking).
  Future<void> _runBatch(String label, Future<void> Function(int id) action, {List<int>? ids}) async {
    final targetIds = ids ?? _selectedIds.toList();
    setState(() {
      _batchRunning = true;
      _batchDone = 0;
      _batchTotal = targetIds.length;
      _batchLabel = label;
    });
    var succeeded = 0;
    var failed = 0;
    for (final id in targetIds) {
      try {
        await action(id);
        succeeded++;
      } catch (_) {
        failed++;
      }
      if (mounted) setState(() => _batchDone++);
    }
    if (!mounted) return;
    setState(() => _batchRunning = false);
    ref.read(vacancyListProvider.notifier).refresh();
    _exitMultiSelect();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(failed == 0
            ? '$label: $succeeded/${targetIds.length} done'
            : '$label: $succeeded/${targetIds.length} done, $failed failed'),
        backgroundColor: failed == 0 ? null : Colors.orange,
      ),
    );
  }

  Future<void> _batchAnalyze() => _runBatch('Analyze', (id) => _repo.analyze(id));
  Future<void> _batchCheckBlockers() => _runBatch('Check blockers', (id) => _repo.runPrefilter(id));
  Future<void> _batchSkip() => _runBatch('Skip', (id) => _repo.decline(id));

  /// Standalone action — never enters multi-select, no manual picking.
  /// Auto-selects everything currently visible flagged at the given
  /// pre-filter stage and skips it. Reuses _runBatch's sequential-execution
  /// + progress UI/snackbar, just with an explicit id list instead of
  /// _selectedIds.
  ///
  /// Split into two separate stage-scoped actions (2026-07-24, explicit user
  /// ask) rather than one "skip every blocker" button — Stage 1 (title,
  /// deterministic) is 100% mechanical, safe to bulk-clear; Stage 2
  /// (content, LLM-judged) is less certain and worth a human glance before
  /// archiving, so it gets its own separate confirm rather than being
  /// silently swept up by the same click.
  ///
  /// Confirms first regardless — a single accidental click archives every
  /// matching vacancy at once, unlike the manual multi-select actions where
  /// the selection itself is the deliberate step.
  Future<void> _skipAllByStage(List<VacancyListItem> visible, String stage, String stageLabel) async {
    final matched = visible.where((v) => v.blockerStage == stage).toList();
    if (matched.isEmpty) return;

    // Lists every matching vacancy with its own checkbox (default: all
    // checked) instead of a bare count — a blind "skip N" confirm commits
    // based on a number alone; seeing the actual list lets the user rescue
    // a pre-filter false-positive without aborting the whole batch
    // (2026-07-28, explicit user ask).
    final selectedIds = await showDialog<List<int>>(
      context: context,
      builder: (context) => SkipConfirmDialog(stageLabel: stageLabel, vacancies: matched),
    );
    if (selectedIds == null || selectedIds.isEmpty) return;

    await _runBatch('Skip', (id) => _repo.decline(id), ids: selectedIds);
  }

  void _onSkipped() {
    _crossFolderNav = false;
    final currentId = _selected?.id;
    if (currentId == null) return;
    final vacancies = ref.read(folderVacanciesProvider(widget.folder));
    final filtered = _filter(vacancies);
    final idx = filtered.indexWhere((v) => v.id == currentId);
    VacancyListItem? next;
    if (idx >= 0 && idx < filtered.length - 1) {
      next = filtered[idx + 1];
    } else if (idx > 0) {
      next = filtered[idx - 1];
    }
    setState(() => _selected = next);
  }

  void _selectByIdAny(int id) {
    final all = ref.read(vacancyListProvider).valueOrNull?.vacancies ?? [];
    final target = all.where((v) => v.id == id).firstOrNull;
    if (target != null) {
      setState(() {
        _selected = target;
        _crossFolderNav = true;
      });
      ref.read(readVacanciesProvider.notifier).markRead(id);
    }
  }

  bool _filterExpanded = false;
  Set<String> _statusFilter = {};
  bool _starredOnly = false;
  bool _blockedOnly = false;
  DateTime? _dateFrom;
  DateTime? _dateTo;

  String get _title => switch (widget.folder) {
        'inbox'     => 'Inbox',
        'analyzed'  => 'Analyzed',
        'processed' => 'Processed',
        'applied'   => 'Applied',
        'archive'   => 'Archive',
        _           => 'Vacancies',
      };

  int get _activeFilterCount =>
      _statusFilter.length +
      (_starredOnly ? 1 : 0) +
      (_blockedOnly ? 1 : 0) +
      (_dateFrom != null || _dateTo != null ? 1 : 0);

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

List<VacancyListItem> _filter(List<VacancyListItem> all) {
    final q = _searchQuery;
    return all.where((v) {
      if (q.isNotEmpty) {
        if (!v.role.toLowerCase().contains(q) &&
            !v.company.toLowerCase().contains(q) &&
            !v.id.toString().contains(q) &&
            !v.roleTags.any((t) => t.toLowerCase().contains(q))) {
          return false;
        }
      }
      if (_statusFilter.isNotEmpty && !_statusFilter.contains(v.status)) {
        return false;
      }
      if (_starredOnly && !v.starred) return false;
      // Stage 1 (title/domain, deterministic) only — not Stage 2 (LLM
      // content check). blockerStage is a real field (2026-07-24), not
      // string-matching blockerReasons for a "title:" prefix.
      if (_blockedOnly && v.blockerStage != 'title') return false;
      if (_dateFrom != null || _dateTo != null) {
        final raw = v.publishedAt;
        if (raw == null) return false;
        final d = DateTime.tryParse(raw);
        if (d == null) return false;
        final day = DateTime(d.year, d.month, d.day);
        if (_dateFrom != null && day.isBefore(_dateFrom!)) return false;
        if (_dateTo != null && day.isAfter(_dateTo!)) return false;
      }
      return true;
    }).toList();
  }

  Future<void> _pickDateFrom() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _dateFrom ?? DateTime.now(),
      firstDate: DateTime(2024),
      lastDate: _dateTo ?? DateTime.now(),
    );
    if (picked != null) setState(() => _dateFrom = picked);
  }

  Future<void> _pickDateTo() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _dateTo ?? DateTime.now(),
      firstDate: _dateFrom ?? DateTime(2024),
      lastDate: DateTime.now(),
    );
    if (picked != null) setState(() => _dateTo = picked);
  }

  void _clearAllFilters() {
    setState(() {
      _statusFilter = {};
      _starredOnly = false;
      _blockedOnly = false;
      _dateFrom = null;
      _dateTo = null;
      _searchController.clear();
      _searchQuery = '';
    });
  }

  @override
  Widget build(BuildContext context) {
    final vacancies = ref.watch(folderVacanciesProvider(widget.folder));
    final listState = ref.watch(vacancyListProvider).valueOrNull;
    final filtered = _filter(vacancies);
    final availableStatuses = vacancies.map((v) => v.status).toSet();

    // Sync _selected with polling updates (status changes, or any other field
    // edited server-side — salary, applied, starred, etc. all bump updated_at).
    ref.listen(folderVacanciesProvider(widget.folder), (_, updated) {
      if (_selected == null) return;
      try {
        final fresh = updated.firstWhere((v) => v.id == _selected!.id);
        if (fresh.updatedAt != _selected!.updatedAt) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) setState(() => _selected = fresh);
          });
        }
      } catch (_) {}
    });

    // Clear selection if selected vacancy no longer in this folder or filtered out
    // Skip cleanup during cross-folder navigation (badge → original in Archive, etc.)
    if (!_crossFolderNav && _selected != null && !filtered.any((v) => v.id == _selected!.id)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) setState(() => _selected = null);
      });
    }

    final cs = Theme.of(context).colorScheme;
    final hasFilters = _searchQuery.isNotEmpty || _activeFilterCount > 0;

    final panelState = ref.watch(listPanelProvider).valueOrNull ?? const ListPanelState();
    final panelCollapsed = panelState.collapsed;
    final panelWidth = _dragWidth ?? panelState.width;

    return Row(
      children: [
        // Master: vacancy list — resizable + collapsible (2026-07-25).
        // Collapsed entirely (not just width:0) when hidden — reopened via
        // the nav rail toggle (app_shell.dart), not from inside this panel.
        if (!panelCollapsed) ...[
        SizedBox(
          width: panelWidth,
          child: Container(
            color: cs.surface,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                InboxListHeader(
                  title: _title,
                  visibleCount: filtered.length,
                  totalCount: vacancies.length,
                  onRefresh: () =>
                      ref.read(vacancyListProvider.notifier).refresh(),
                  pollingState: listState,
                  filterCount: _activeFilterCount,
                  filterExpanded: _filterExpanded,
                  onToggleFilter: () =>
                      setState(() => _filterExpanded = !_filterExpanded),
                  titleBlockedCount: filtered.where((v) => v.blockerStage == 'title').length,
                  onSkipAllTitleBlocked: _batchRunning
                      ? null
                      : () => _skipAllByStage(filtered, 'title', 'title-blocked'),
                  contentBlockedCount: filtered.where((v) => v.blockerStage == 'content').length,
                  onSkipAllContentBlocked: _batchRunning
                      ? null
                      : () => _skipAllByStage(filtered, 'content', 'content-blocked'),
                  multiSelectActive: _multiSelectMode,
                  onToggleMultiSelect: _batchRunning ? null : _toggleMultiSelectMode,
                ),
                // Lives right below the header (same row as the toggle that
                // turns it on) — not at the bottom of the list — so entering
                // Mass Action shows its controls where the mode was switched
                // on, above search/filter (2026-07-26, explicit user ask).
                // _batchRunning alone (no multi-select) covers standalone
                // batches like "Skip all with blockers" — same progress UI,
                // no manual selection involved.
                if (_multiSelectMode || _batchRunning)
                  InboxBatchActionBar(
                    count: _selectedIds.length,
                    running: _batchRunning,
                    runningLabel: _batchLabel,
                    done: _batchDone,
                    total: _batchTotal,
                    onAnalyze: _selectedIds.isEmpty || _batchRunning ? null : _batchAnalyze,
                    onCheckBlockers: _selectedIds.isEmpty || _batchRunning ? null : _batchCheckBlockers,
                    onSkip: _selectedIds.isEmpty || _batchRunning ? null : _batchSkip,
                    onCancel: _batchRunning ? null : _exitMultiSelect,
                  ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(8, 0, 8, 8),
                  child: TextField(
                    controller: _searchController,
                    onChanged: (v) =>
                        setState(() => _searchQuery = v.trim().toLowerCase()),
                    style: Theme.of(context).textTheme.bodySmall,
                    decoration: InputDecoration(
                      hintText: 'Search role or company…',
                      hintStyle: Theme.of(context)
                          .textTheme
                          .bodySmall
                          ?.copyWith(color: cs.onSurfaceVariant),
                      prefixIcon: Icon(Icons.search,
                          size: 18, color: cs.onSurfaceVariant),
                      suffixIcon: _searchQuery.isNotEmpty
                          ? IconButton(
                              icon: Icon(Icons.close,
                                  size: 16, color: cs.onSurfaceVariant),
                              onPressed: () => setState(() {
                                _searchController.clear();
                                _searchQuery = '';
                              }),
                              splashRadius: 14,
                            )
                          : null,
                      isDense: true,
                      contentPadding: const EdgeInsets.symmetric(vertical: 8),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide:
                            BorderSide(color: cs.outlineVariant, width: 1),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide:
                            BorderSide(color: cs.outlineVariant, width: 1),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide: BorderSide(color: cs.primary, width: 1.5),
                      ),
                    ),
                  ),
                ),
                if (_filterExpanded && !_multiSelectMode)
                  InboxFilterPanel(
                    availableStatuses: availableStatuses,
                    selectedStatuses: _statusFilter,
                    onStatusToggle: (s) => setState(() {
                      if (_statusFilter.contains(s)) {
                        _statusFilter = Set.from(_statusFilter)..remove(s);
                      } else {
                        _statusFilter = Set.from(_statusFilter)..add(s);
                      }
                    }),
                    starredOnly: _starredOnly,
                    onToggleStarred: () =>
                        setState(() => _starredOnly = !_starredOnly),
                    blockedOnly: _blockedOnly,
                    onToggleBlocked: () =>
                        setState(() => _blockedOnly = !_blockedOnly),
                    dateFrom: _dateFrom,
                    dateTo: _dateTo,
                    onPickFrom: _pickDateFrom,
                    onPickTo: _pickDateTo,
                    onClearDates: () =>
                        setState(() { _dateFrom = null; _dateTo = null; }),
                    hasActiveFilters: _activeFilterCount > 0 || _searchQuery.isNotEmpty,
                    onClearAll: _clearAllFilters,
                  ),
                Divider(
                  height: 1,
                  thickness: 1,
                  color: cs.outlineVariant.withValues(alpha: 0.2),
                ),
                Expanded(
                  child: filtered.isEmpty
                      ? (hasFilters
                          ? _NoResults(
                              query: _searchController.text.isEmpty
                                  ? null
                                  : _searchController.text)
                          : _EmptyState(folder: widget.folder))
                      : InboxVacancyList(
                          vacancies: filtered,
                          todayDividerBasis: widget.folder == 'inbox'
                              ? TodayDividerBasis.publishedAt
                              : kUpdatedAtSortedFolders.contains(widget.folder)
                                  ? TodayDividerBasis.updatedAt
                                  : null,
                          selectedId: _selected?.id,
                          onSelect: (v) {
                            setState(() {
                              _selected = v;
                              _crossFolderNav = false;
                            });
                            ref.read(readVacanciesProvider.notifier).markRead(v.id);
                          },
                          onTapRelated: _selectByIdAny,
                          multiSelectMode: _multiSelectMode,
                          checkedIds: _selectedIds,
                          onCheckToggle: _toggleCheck,
                          onLongPress: _enterMultiSelect,
                        ),
                ),
              ],
            ),
          ),
        ),
        ],
        // Vertical divider — draggable to resize the panel above. Hit area
        // is wider (8px) than the visual line (1px) — a 1px drag target is
        // unhittable with a mouse.
        MouseRegion(
          cursor: panelCollapsed ? MouseCursor.defer : SystemMouseCursors.resizeColumn,
          child: GestureDetector(
            behavior: HitTestBehavior.translucent,
            onHorizontalDragUpdate: panelCollapsed
                ? null
                : (details) => setState(() {
                      _dragWidth = (panelWidth + details.delta.dx)
                          .clamp(kListPanelMinWidth, kListPanelMaxWidth);
                    }),
            onHorizontalDragEnd: panelCollapsed
                ? null
                : (_) {
                    final committed = _dragWidth;
                    if (committed != null) {
                      ref.read(listPanelProvider.notifier).setWidth(committed);
                    }
                    setState(() => _dragWidth = null);
                  },
            child: SizedBox(
              width: 8,
              child: Center(
                child: VerticalDivider(
                  width: 1,
                  thickness: 1,
                  color: cs.outlineVariant.withValues(alpha: 0.2),
                ),
              ),
            ),
          ),
        ),
        // Detail panel (bg-surface-container-lowest)
        Expanded(
          child: ColoredBox(
            color: cs.surfaceContainerLowest,
            child: _selected != null
                ? VacancyDetailScreen(
                    vacancyId: _selected!.id,
                    url: _selected!.url,
                    vacancy: _selected!,
                    onSkipped: _onSkipped,
                    onNavigateTo: _selectByIdAny,
                  )
                : const _NoSelectionPlaceholder(),
          ),
        ),
      ],
    );
  }
}

// ─── Skip-all-by-stage confirm dialog ──────────────────────────────────────────

/// Lists every vacancy a "Skip all {stage}-blocked" action would archive,
/// each with its own checkbox (default: all checked) — pops the still-checked
/// ids on confirm, or an empty list on Cancel/dismiss. 2026-07-28: replaces a
/// bare count-only confirm, which committed based on a number alone with no
/// way to rescue a single pre-filter false-positive short of aborting the
/// whole batch.
class SkipConfirmDialog extends StatefulWidget {
  final String stageLabel;
  final List<VacancyListItem> vacancies;

  const SkipConfirmDialog({
    super.key,
    required this.stageLabel,
    required this.vacancies,
  });

  @override
  State<SkipConfirmDialog> createState() => _SkipConfirmDialogState();
}

class _SkipConfirmDialogState extends State<SkipConfirmDialog> {
  late final Set<int> _checked;

  @override
  void initState() {
    super.initState();
    _checked = widget.vacancies.map((v) => v.id).toSet();
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return AlertDialog(
      title: Text('Skip ${widget.stageLabel}?'),
      content: SizedBox(
        width: 620,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Flagged by the ${widget.stageLabel} pre-filter check. '
              'Uncheck any you want to keep — this can\'t be undone in bulk.',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: cs.onSurfaceVariant),
            ),
            const SizedBox(height: 8),
            Flexible(
              child: ListView.builder(
                shrinkWrap: true,
                itemCount: widget.vacancies.length,
                itemBuilder: (ctx, i) {
                  final v = widget.vacancies[i];
                  // Reasons already read (title-stage: which allowlist term is
                  // missing; content-stage: "category: quoted JD line") — show
                  // right under the title so the user can decide skip/keep
                  // without leaving the dialog (2026-07-30, explicit user ask
                  // — content-stage reasons especially aren't obvious from
                  // the title alone, unlike title-stage).
                  return CheckboxListTile(
                    controlAffinity: ListTileControlAffinity.leading,
                    isThreeLine: v.blockerReasons.isNotEmpty,
                    value: _checked.contains(v.id),
                    title: Text(
                      '${v.role} — ${v.company}',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    subtitle: v.blockerReasons.isEmpty
                        ? null
                        : Text(
                            v.blockerReasons.join('\n'),
                            maxLines: 3,
                            overflow: TextOverflow.ellipsis,
                            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                  color: cs.onSurfaceVariant,
                                ),
                          ),
                    onChanged: (checked) => setState(() {
                      if (checked ?? false) {
                        _checked.add(v.id);
                      } else {
                        _checked.remove(v.id);
                      }
                    }),
                  );
                },
              ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(<int>[]),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _checked.isEmpty
              ? null
              : () => Navigator.of(context).pop(_checked.toList()),
          style: FilledButton.styleFrom(backgroundColor: cs.error),
          child: Text('Skip ${_checked.length}'),
        ),
      ],
    );
  }
}

// ─── Header ──────────────────────────────────────────────────────────────────

class InboxListHeader extends StatelessWidget {
  final String title;
  final int visibleCount;
  final int totalCount;
  final VoidCallback onRefresh;
  final PollingState? pollingState;
  final int filterCount;
  final bool filterExpanded;
  final VoidCallback onToggleFilter;
  // Split into two stage-scoped actions (2026-07-24) rather than one "skip
  // every blocker" button — Stage 1 (title, deterministic) is safe to
  // bulk-clear; Stage 2 (content, LLM-judged) is less certain and gets its
  // own separate action so it's never silently swept up by the same click.
  final int titleBlockedCount;
  final VoidCallback? onSkipAllTitleBlocked;
  final int contentBlockedCount;
  final VoidCallback? onSkipAllContentBlocked;
  // Explicit header entry point for multi-select (2026-07-25) — alongside
  // long-press, not replacing it (see _toggleMultiSelectMode's doc comment).
  final bool multiSelectActive;
  final VoidCallback? onToggleMultiSelect;

  const InboxListHeader({
    super.key,
    required this.title,
    required this.visibleCount,
    required this.totalCount,
    required this.onRefresh,
    this.pollingState,
    required this.filterCount,
    required this.filterExpanded,
    required this.onToggleFilter,
    this.titleBlockedCount = 0,
    this.onSkipAllTitleBlocked,
    this.contentBlockedCount = 0,
    this.onSkipAllContentBlocked,
    this.multiSelectActive = false,
    this.onToggleMultiSelect,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final polling = pollingState?.status == PollingStatus.polling;

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 8, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  title,
                  style: Theme.of(context).textTheme.headlineMedium,
                ),
              ),
              // Standalone bulk actions — not part of manual multi-select
              // (2026-07-24 design call): auto-select every visible
              // vacancy at the given pre-filter stage and skip it in one
              // click, no long-press/checkbox picking. Title (deterministic,
              // safe to bulk-clear) and content (LLM-judged, its own
              // confirm) stay separate actions — just consolidated into one
              // overflow menu instead of two more standalone icons.
              //
              // Found live 2026-07-24: this row already had filter+refresh
              // icons plus an Expanded title — adding two more unconditional
              // IconButtons pushed the total past what a narrow detail-pane
              // width leaves for the header, overflowing it. Same root
              // mistake as the badge-cluster bug earlier the same day
              // (an unbounded-growing icon/badge count sharing a plain Row
              // with no wrap/overflow protection) — just a different Row,
              // caught later because the debug overflow banner rendered
              // off in the empty detail pane, easy to miss at a glance.
              if (titleBlockedCount > 0 || contentBlockedCount > 0)
                PopupMenuButton<VoidCallback?>(
                  tooltip: 'Skip all flagged',
                  // Compact tap target — 3 icon-ish controls (this menu,
                  // filter, refresh) share this row with the title; at
                  // Material's default 48px-minimum touch target each,
                  // three of them alone (144px) can exceed a narrow
                  // detail-pane's available width before the title even
                  // gets a look-in. Found via this fix's own regression
                  // test, reproducing the real 160px-wide overflow.
                  padding: EdgeInsets.zero,
                  // `child:` instead of `icon:` — PopupMenuButton's `icon`
                  // shorthand wraps content in its own IconButton, which
                  // keeps Material 3's 48px minimum regardless of
                  // `padding:` (same gotcha as the plain IconButtons below,
                  // confirmed by measuring). `child:` skips that wrapper
                  // entirely, sizing to content.
                  child: Padding(
                    padding: const EdgeInsets.all(6),
                    child: Badge(
                      label: Text('${titleBlockedCount + contentBlockedCount}'),
                      backgroundColor: cs.error,
                      child: Icon(Icons.playlist_remove, size: 20, color: cs.error),
                    ),
                  ),
                  onSelected: (action) => action?.call(),
                  itemBuilder: (context) => [
                    // Text wrapped in Expanded+ellipsis on purpose — a plain
                    // Text sibling in a Row overflows PopupMenuItem's own
                    // constrained width on a narrow window (found writing
                    // this fix's own test). Same lesson as the badge-cluster
                    // and header-icon overflows above: text sharing a Row
                    // with anything else needs explicit overflow handling,
                    // never assume it'll just fit.
                    if (titleBlockedCount > 0)
                      PopupMenuItem<VoidCallback?>(
                        value: onSkipAllTitleBlocked,
                        child: Row(
                          children: [
                            const Icon(Icons.title, size: 16),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                'Skip $titleBlockedCount title-blocked',
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                      ),
                    if (contentBlockedCount > 0)
                      PopupMenuItem<VoidCallback?>(
                        value: onSkipAllContentBlocked,
                        child: Row(
                          children: [
                            const Icon(Icons.psychology_outlined, size: 16),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                'Skip $contentBlockedCount content-blocked',
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
              IconButton(
                icon: Icon(
                  multiSelectActive ? Icons.checklist_rtl : Icons.checklist,
                  size: 20,
                  color: multiSelectActive ? cs.primary : cs.onSurfaceVariant,
                ),
                onPressed: onToggleMultiSelect,
                tooltip: multiSelectActive ? 'Exit selection' : 'Select multiple',
                style: IconButton.styleFrom(
                  minimumSize: const Size(32, 32),
                  padding: EdgeInsets.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
              ),
              IconButton(
                icon: Badge(
                  isLabelVisible: filterCount > 0,
                  label: Text('$filterCount'),
                  child: Icon(
                    filterExpanded
                        ? Icons.filter_list_off
                        : Icons.filter_list,
                    size: 20,
                    color: filterCount > 0 ? cs.primary : cs.onSurfaceVariant,
                  ),
                ),
                onPressed: onToggleFilter,
                tooltip: 'Filters',
                // `constraints:` alone doesn't shrink Material 3's IconButton
                // below its 48x48 default (found measuring this fix's own
                // test) — the theme's minimum tap target still wins unless
                // tapTargetSize is explicitly shrinkWrap via style.
                style: IconButton.styleFrom(
                  minimumSize: const Size(32, 32),
                  padding: EdgeInsets.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
              ),
              IconButton(
                icon: Icon(
                  polling ? Icons.sync : Icons.refresh,
                  size: 20,
                  color: polling ? cs.primary : cs.onSurfaceVariant,
                ),
                onPressed: polling ? null : onRefresh,
                tooltip: 'Refresh',
                style: IconButton.styleFrom(
                  minimumSize: const Size(32, 32),
                  padding: EdgeInsets.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: polling ? cs.primary : const Color(0xFF4CAF50),
                ),
              ),
              const SizedBox(width: 6),
              // Expanded+ellipsis — same lesson as everywhere else in this
              // header today: a plain Text sharing a Row with anything else
              // needs explicit overflow handling, found via this fix's own
              // regression test rather than assumed safe.
              Expanded(
                child: Text(
                  visibleCount == totalCount
                      ? '$totalCount ${totalCount == 1 ? 'vacancy' : 'vacancies'}'
                      : '$visibleCount / $totalCount vacancies',
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.labelMedium?.copyWith(
                        color: cs.secondary,
                      ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

// ─── Filter panel ─────────────────────────────────────────────────────────────

class InboxFilterPanel extends StatelessWidget {
  final Set<String> availableStatuses;
  final Set<String> selectedStatuses;
  final ValueChanged<String> onStatusToggle;
  final bool starredOnly;
  final VoidCallback onToggleStarred;
  final bool blockedOnly;
  final VoidCallback onToggleBlocked;
  final DateTime? dateFrom;
  final DateTime? dateTo;
  final VoidCallback onPickFrom;
  final VoidCallback onPickTo;
  final VoidCallback onClearDates;
  final bool hasActiveFilters;
  final VoidCallback onClearAll;

  const InboxFilterPanel({
    super.key,
    required this.availableStatuses,
    required this.selectedStatuses,
    required this.onStatusToggle,
    required this.starredOnly,
    required this.onToggleStarred,
    required this.blockedOnly,
    required this.onToggleBlocked,
    this.dateFrom,
    this.dateTo,
    required this.onPickFrom,
    required this.onPickTo,
    required this.onClearDates,
    required this.hasActiveFilters,
    required this.onClearAll,
  });

  static const _statusLabels = <String, String>{
    'fetched': 'New',
    'analyzing': 'In Queue',
    'analysis_failed': 'Failed',
    'analyzed': 'Analyzed',
    'cv_generated': 'CV Ready',
    'cover_generated': 'Cover Ready',
  };

  static String _fmtDate(DateTime d) {
    const months = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    ];
    return '${months[d.month - 1]} ${d.day}';
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final labelSmall = Theme.of(context).textTheme.labelSmall;

    final statuses = _statusLabels.keys
        .where((s) => availableStatuses.contains(s))
        .toList();

    return Container(
      margin: const EdgeInsets.fromLTRB(8, 0, 8, 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: cs.surfaceContainerLow,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: cs.outlineVariant, width: 0.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (statuses.isNotEmpty) ...[
            Text('Status',
                style: labelSmall?.copyWith(color: cs.onSurfaceVariant)),
            const SizedBox(height: 6),
            Wrap(
              spacing: 6,
              runSpacing: 4,
              children: statuses.map((s) {
                final selected = selectedStatuses.contains(s);
                return FilterChip(
                  label: Text(
                    _statusLabels[s]!,
                    style: Theme.of(context).textTheme.labelSmall,
                  ),
                  selected: selected,
                  onSelected: (_) => onStatusToggle(s),
                  materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 4, vertical: 0),
                  visualDensity: VisualDensity.compact,
                );
              }).toList(),
            ),
            const SizedBox(height: 10),
          ],
          Wrap(
            spacing: 6,
            runSpacing: 4,
            children: [
              FilterChip(
                avatar: Icon(
                  starredOnly ? Icons.star : Icons.star_border,
                  size: 14,
                  color: starredOnly ? cs.primary : cs.onSurfaceVariant,
                ),
                label: Text('Starred',
                    style: Theme.of(context).textTheme.labelSmall),
                selected: starredOnly,
                onSelected: (_) => onToggleStarred(),
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 0),
                visualDensity: VisualDensity.compact,
              ),
              // Stage 1 (title/domain, deterministic) only — not Stage 2
              // (LLM content check). "Title blocked" names the specific
              // check, not a generic "has any blocker" (2026-07-24).
              FilterChip(
                avatar: Icon(
                  Icons.block,
                  size: 14,
                  color: blockedOnly ? cs.error : cs.onSurfaceVariant,
                ),
                label: Text('Title blocked',
                    style: Theme.of(context).textTheme.labelSmall),
                selected: blockedOnly,
                onSelected: (_) => onToggleBlocked(),
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 0),
                visualDensity: VisualDensity.compact,
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text('Published',
              style: labelSmall?.copyWith(color: cs.onSurfaceVariant)),
          const SizedBox(height: 6),
          Row(
            children: [
              Expanded(
                child: _DateButton(
                  label: dateFrom != null ? _fmtDate(dateFrom!) : 'From',
                  hasValue: dateFrom != null,
                  onTap: onPickFrom,
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 6),
                child: Text('—',
                    style: labelSmall?.copyWith(color: cs.onSurfaceVariant)),
              ),
              Expanded(
                child: _DateButton(
                  label: dateTo != null ? _fmtDate(dateTo!) : 'To',
                  hasValue: dateTo != null,
                  onTap: onPickTo,
                ),
              ),
              if (dateFrom != null || dateTo != null) ...[
                const SizedBox(width: 4),
                IconButton(
                  icon: Icon(Icons.close, size: 14, color: cs.onSurfaceVariant),
                  onPressed: onClearDates,
                  splashRadius: 12,
                  tooltip: 'Clear dates',
                ),
              ],
            ],
          ),
          if (hasActiveFilters) ...[
            const SizedBox(height: 10),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: onClearAll,
                icon: Icon(Icons.filter_list_off, size: 14, color: cs.error),
                label: Text(
                  'Clear all filters',
                  style: labelSmall?.copyWith(color: cs.error),
                ),
                style: TextButton.styleFrom(
                  minimumSize: Size.zero,
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _DateButton extends StatelessWidget {
  final String label;
  final bool hasValue;
  final VoidCallback onTap;

  const _DateButton({
    required this.label,
    required this.hasValue,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return OutlinedButton.icon(
      onPressed: onTap,
      icon: const Icon(Icons.calendar_today, size: 12),
      label: Text(label, style: Theme.of(context).textTheme.labelSmall),
      style: OutlinedButton.styleFrom(
        foregroundColor: hasValue ? cs.primary : cs.onSurfaceVariant,
        side: BorderSide(
          color: hasValue ? cs.primary : cs.outlineVariant,
          width: hasValue ? 1.5 : 1,
        ),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        minimumSize: const Size(0, 28),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
    );
  }
}

// ─── List ────────────────────────────────────────────────────────────────────

/// Which date field the Today/Earlier divider (below) checks — must match
/// whatever field the caller's list is actually sorted by.
enum TodayDividerBasis { publishedAt, updatedAt }

class InboxVacancyList extends StatelessWidget {
  final List<VacancyListItem> vacancies;
  final int? selectedId;
  final ValueChanged<VacancyListItem> onSelect;
  final void Function(int vacancyId)? onTapRelated;
  final bool multiSelectMode;
  final Set<int> checkedIds;
  final void Function(int id)? onCheckToggle;
  final void Function(int id)? onLongPress;
  // The Today/Earlier boundary must be scanned against whichever field the
  // list is actually sorted by, or it lands in the wrong place (2026-07-26
  // — Analyzed/Processed sort by updated_at, not published_at). `null`
  // disables the divider entirely (folders with no "today" concept worth
  // showing, e.g. Applied/Archive keep the plain unsorted-by-date list).
  final TodayDividerBasis? todayDividerBasis;

  const InboxVacancyList({
    super.key,
    required this.vacancies,
    required this.selectedId,
    required this.onSelect,
    this.onTapRelated,
    this.multiSelectMode = false,
    this.checkedIds = const {},
    this.onCheckToggle,
    this.onLongPress,
    this.todayDividerBasis = TodayDividerBasis.publishedAt,
  });

  /// Index of the first vacancy whose divider-basis date falls before the
  /// start of today (local time) — the list must already be sorted
  /// newest-first BY THAT SAME FIELD, so this is where the "Today" section
  /// ends and "Earlier" begins. Returns null when there's nothing to
  /// separate (every dated vacancy is from today, or none are dated) — in
  /// that case no section headers are shown at all. Returns 0 when NOTHING
  /// is from today (every vacancy is earlier) — the caller shows an
  /// explicit "Nothing for today" note instead of just starting the list
  /// with a bare "Earlier" header, which read as unexplained (2026-07-25,
  /// explicit user ask — the original bare-"Earlier" version looked
  /// "visually strange" with no "Today" to contrast against).
  /// Purely visual — doesn't change order, filtering, or grouping.
  int? _todayDividerIndex() {
    final basis = todayDividerBasis;
    if (basis == null) return null;
    final now = DateTime.now();
    final startOfToday = DateTime(now.year, now.month, now.day);
    for (var i = 0; i < vacancies.length; i++) {
      final raw = basis == TodayDividerBasis.updatedAt
          ? vacancies[i].updatedAt
          : vacancies[i].publishedAt;
      if (raw == null) continue;
      final local = parseBackendUtc(raw).toLocal();
      if (local.isBefore(startOfToday)) return i;
    }
    return null;
  }

  Widget _buildCard(VacancyListItem v) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: ProcessingWrapper(
        key: ValueKey('pw_${v.id}'),
        status: v.status,
        child: VacancyCard(
          vacancy: v,
          selected: v.id == selectedId,
          onTap: () => onSelect(v),
          onTapRelated: onTapRelated,
          multiSelectMode: multiSelectMode,
          checked: checkedIds.contains(v.id),
          onCheckToggle: onCheckToggle == null ? null : () => onCheckToggle!(v.id),
          onLongPress: onLongPress == null ? null : () => onLongPress!(v.id),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final dividerIndex = _todayDividerIndex();

    final items = <Widget>[];
    if (dividerIndex == 0) {
      items.add(const _SectionHeader(label: 'Today'));
      items.add(const _NothingForTodayNote());
      items.add(const _SectionHeader(label: 'Earlier'));
    } else if (dividerIndex != null) {
      items.add(const _SectionHeader(label: 'Today'));
    }
    for (var i = 0; i < vacancies.length; i++) {
      if (dividerIndex != null && dividerIndex > 0 && i == dividerIndex) {
        items.add(const _SectionHeader(label: 'Earlier'));
      }
      items.add(_buildCard(vacancies[i]));
    }

    return ListView.builder(
      padding: const EdgeInsets.all(8),
      itemCount: items.length,
      itemBuilder: (ctx, i) => items[i],
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String label;

  const _SectionHeader({required this.label});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Expanded(child: Divider(color: cs.outlineVariant, thickness: 1)),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Text(
              label,
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: cs.onSurfaceVariant,
                    letterSpacing: 0.5,
                  ),
            ),
          ),
          Expanded(child: Divider(color: cs.outlineVariant, thickness: 1)),
        ],
      ),
    );
  }
}

class _NothingForTodayNote extends StatelessWidget {
  const _NothingForTodayNote();

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 4),
      child: Center(
        child: Text(
          'Nothing for today',
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: cs.onSurfaceVariant,
                fontStyle: FontStyle.italic,
              ),
        ),
      ),
    );
  }
}

// ─── Batch action bar (mass actions: Analyze / Check blockers / Skip) ─────────

class InboxBatchActionBar extends StatelessWidget {
  final int count;
  final bool running;
  final String runningLabel;
  final int done;
  final int total;
  final VoidCallback? onAnalyze;
  final VoidCallback? onCheckBlockers;
  final VoidCallback? onSkip;
  final VoidCallback? onCancel;

  const InboxBatchActionBar({
    super.key,
    required this.count,
    required this.running,
    required this.runningLabel,
    required this.done,
    required this.total,
    this.onAnalyze,
    this.onCheckBlockers,
    this.onSkip,
    this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
      decoration: BoxDecoration(
        color: cs.surfaceContainerHigh,
        border: Border(top: BorderSide(color: cs.outlineVariant.withValues(alpha: 0.4))),
      ),
      child: running
          ? Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('$runningLabel: $done/$total',
                    style: Theme.of(context).textTheme.labelMedium),
                const SizedBox(height: 6),
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: total == 0 ? null : done / total,
                    minHeight: 4,
                  ),
                ),
              ],
            )
          // 2 primary actions (Skip/Analyze — the daily-driver pair) + an
          // overflow menu for less-frequent ones (Check blockers, and room
          // for future additions) — a flat button-per-action row doesn't
          // scale on a 360px inbox panel (design call, 2026-07-24: same
          // narrow-panel constraint that caused the badge-row overflow bug).
          : Row(
              children: [
                Text('$count selected',
                    style: Theme.of(context).textTheme.labelMedium),
                const Spacer(),
                IconButton(
                  tooltip: 'Cancel',
                  icon: const Icon(Icons.close, size: 18),
                  onPressed: onCancel,
                  visualDensity: VisualDensity.compact,
                ),
                PopupMenuButton<void>(
                  tooltip: 'More actions',
                  icon: const Icon(Icons.more_horiz, size: 18),
                  itemBuilder: (context) => [
                    PopupMenuItem<void>(
                      onTap: onCheckBlockers,
                      child: const Row(
                        children: [
                          Icon(Icons.shield_outlined, size: 16),
                          SizedBox(width: 8),
                          Text('Check blockers'),
                        ],
                      ),
                    ),
                  ],
                ),
                TextButton.icon(
                  onPressed: onSkip,
                  icon: Icon(Icons.block, size: 16, color: cs.error),
                  label: Text('Skip', style: TextStyle(color: cs.error)),
                ),
                FilledButton.icon(
                  onPressed: onAnalyze,
                  icon: const Icon(Icons.play_arrow, size: 16),
                  label: const Text('Analyze'),
                ),
              ],
            ),
    );
  }
}

// ─── Empty / No-results states ────────────────────────────────────────────────

class _NoResults extends StatelessWidget {
  final String? query;

  const _NoResults({this.query});

  @override
  Widget build(BuildContext context) {
    final msg = (query != null && query!.isNotEmpty)
        ? 'No matches for "$query"'
        : 'No vacancies match the active filters';
    return Center(
      child: Text(
        msg,
        textAlign: TextAlign.center,
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final String folder;

  const _EmptyState({required this.folder});

  @override
  Widget build(BuildContext context) {
    final msg = switch (folder) {
      'inbox'     => 'No new vacancies.\nThe RSS pipeline will add them automatically.',
      'analyzed'  => 'No analyzed vacancies yet.',
      'processed' => 'No CVs or covers generated yet.',
      'applied'   => 'No applications sent yet.',
      'archive'   => 'Archive is empty.',
      _           => 'No vacancies.',
    };
    return Center(
      child: Text(
        msg,
        textAlign: TextAlign.center,
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
      ),
    );
  }
}

class _NoSelectionPlaceholder extends StatelessWidget {
  const _NoSelectionPlaceholder();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.work_outline,
              size: 48,
              color: Theme.of(context).colorScheme.onSurfaceVariant),
          const SizedBox(height: 12),
          Text(
            'Select a vacancy',
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
        ],
      ),
    );
  }
}
