import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class VacScoreBadge extends StatelessWidget {
  final double score;
  final bool large;

  const VacScoreBadge({super.key, required this.score, this.large = false});

  @override
  Widget build(BuildContext context) {
    final color = VacScoreColors.forScore(score);
    final tier = VacScoreColors.tierLabel(score);
    final size = large ? 13.0 : 10.0;
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: large ? 8 : 5,
        vertical: large ? 3 : 2,
      ),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Text(
        '${score.toStringAsFixed(1)} $tier',
        style: TextStyle(
          fontSize: size,
          fontWeight: FontWeight.w600,
          color: color,
        ),
      ),
    );
  }
}
