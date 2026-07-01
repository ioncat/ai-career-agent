import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class FitScoreChip extends StatelessWidget {
  final int score;

  const FitScoreChip({super.key, required this.score});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final fg = FitColors.forScore(score, cs);
    final bg = FitColors.bgForScore(score, cs);

    return Container(
      height: 24,
      padding: const EdgeInsets.symmetric(horizontal: 8),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(999),
      ),
      alignment: Alignment.center,
      child: Text(
        'Fit $score',
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: fg,
              fontWeight: FontWeight.w700,
            ),
      ),
    );
  }
}
