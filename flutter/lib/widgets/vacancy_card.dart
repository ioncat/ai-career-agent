import 'package:flutter/material.dart';
import '../models/vacancy.dart';
import 'fit_score_chip.dart';
import 'vac_score_badge.dart';
import 'recommendation_chip.dart';
import 'source_badge.dart';

class VacancyCard extends StatelessWidget {
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
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return InkWell(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        decoration: BoxDecoration(
          color: selected ? cs.primaryContainer.withOpacity(0.3) : cs.surface,
          border: Border(
            left: BorderSide(
              color: selected ? cs.primary : Colors.transparent,
              width: 3,
            ),
            bottom: BorderSide(color: cs.outlineVariant, width: 1),
          ),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Row 1: role + source badge
            Row(
              children: [
                Expanded(
                  child: Text(
                    vacancy.role,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 8),
                SourceBadge(site: vacancy.site),
              ],
            ),
            const SizedBox(height: 4),
            // Row 2: company + scores
            Row(
              children: [
                Expanded(
                  child: Text(
                    vacancy.company,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: cs.onSurfaceVariant,
                        ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const SizedBox(width: 8),
                if (vacancy.fitScore != null)
                  FitScoreChip(score: vacancy.fitScore!),
                if (vacancy.vacancyScore != null) ...[
                  const SizedBox(width: 4),
                  VacScoreBadge(score: vacancy.vacancyScore!),
                ],
              ],
            ),
            const SizedBox(height: 4),
            // Row 3: recommendation + date
            Row(
              children: [
                if (vacancy.recommendation != null &&
                    vacancy.recommendationLabel != null)
                  Expanded(
                    child: RecommendationChip(
                      recommendation: vacancy.recommendation!,
                      label: vacancy.recommendationLabel!,
                    ),
                  ),
                if (vacancy.publishedAt != null)
                  Text(
                    _relativeTime(vacancy.publishedAt!),
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                          color: cs.onSurfaceVariant,
                        ),
                  ),
              ],
            ),
            // Row 4: first barrier (optional)
            if (vacancy.keyBarriers.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                '⚠️ ${vacancy.keyBarriers.first}',
                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: const Color(0xFFE65100),
                    ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ],
          ],
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
