import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class FitDotBar extends StatelessWidget {
  final int score;

  const FitDotBar({super.key, required this.score});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final filledColor = FitColors.forScore(score, cs);
    final emptyColor = cs.surfaceContainerHighest;

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(10, (i) {
        return Container(
          width: 10,
          height: 10,
          margin: const EdgeInsets.only(right: 4),
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: i < score ? filledColor : emptyColor,
          ),
        );
      }),
    );
  }
}
