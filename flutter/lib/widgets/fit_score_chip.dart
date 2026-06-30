import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class FitScoreChip extends StatelessWidget {
  final int score;
  final bool large;

  const FitScoreChip({super.key, required this.score, this.large = false});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final fg = FitColors.forScore(score, cs);
    final bg = FitColors.bgForScore(score, cs);

    return Container(
      height: 24,
      padding: EdgeInsets.symmetric(horizontal: large ? 10 : 8),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(999),
      ),
      alignment: Alignment.center,
      child: Text(
        large ? 'Fit $score/10' : 'F: $score',
        style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: fg,
              fontWeight: FontWeight.w700,
            ),
      ),
    );
  }
}
