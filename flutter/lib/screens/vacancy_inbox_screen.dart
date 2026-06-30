import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/vacancy.dart';
import '../providers/vacancy_list_provider.dart';
import '../widgets/vacancy_card.dart';
import 'vacancy_detail_screen.dart';

class VacancyInboxScreen extends ConsumerStatefulWidget {
  final String folder;

  const VacancyInboxScreen({super.key, required this.folder});

  @override
  ConsumerState<VacancyInboxScreen> createState() => _VacancyInboxScreenState();
}

class _VacancyInboxScreenState extends ConsumerState<VacancyInboxScreen> {
  VacancyListItem? _selected;

  String get _title => switch (widget.folder) {
        'inbox' => 'Inbox',
        'in_progress' => 'In Progress',
        'applied' => 'Applied',
        'archive' => 'Archive',
        _ => 'Vacancies',
      };

  @override
  Widget build(BuildContext context) {
    final vacancies = ref.watch(folderVacanciesProvider(widget.folder));
    final listState = ref.watch(vacancyListProvider).valueOrNull;

    // Clear selection if selected vacancy no longer in this folder
    if (_selected != null && !vacancies.any((v) => v.id == _selected!.id)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) setState(() => _selected = null);
      });
    }

    final cs = Theme.of(context).colorScheme;

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
                  count: vacancies.length,
                  onRefresh: () =>
                      ref.read(vacancyListProvider.notifier).refresh(),
                  pollingState: listState,
                ),
                Divider(
                  height: 1,
                  thickness: 1,
                  color: cs.outlineVariant.withValues(alpha: 0.2),
                ),
                Expanded(
                  child: vacancies.isEmpty
                      ? _EmptyState(folder: widget.folder)
                      : _VacancyList(
                          vacancies: vacancies,
                          selectedId: _selected?.id,
                          onSelect: (v) => setState(() => _selected = v),
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
                  )
                : const _NoSelectionPlaceholder(),
          ),
        ),
      ],
    );
  }
}

class _ListHeader extends StatelessWidget {
  final String title;
  final int count;
  final VoidCallback onRefresh;
  final PollingState? pollingState;

  const _ListHeader({
    required this.title,
    required this.count,
    required this.onRefresh,
    this.pollingState,
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
                icon: Icon(
                  Icons.tune,
                  size: 20,
                  color: cs.onSurfaceVariant,
                ),
                onPressed: polling ? null : onRefresh,
                tooltip: 'Обновить',
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
                '$count вакансий проанализировано',
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
        return VacancyCard(
          key: ValueKey(v.id),
          vacancy: v,
          selected: v.id == selectedId,
          onTap: () => onSelect(v),
        );
      },
    );
  }
}

class _EmptyState extends StatelessWidget {
  final String folder;

  const _EmptyState({required this.folder});

  @override
  Widget build(BuildContext context) {
    final msg = switch (folder) {
      'inbox' =>
        'Нет новых вакансий.\nRSS-пайплайн автоматически добавит их когда появятся.',
      'in_progress' => 'Нет вакансий в работе.',
      'applied' => 'Вы ещё не отправили CV.',
      'archive' => 'Архив пуст.',
      _ => 'Нет вакансий.',
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
            'Выбери вакансию',
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
        ],
      ),
    );
  }
}
