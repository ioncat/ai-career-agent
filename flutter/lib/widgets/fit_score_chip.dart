import 'package:flutter/material.dart';

class FitScoreChip extends StatelessWidget {
  final int score;

  const FitScoreChip({super.key, required this.score});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return _InfoBadge(label: 'Fit $score', cs: cs);
  }
}

class _InfoBadge extends StatelessWidget {
  final String label;
  final ColorScheme cs;

  const _InfoBadge({required this.label, required this.cs});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 24,
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(
        color: cs.surfaceContainerLowest,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: cs.outlineVariant.withValues(alpha: 0.55)),
      ),
      alignment: Alignment.center,
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: cs.onSurfaceVariant,
              fontWeight: FontWeight.w500,
            ),
      ),
    );
  }
}
