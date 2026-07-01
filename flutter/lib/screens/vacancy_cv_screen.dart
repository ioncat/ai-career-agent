import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/vacancy_cv_provider.dart';

class VacancyCvDialog extends ConsumerStatefulWidget {
  final int vacancyId;
  final String role;

  const VacancyCvDialog({
    super.key,
    required this.vacancyId,
    required this.role,
  });

  @override
  ConsumerState<VacancyCvDialog> createState() => _VacancyCvDialogState();
}

class _VacancyCvDialogState extends ConsumerState<VacancyCvDialog>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final cvAsync = ref.watch(vacancyCvProvider(widget.vacancyId));

    return Dialog(
      backgroundColor: cs.surface,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: SizedBox(
        width: 760,
        height: MediaQuery.of(context).size.height * 0.85,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Header row
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 18, 12, 0),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      widget.role,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            color: cs.onSurface,
                            fontWeight: FontWeight.w600,
                          ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, size: 20),
                    onPressed: () => Navigator.of(context).pop(),
                    color: cs.onSurfaceVariant,
                    tooltip: 'Close',
                  ),
                ],
              ),
            ),
            // Tabs
            TabBar(
              controller: _tabController,
              labelColor: cs.primary,
              unselectedLabelColor: cs.onSurfaceVariant,
              indicatorColor: cs.primary,
              labelStyle: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
              tabs: const [
                Tab(text: 'CV'),
                Tab(text: 'Cover'),
              ],
            ),
            Divider(
              height: 1,
              color: cs.outlineVariant.withValues(alpha: 0.3),
            ),
            // Content
            Expanded(
              child: cvAsync.when(
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (e, _) => Center(
                  child: Text(
                    'Ошибка загрузки: $e',
                    style: TextStyle(color: cs.error),
                  ),
                ),
                data: (cv) => TabBarView(
                  controller: _tabController,
                  children: [
                    cv.hasCv
                        ? Markdown(
                            data: cv.cvMd!,
                            selectable: true,
                            padding: const EdgeInsets.fromLTRB(24, 20, 24, 24),
                          )
                        : _EmptyState(
                            icon: Icons.description_outlined,
                            message: 'CV ещё не сгенерирован',
                            cs: cs,
                          ),
                    cv.hasCover
                        ? Markdown(
                            data: cv.coverMd!,
                            selectable: true,
                            padding: const EdgeInsets.fromLTRB(24, 20, 24, 24),
                          )
                        : _EmptyState(
                            icon: Icons.mail_outline,
                            message: 'Cover letter ещё не сгенерирован',
                            cs: cs,
                          ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final IconData icon;
  final String message;
  final ColorScheme cs;

  const _EmptyState({
    required this.icon,
    required this.message,
    required this.cs,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 48, color: cs.onSurfaceVariant.withValues(alpha: 0.4)),
          const SizedBox(height: 12),
          Text(
            message,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: cs.onSurfaceVariant,
                ),
          ),
        ],
      ),
    );
  }
}
