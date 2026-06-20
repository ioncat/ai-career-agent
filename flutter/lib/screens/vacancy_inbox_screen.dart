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
  int? _selectedId;

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

    return Row(
      children: [
        // Master: vacancy list
        SizedBox(
          width: 360,
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
              const Divider(height: 1),
              Expanded(
                child: vacancies.isEmpty
                    ? _EmptyState(folder: widget.folder)
                    : _AnimatedList(
                        vacancies: vacancies,
                        selectedId: _selectedId,
                        onSelect: (id) =>
                            setState(() => _selectedId = id),
                      ),
              ),
            ],
          ),
        ),
        // Vertical divider
        const VerticalDivider(width: 1, thickness: 1),
        // Detail panel
        Expanded(
          child: _selectedId != null
              ? VacancyDetailScreen(vacancyId: _selectedId!)
              : const _NoSelectionPlaceholder(),
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
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '$title  $count',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ],
            ),
          ),
          IconButton(
            icon: const Icon(Icons.refresh, size: 18),
            onPressed: pollingState?.status == PollingStatus.polling
                ? null
                : onRefresh,
            tooltip: 'Обновить',
          ),
        ],
      ),
    );
  }
}

class _AnimatedList extends StatelessWidget {
  final List<VacancyListItem> vacancies;
  final int? selectedId;
  final ValueChanged<int> onSelect;

  const _AnimatedList({
    required this.vacancies,
    required this.selectedId,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      itemCount: vacancies.length,
      itemBuilder: (ctx, i) {
        final v = vacancies[i];
        return VacancyCard(
          key: ValueKey(v.id),
          vacancy: v,
          selected: v.id == selectedId,
          onTap: () => onSelect(v.id),
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
      'inbox' => 'Нет новых вакансий.\nRSS-пайплайн автоматически добавит их когда появятся.',
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
