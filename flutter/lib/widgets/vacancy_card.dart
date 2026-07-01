import 'package:flutter/material.dart';
import '../models/vacancy.dart';
import 'fit_score_chip.dart';
import 'vac_score_badge.dart';
import 'source_badge.dart';

class VacancyCard extends StatefulWidget {
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
  State<VacancyCard> createState() => _VacancyCardState();
}

class _VacancyCardState extends State<VacancyCard> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final v = widget.vacancy;

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
          margin: const EdgeInsets.only(bottom: 8),
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
              // Row 1: source badge + date
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  if (v.site.isNotEmpty) SourceBadge(site: v.site),
                  if (v.publishedAt != null) ...[
                    const SizedBox(width: 8),
                    Text(
                      _relativeTime(v.publishedAt!),
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(
                            color: cs.secondary,
                          ),
                    ),
                  ],
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
              const SizedBox(height: 10),
              // Row 4: scores
              Row(
                children: [
                  if (v.fitScore != null) FitScoreChip(score: v.fitScore!),
                  if (v.vacancyScore != null) ...[
                    const SizedBox(width: 6),
                    VacScoreBadge(score: v.vacancyScore!),
                  ],
                ],
              ),
              // Row 5: key barrier (optional)
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
      if (diff.inDays > 0) return '${diff.inDays}д назад';
      if (diff.inHours > 0) return '${diff.inHours}ч назад';
      if (diff.inMinutes > 0) return '${diff.inMinutes}м назад';
      return 'только что';
    } catch (_) {
      return iso;
    }
  }
}

