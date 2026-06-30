import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class SourceBadge extends StatelessWidget {
  final String site;

  const SourceBadge({super.key, required this.site});

  @override
  Widget build(BuildContext context) {
    final color = SourceColors.forSite(site);
    final label = SourceColors.label(site);

    return Container(
      height: 24,
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(999),
      ),
      alignment: Alignment.center,
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: Colors.white,
              fontWeight: FontWeight.w500,
            ),
      ),
    );
  }
}
