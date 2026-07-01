import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class VacScoreBadge extends StatelessWidget {
  final double score;

  const VacScoreBadge({super.key, required this.score});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final bg = VacScoreColors.bgForScore(score, cs);
    final fg = VacScoreColors.onBgForScore(score, cs);

    return Container(
      height: 24,
      padding: const EdgeInsets.symmetric(horizontal: 8),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(6),
        border: score < 5.5
            ? Border.all(color: cs.outline.withValues(alpha: 0.5))
            : null,
      ),
      alignment: Alignment.center,
      child: Text(
        'Attraction ${score.toStringAsFixed(1)}',
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: fg,
              fontWeight: FontWeight.w700,
            ),
      ),
    );
  }
}
