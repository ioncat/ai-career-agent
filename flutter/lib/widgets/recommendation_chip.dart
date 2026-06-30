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
    final cs = Theme.of(context).colorScheme;
    final bg = RecColors.forRec(recommendation, cs);
    final fg = RecColors.onForRec(recommendation, cs);
    final icon = RecColors.iconForRec(recommendation);
    final isOutlined = recommendation != 'apply' && recommendation != 'take_a_chance';

    return Container(
      height: 28,
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(999),
        border: isOutlined ? Border.all(color: cs.outline) : null,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: fg),
          const SizedBox(width: 4),
          Flexible(
            child: Text(
              label,
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                    color: fg,
                    fontWeight: FontWeight.w500,
                  ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}
