import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class FitScoreChip extends StatelessWidget {
  final int score;
  final bool large;

  const FitScoreChip({super.key, required this.score, this.large = false});

  @override
  Widget build(BuildContext context) {
    final color = FitColors.forScore(score);
    final size = large ? 14.0 : 11.0;
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: large ? 10 : 6,
        vertical: large ? 4 : 2,
      ),
      decoration: BoxDecoration(
        color: color.withOpacity(0.12),
        border: Border.all(color: color.withOpacity(0.4)),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        'Fit $score/10',
        style: TextStyle(
          fontSize: size,
          fontWeight: FontWeight.w600,
          color: color,
        ),
      ),
    );
  }
}
