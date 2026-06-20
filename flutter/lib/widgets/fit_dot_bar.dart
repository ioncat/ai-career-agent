import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class FitDotBar extends StatelessWidget {
  final int score;

  const FitDotBar({super.key, required this.score});

  @override
  Widget build(BuildContext context) {
    final filled = FitColors.forScore(score);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(10, (i) {
        return Container(
          width: 10,
          height: 10,
          margin: const EdgeInsets.only(right: 4),
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: i < score ? filled : const Color(0xFFE0E0E0),
          ),
        );
      }),
    );
  }
}
