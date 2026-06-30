import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

// ── Brand colors (from DESIGN.md / Fluid Desktop Workspace) ──────────────────

class AppColors {
  // Source-platform brand colors (not in M3 ColorScheme)
  static const sourceDjinni  = Color(0xFF007BFF);
  static const sourceDou     = Color(0xFF4CAF50);
  static const sourceLinkedIn = Color(0xFF004182);
  static const sourceOther   = Color(0xFF7A7582);  // == outline
}

// ── Full M3 ColorScheme (Fluid Desktop Workspace palette) ─────────────────────

const _colorScheme = ColorScheme(
  brightness: Brightness.light,

  primary:            Color(0xFF4F378A),
  onPrimary:          Color(0xFFFFFFFF),
  primaryContainer:   Color(0xFF6750A4),
  onPrimaryContainer: Color(0xFFE0D2FF),

  secondary:            Color(0xFF625B71),
  onSecondary:          Color(0xFFFFFFFF),
  secondaryContainer:   Color(0xFFE8DEF9),
  onSecondaryContainer: Color(0xFF686177),

  tertiary:            Color(0xFF633B48),
  onTertiary:          Color(0xFFFFFFFF),
  tertiaryContainer:   Color(0xFF7D5260),
  onTertiaryContainer: Color(0xFFFFCBDA),

  error:            Color(0xFFBA1A1A),
  onError:          Color(0xFFFFFFFF),
  errorContainer:   Color(0xFFFFDAD6),
  onErrorContainer: Color(0xFF93000A),

  surface:                  Color(0xFFFDF7FF),
  onSurface:                Color(0xFF1D1B20),
  surfaceContainerLowest:   Color(0xFFFFFFFF),
  surfaceContainerLow:      Color(0xFFF8F2FA),
  surfaceContainer:         Color(0xFFF3F3F7),
  surfaceContainerHigh:     Color(0xFFECE6EE),
  surfaceContainerHighest:  Color(0xFFE6E0E9),
  onSurfaceVariant:         Color(0xFF494551),

  outline:        Color(0xFF7A7582),
  outlineVariant: Color(0xFFCBC4D2),

  inverseSurface:   Color(0xFF322F35),
  onInverseSurface: Color(0xFFF5EFF7),
  inversePrimary:   Color(0xFFCFBCFF),

  surfaceTint: Color(0xFF6750A4),
);

// ── TextTheme (Hanken Grotesk / Inter / JetBrains Mono) ──────────────────────

TextTheme _buildTextTheme() {
  final hg = GoogleFonts.hankenGroteskTextTheme();
  final inter = GoogleFonts.interTextTheme();
  final jbm = GoogleFonts.jetBrainsMonoTextTheme();

  return TextTheme(
    // Headings — Hanken Grotesk
    displaySmall:   hg.displaySmall?.copyWith(fontSize: 24, fontWeight: FontWeight.w700, height: 32/24),
    headlineMedium: hg.headlineMedium?.copyWith(fontSize: 20, fontWeight: FontWeight.w600, height: 28/20),
    titleMedium:    hg.titleMedium?.copyWith(fontSize: 16, fontWeight: FontWeight.w700, height: 24/16),
    titleSmall:     hg.titleSmall?.copyWith(fontSize: 14, fontWeight: FontWeight.w600, height: 20/14),
    // Body — Inter
    bodyMedium: inter.bodyMedium?.copyWith(fontSize: 14, fontWeight: FontWeight.w400, height: 20/14),
    bodySmall:  inter.bodySmall?.copyWith(fontSize: 12, fontWeight: FontWeight.w400, height: 16/12),
    // Labels — JetBrains Mono
    labelMedium: jbm.labelMedium?.copyWith(fontSize: 12, fontWeight: FontWeight.w500, height: 16/12),
    labelSmall:  jbm.labelSmall?.copyWith(fontSize: 11, fontWeight: FontWeight.w500, height: 16/11, letterSpacing: 0.5),
  );
}

// ── ThemeData ─────────────────────────────────────────────────────────────────

class AppTheme {
  static ThemeData get light => ThemeData(
    useMaterial3: true,
    colorScheme: _colorScheme,
    textTheme: _buildTextTheme(),
    navigationRailTheme: NavigationRailThemeData(
      backgroundColor: _colorScheme.surfaceContainer,
      indicatorColor: _colorScheme.secondaryContainer,
      selectedIconTheme: IconThemeData(color: _colorScheme.primary),
      unselectedIconTheme: IconThemeData(color: _colorScheme.onSurfaceVariant),
      labelType: NavigationRailLabelType.all,
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: _colorScheme.outlineVariant.withValues(alpha: 0.3), width: 1),
      ),
      color: _colorScheme.surface,
    ),
    dividerTheme: DividerThemeData(
      color: _colorScheme.outlineVariant.withValues(alpha: 0.3),
      thickness: 1,
      space: 1,
    ),
  );
}

// ── Semantic color helpers ────────────────────────────────────────────────────

class FitColors {
  static Color forScore(int score, ColorScheme cs) {
    if (score >= 8) return cs.primary;
    if (score >= 6) return cs.secondary;
    if (score >= 4) return cs.tertiary;
    return cs.error;
  }

  static Color bgForScore(int score, ColorScheme cs) {
    if (score >= 8) return cs.primaryContainer.withValues(alpha: 0.15);
    if (score >= 6) return cs.secondaryContainer.withValues(alpha: 0.15);
    if (score >= 4) return cs.tertiaryContainer.withValues(alpha: 0.15);
    return cs.errorContainer.withValues(alpha: 0.15);
  }
}

class VacScoreColors {
  static Color forScore(double score, ColorScheme cs) {
    if (score >= 7.5) return cs.primary;
    if (score >= 5.5) return cs.secondary;
    return cs.outline;
  }

  static Color bgForScore(double score, ColorScheme cs) {
    if (score >= 7.5) return cs.primaryContainer;
    if (score >= 5.5) return cs.secondaryContainer;
    return cs.surface;
  }

  static Color onBgForScore(double score, ColorScheme cs) {
    if (score >= 7.5) return cs.onPrimaryContainer;
    if (score >= 5.5) return cs.onSecondaryContainer;
    return cs.onSurfaceVariant;
  }

  static String tierLabel(double score) {
    if (score >= 7.5) return 'Premium';
    if (score >= 5.5) return 'Solid';
    return 'Limited';
  }
}

class SourceColors {
  static Color forSite(String site) {
    switch (site.toLowerCase()) {
      case 'djinni':   return AppColors.sourceDjinni;
      case 'dou':      return AppColors.sourceDou;
      case 'linkedin': return AppColors.sourceLinkedIn;
      default:         return AppColors.sourceOther;
    }
  }

  static String label(String site) {
    switch (site.toLowerCase()) {
      case 'djinni':   return 'Djinni';
      case 'dou':      return 'DOU.ua';
      case 'linkedin': return 'LinkedIn';
      default:         return site.isEmpty ? 'Other' : site;
    }
  }
}

class RecColors {
  static Color forRec(String rec, ColorScheme cs) {
    switch (rec) {
      case 'apply':         return cs.primary;
      case 'take_a_chance': return cs.tertiaryContainer;
      default:              return cs.surface;
    }
  }

  static Color onForRec(String rec, ColorScheme cs) {
    switch (rec) {
      case 'apply':         return cs.onPrimary;
      case 'take_a_chance': return cs.onTertiaryContainer;
      default:              return cs.onSurfaceVariant;
    }
  }

  static IconData iconForRec(String rec) {
    switch (rec) {
      case 'apply':         return Icons.check;
      case 'take_a_chance': return Icons.bolt;
      default:              return Icons.close;
    }
  }
}
