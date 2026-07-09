import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/vacancy.dart';
import '../providers/read_vacancies_provider.dart';
import '../providers/settings_provider.dart';
import '../providers/vacancy_list_provider.dart';
import '../repositories/vacancy_repository.dart';
import 'fit_score_chip.dart';
import 'vac_score_badge.dart';
import 'source_badge.dart';

class VacancyCard extends ConsumerStatefulWidget {
  final VacancyListItem vacancy;
  final bool selected;
  final VoidCallback onTap;

  const VacancyCard({
    super.key,
    required this.vacancy,
    required this.onTap,
    this.selected = false,
  });

  @override
  ConsumerState<VacancyCard> createState() => _VacancyCardState();
}

class _VacancyCardState extends ConsumerState<VacancyCard> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final v = widget.vacancy;
    final readIds = ref.watch(readVacanciesProvider).valueOrNull ?? {};
    final isUnread = v.status == 'fetched' && !readIds.contains(v.id);

    final bgColor = widget.selected
        ? cs.surface
        : _hovered
            ? cs.surfaceContainerLow
            : cs.surface;

    final borderRadius = BorderRadius.circular(12);

    return MouseRegion(
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: GestureDetector(
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          margin: EdgeInsets.zero,
          decoration: BoxDecoration(
            color: bgColor,
            borderRadius: borderRadius,
            border: widget.selected
                ? Border.all(color: cs.primary.withValues(alpha: 0.55), width: 1.5)
                : Border.all(
                    color: cs.outlineVariant.withValues(alpha: 0.3),
                  ),
            boxShadow: widget.selected
                ? [
                    BoxShadow(
                      color: cs.primary.withValues(alpha: 0.14),
                      blurRadius: 10,
                      spreadRadius: 0,
                      offset: const Offset(0, 2),
                    ),
                  ]
                : [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: _hovered ? 0.08 : 0.04),
                      blurRadius: _hovered ? 8 : 2,
                      offset: Offset(0, _hovered ? 2 : 1),
                    ),
                  ],
          ),
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              // Row 1: source badge + "New" badge + dedup/republish badges | date right-aligned
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  if (v.site.isNotEmpty) SourceBadge(site: v.site),
                  if (isUnread) ...[
                    const SizedBox(width: 6),
                    _NewBadge(),
                  ],
                  if (v.republishedAt != null) ...[
                    const SizedBox(width: 6),
                    _RepublishedBadge(),
                  ],
                  if (v.duplicateOf != null) ...[
                    const SizedBox(width: 6),
                    _DuplicateBadge(originalId: v.duplicateOf!),
                  ],
                  const Spacer(),
                  if (v.publishedAt != null)
                    Text(
                      _relativeTime(v.publishedAt!),
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(
                            color: cs.secondary,
                          ),
                    ),
                  _StarButton(vacancyId: v.id, isStarred: v.starred),
                ],
              ),
              const SizedBox(height: 8),
              // Row 2: role title + #id aligned right
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Expanded(
                    child: Text(
                      v.role,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            color: widget.selected ? cs.primary : cs.onSurface,
                          ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    '#${v.id}',
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                          color: cs.onSurfaceVariant.withValues(alpha: 0.45),
                        ),
                  ),
                ],
              ),
              const SizedBox(height: 2),
              // Row 3: company
              if (v.company.isNotEmpty)
                Text(
                  v.company,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: cs.onSurfaceVariant,
                      ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              if (v.roleTags.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  v.roleTags.join('  '),
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                        color: cs.secondary.withValues(alpha: 0.65),
                        letterSpacing: 0.2,
                      ),
                ),
              ],
              const SizedBox(height: 10),
              // Row 4: scores or status badge — show scores if present regardless of status
              if (v.fitScore != null || v.vacancyScore != null)
                Row(
                  children: [
                    if (v.fitScore != null) FitScoreChip(score: v.fitScore!),
                    if (v.vacancyScore != null) ...[
                      const SizedBox(width: 6),
                      VacScoreBadge(score: v.vacancyScore!),
                    ],
                  ],
                )
              else if (v.status == 'analysis_failed')
                _FailedBadge(),
              // Row 5: key barrier — show if present regardless of status
              if (v.keyBarriers.isNotEmpty) ...[
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                  decoration: BoxDecoration(
                    color: cs.errorContainer.withValues(alpha: 0.3),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(
                      color: cs.error.withValues(alpha: 0.2),
                    ),
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(Icons.warning_amber_rounded,
                          size: 14, color: cs.error),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(
                          v.keyBarriers.first,
                          style:
                              Theme.of(context).textTheme.labelSmall?.copyWith(
                                    color: cs.onSurfaceVariant,
                                  ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  String _relativeTime(String iso) {
    try {
      final dt = DateTime.parse(iso);
      final diff = DateTime.now().difference(dt);
      if (diff.inDays > 0) return '${diff.inDays}d ago';
      if (diff.inHours > 0) return '${diff.inHours}h ago';
      if (diff.inMinutes > 0) return '${diff.inMinutes}m ago';
      return 'just now';
    } catch (_) {
      return iso;
    }
  }
}

class _NewBadge extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF3E0),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0xFFFFB300), width: 0.8),
      ),
      child: Text(
        'New',
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: const Color(0xFFE65100),
              fontWeight: FontWeight.w700,
              fontSize: 10,
            ),
      ),
    );
  }
}

class _FailedBadge extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.error_outline_rounded, size: 13, color: cs.error),
        const SizedBox(width: 4),
        Text(
          'Analysis failed · tap to retry',
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: cs.error,
                fontWeight: FontWeight.w600,
              ),
        ),
      ],
    );
  }
}

class _RepublishedBadge extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF8E1),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0xFFFFCA28), width: 0.8),
      ),
      child: Text(
        '↑ Republished',
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: const Color(0xFFF57F17),
              fontWeight: FontWeight.w700,
              fontSize: 10,
            ),
      ),
    );
  }
}

class _DuplicateBadge extends StatelessWidget {
  final int originalId;
  const _DuplicateBadge({required this.originalId});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: cs.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: cs.outlineVariant, width: 0.8),
      ),
      child: Text(
        'Dup #$originalId',
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: cs.onSurfaceVariant,
              fontWeight: FontWeight.w600,
              fontSize: 10,
            ),
      ),
    );
  }
}

// ─── Star toggle ─────────────────────────────────────────────────────────────

class _StarButton extends ConsumerStatefulWidget {
  final int vacancyId;
  final bool isStarred;

  const _StarButton({required this.vacancyId, required this.isStarred});

  @override
  ConsumerState<_StarButton> createState() => _StarButtonState();
}

class _StarButtonState extends ConsumerState<_StarButton> {
  late bool _starred;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _starred = widget.isStarred;
  }

  @override
  void didUpdateWidget(_StarButton old) {
    super.didUpdateWidget(old);
    if (old.isStarred != widget.isStarred) _starred = widget.isStarred;
  }

  Future<void> _toggle() async {
    if (_loading) return;
    final next = !_starred;
    setState(() { _starred = next; _loading = true; });
    try {
      final apiUrl = ref.read(settingsProvider).valueOrNull?.apiUrl ?? 'http://localhost:8080';
      await VacancyRepository(baseUrl: apiUrl).setStarred(widget.vacancyId, next);
      if (mounted) ref.read(vacancyListProvider.notifier).refresh();
    } catch (_) {
      if (mounted) setState(() => _starred = !next);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: _toggle,
      child: Padding(
        padding: const EdgeInsets.only(left: 4),
        child: Icon(
          _starred ? Icons.star_rounded : Icons.star_outline_rounded,
          size: 18,
          color: _starred ? const Color(0xFFFFB300) : Theme.of(context).colorScheme.onSurfaceVariant.withValues(alpha: 0.4),
        ),
      ),
    );
  }
}

