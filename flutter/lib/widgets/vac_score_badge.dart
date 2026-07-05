import 'package:flutter/material.dart';

class VacScoreBadge extends StatelessWidget {
  final double score;

  const VacScoreBadge({super.key, required this.score});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    // No `alignment` → Container wraps to content size (text + padding).
    return Container(
      height: 24,
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(
        color: cs.surfaceContainerLowest,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: cs.outlineVariant.withValues(alpha: 0.55)),
      ),
      child: Text(
        'Attraction ${score.toStringAsFixed(1)}',
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: cs.onSurfaceVariant,
              fontWeight: FontWeight.w500,
            ),
      ),
    );
  }
}
