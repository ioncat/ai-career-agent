import 'package:flutter/material.dart';

class AppTheme {
  static const _primary = Color(0xFF005DAC);
  static const _secondary = Color(0xFF046B5E);

  static ThemeData get light => ThemeData(
        useMaterial3: true,
        colorScheme: const ColorScheme(
          brightness: Brightness.light,
          primary: _primary,
          onPrimary: Color(0xFFFFFFFF),
          primaryContainer: Color(0xFF1976D2),
          onPrimaryContainer: Color(0xFFFFFFFF),
          secondary: _secondary,
          onSecondary: Color(0xFFFFFFFF),
          secondaryContainer: Color(0xFF9DEFDE),
          onSecondaryContainer: Color(0xFF0F6F62),
          tertiary: Color(0xFF8A31B1),
          onTertiary: Color(0xFFFFFFFF),
          tertiaryContainer: Color(0xFFA64DCC),
          onTertiaryContainer: Color(0xFFFFFFFF),
          error: Color(0xFFBA1A1A),
          onError: Color(0xFFFFFFFF),
          errorContainer: Color(0xFFFFDAD6),
          onErrorContainer: Color(0xFF93000A),
          surface: Color(0xFFF9F9FF),
          onSurface: Color(0xFF181C21),
          surfaceContainerLowest: Color(0xFFFFFFFF),
          surfaceContainerLow: Color(0xFFF2F3FC),
          surfaceContainer: Color(0xFFECEDF6),
          surfaceContainerHigh: Color(0xFFE6E8F0),
          surfaceContainerHighest: Color(0xFFE0E2EA),
          onSurfaceVariant: Color(0xFF414752),
          outline: Color(0xFF717783),
          outlineVariant: Color(0xFFC1C6D4),
          inverseSurface: Color(0xFF2D3037),
          onInverseSurface: Color(0xFFEFF0F9),
          inversePrimary: Color(0xFFA5C8FF),
          surfaceTint: _primary,
        ),
        fontFamily: 'Inter',
        navigationRailTheme: const NavigationRailThemeData(
          backgroundColor: Color(0xFFF2F3FC),
          indicatorColor: Color(0xFFD4E3FF),
          labelType: NavigationRailLabelType.all,
        ),
        cardTheme: CardThemeData(
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
            side: const BorderSide(color: Color(0xFFC1C6D4), width: 1),
          ),
          color: Color(0xFFFFFFFF),
        ),
        dividerTheme: const DividerThemeData(
          color: Color(0xFFC1C6D4),
          thickness: 1,
          space: 1,
        ),
      );
}

// Semantic color tokens — used directly in widgets
class FitColors {
  static Color forScore(int score) {
    if (score >= 8) return const Color(0xFF2E7D32);
    if (score >= 6) return const Color(0xFF00695C);
    if (score >= 4) return const Color(0xFFE65100);
    return const Color(0xFFC62828);
  }
}

class VacScoreColors {
  static Color forScore(double score) {
    if (score >= 7.5) return const Color(0xFF388E3C);
    if (score >= 5.5) return const Color(0xFFF57C00);
    return const Color(0xFF757575);
  }

  static String tierLabel(double score) {
    if (score >= 7.5) return 'Premium';
    if (score >= 5.5) return 'Solid';
    return 'Limited';
  }
}

class RecColors {
  static Color forRec(String rec) {
    switch (rec) {
      case 'apply':
        return const Color(0xFF2E7D32);
      case 'take_a_chance':
        return const Color(0xFFF57C00);
      default:
        return const Color(0xFF757575);
    }
  }

  static String icon(String rec) {
    switch (rec) {
      case 'apply':
        return '✅';
      case 'take_a_chance':
        return '⚡';
      default:
        return '✗';
    }
  }
}

class SourceColors {
  static Color forSite(String site) {
    switch (site.toLowerCase()) {
      case 'djinni':
        return const Color(0xFF1565C0);
      case 'dou':
        return const Color(0xFF2E7D32);
      case 'linkedin':
        return const Color(0xFF0A3D62);
      default:
        return const Color(0xFF616161);
    }
  }

  static String label(String site) {
    switch (site.toLowerCase()) {
      case 'djinni':
        return 'Djinni';
      case 'dou':
        return 'DOU.ua';
      case 'linkedin':
        return 'LinkedIn';
      default:
        return site.isEmpty ? 'Other' : site;
    }
  }
}
