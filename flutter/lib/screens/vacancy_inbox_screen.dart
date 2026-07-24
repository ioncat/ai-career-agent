import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/vacancy.dart';
import '../providers/read_vacancies_provider.dart';
import '../providers/settings_provider.dart';
import '../providers/vacancy_list_provider.dart';
import '../repositories/vacancy_repository.dart';
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
  /// Auto-selects everything currently visible with a pre-filter blocker
  /// flag and skips it. Reuses _runBatch's sequential-execution + progress
  /// UI/snackbar, just with an explicit id list instead of _selectedIds.
  /// Confirms first (2026-07-24, explicit user ask) — a single accidental
  /// click on this button archives every flagged vacancy at once, unlike
  /// the manual multi-select actions where the selection itself is the
  /// deliberate step.
  Future<void> _skipAllWithBlockers(List<VacancyListItem> visible) async {
    final ids = visible.where((v) => v.blockerFlag).map((v) => v.id).toList();
    if (ids.isEmpty) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Skip all with blockers?'),
        content: Text(
          'This will archive ${ids.length} vacancy${ids.length == 1 ? '' : 'ies'} '
          'flagged by the pre-filter. This can\'t be undone in bulk.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: FilledButton.styleFrom(backgroundColor: Theme.of(context).colorScheme.error),
            child: Text('Skip ${ids.length}'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    await _runBatch('Skip', (id) => _repo.decline(id), ids: ids);
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

    return Row(
      children: [
        // Master: vacancy list (360px, bg-surface)
        SizedBox(
          width: 360,
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
                  blockedCount: filtered.where((v) => v.blockerFlag).length,
                  onSkipAllBlocked: _batchRunning ? null : () => _skipAllWithBlockers(filtered),
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
                if (_filterExpanded)
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
                      : _VacancyList(
                          vacancies: filtered,
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
              ],
            ),
          ),
        ),
        // Vertical divider
        VerticalDivider(
          width: 1,
          thickness: 1,
          color: cs.outlineVariant.withValues(alpha: 0.2),
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
  final int blockedCount;
  final VoidCallback? onSkipAllBlocked;

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
    this.blockedCount = 0,
    this.onSkipAllBlocked,
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
              // Standalone bulk action — not part of manual multi-select
              // (2026-07-24 design call): auto-selects every visible
              // pre-filter-flagged vacancy and skips it in one click, no
              // long-press/checkbox picking needed.
              if (blockedCount > 0)
                IconButton(
                  icon: Badge(
                    label: Text('$blockedCount'),
                    backgroundColor: cs.error,
                    child: Icon(Icons.playlist_remove, size: 20, color: cs.error),
                  ),
                  onPressed: onSkipAllBlocked,
                  tooltip: 'Skip all $blockedCount with blockers',
                  splashRadius: 18,
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
                splashRadius: 18,
              ),
              IconButton(
                icon: Icon(
                  polling ? Icons.sync : Icons.refresh,
                  size: 20,
                  color: polling ? cs.primary : cs.onSurfaceVariant,
                ),
                onPressed: polling ? null : onRefresh,
                tooltip: 'Refresh',
                splashRadius: 18,
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
              Text(
                visibleCount == totalCount
                    ? '$totalCount ${totalCount == 1 ? 'vacancy' : 'vacancies'}'
                    : '$visibleCount / $totalCount vacancies',
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                      color: cs.secondary,
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

class _VacancyList extends StatelessWidget {
  final List<VacancyListItem> vacancies;
  final int? selectedId;
  final ValueChanged<VacancyListItem> onSelect;
  final void Function(int vacancyId)? onTapRelated;
  final bool multiSelectMode;
  final Set<int> checkedIds;
  final void Function(int id)? onCheckToggle;
  final void Function(int id)? onLongPress;

  const _VacancyList({
    required this.vacancies,
    required this.selectedId,
    required this.onSelect,
    this.onTapRelated,
    this.multiSelectMode = false,
    this.checkedIds = const {},
    this.onCheckToggle,
    this.onLongPress,
  });

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      padding: const EdgeInsets.all(8),
      itemCount: vacancies.length,
      itemBuilder: (ctx, i) {
        final v = vacancies[i];
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
      },
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
