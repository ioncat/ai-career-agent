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
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w500,
          color: color,
          letterSpacing: 0.3,
        ),
      ),
    );
  }
}
