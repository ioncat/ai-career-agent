import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class RecommendationChip extends StatelessWidget {
  final String recommendation;
  final String label;

  const RecommendationChip({
    super.key,
    required this.recommendation,
    required this.label,
  });

  @override
  Widget build(BuildContext context) {
    final color = RecColors.forRec(recommendation);
    final icon = RecColors.icon(recommendation);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withOpacity(0.35)),
      ),
      child: Text(
        '$icon $label',
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w500,
          color: color,
        ),
        overflow: TextOverflow.ellipsis,
      ),
    );
  }
}
