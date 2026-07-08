import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/vacancy.dart';
import '../providers/read_vacancies_provider.dart';
import '../providers/vacancy_list_provider.dart';
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
  final _searchController = TextEditingController();
  String _searchQuery = '';

  void _onSkipped() {
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

  bool _filterExpanded = false;
  Set<String> _statusFilter = {};
  DateTime? _dateFrom;
  DateTime? _dateTo;

  String get _title => switch (widget.folder) {
        'inbox'   => 'Inbox',
        'applied' => 'Applied',
        'archive' => 'Archive',
        _         => 'Vacancies',
      };

  int get _activeFilterCount =>
      _statusFilter.length + (_dateFrom != null || _dateTo != null ? 1 : 0);

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

    // Sync _selected with polling updates (status changes: fetched→analyzing→analyzed)
    ref.listen(folderVacanciesProvider(widget.folder), (_, updated) {
      if (_selected == null) return;
      try {
        final fresh = updated.firstWhere((v) => v.id == _selected!.id);
        if (fresh.status != _selected!.status) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) setState(() => _selected = fresh);
          });
        }
      } catch (_) {}
    });

    // Clear selection if selected vacancy no longer in this folder or filtered out
    if (_selected != null && !filtered.any((v) => v.id == _selected!.id)) {
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
                _ListHeader(
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
                  _FilterPanel(
                    availableStatuses: availableStatuses,
                    selectedStatuses: _statusFilter,
                    onStatusToggle: (s) => setState(() {
                      if (_statusFilter.contains(s)) {
                        _statusFilter = Set.from(_statusFilter)..remove(s);
                      } else {
                        _statusFilter = Set.from(_statusFilter)..add(s);
                      }
                    }),
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
                            setState(() => _selected = v);
                            ref.read(readVacanciesProvider.notifier).markRead(v.id);
                          },
                        ),
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
                  )
                : const _NoSelectionPlaceholder(),
          ),
        ),
      ],
    );
  }
}

// ─── Header ──────────────────────────────────────────────────────────────────

class _ListHeader extends StatelessWidget {
  final String title;
  final int visibleCount;
  final int totalCount;
  final VoidCallback onRefresh;
  final PollingState? pollingState;
  final int filterCount;
  final bool filterExpanded;
  final VoidCallback onToggleFilter;

  const _ListHeader({
    required this.title,
    required this.visibleCount,
    required this.totalCount,
    required this.onRefresh,
    this.pollingState,
    required this.filterCount,
    required this.filterExpanded,
    required this.onToggleFilter,
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

class _FilterPanel extends StatelessWidget {
  final Set<String> availableStatuses;
  final Set<String> selectedStatuses;
  final ValueChanged<String> onStatusToggle;
  final DateTime? dateFrom;
  final DateTime? dateTo;
  final VoidCallback onPickFrom;
  final VoidCallback onPickTo;
  final VoidCallback onClearDates;
  final bool hasActiveFilters;
  final VoidCallback onClearAll;

  const _FilterPanel({
    required this.availableStatuses,
    required this.selectedStatuses,
    required this.onStatusToggle,
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

  const _VacancyList({
    required this.vacancies,
    required this.selectedId,
    required this.onSelect,
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
            ),
          ),
        );
      },
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
      'inbox'   => 'No new vacancies.\nThe RSS pipeline will add them automatically.',
      'applied' => 'No applications sent yet.',
      'archive' => 'Archive is empty.',
      _         => 'No vacancies.',
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
