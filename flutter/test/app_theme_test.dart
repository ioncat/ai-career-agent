import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/theme/app_theme.dart';

// Fonts bundled locally (2026-07-25) instead of fetched at runtime via
// google_fonts — that package's async fetch/cache-read raced first-frame
// layout of IntrinsicWidth-sized widgets (SourceBadge pills truncated on
// app start, self-corrected once the font swapped in ~a minute later).
// Widget tests never exercised the real async path (flutter_test never
// does a genuine network/cache font fetch), so this couldn't catch the
// original bug — this just guards against silently reverting to
// GoogleFonts.*TextTheme() by asserting the TextTheme resolves to the
// bundled family names declared in pubspec.yaml.

void main() {
  test('TextTheme uses the locally-bundled font families, not GoogleFonts', () {
    final t = AppTheme.light.textTheme;

    expect(t.displaySmall?.fontFamily, 'Hanken Grotesk');
    expect(t.headlineMedium?.fontFamily, 'Hanken Grotesk');
    expect(t.titleMedium?.fontFamily, 'Hanken Grotesk');
    expect(t.titleSmall?.fontFamily, 'Hanken Grotesk');

    expect(t.bodyMedium?.fontFamily, 'Inter');
    expect(t.bodySmall?.fontFamily, 'Inter');

    expect(t.labelMedium?.fontFamily, 'JetBrains Mono');
    expect(t.labelSmall?.fontFamily, 'JetBrains Mono');
  });
}
