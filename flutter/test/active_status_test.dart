import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/utils/active_status.dart';

void main() {
  group('keepSelectionOutsideFolder', () {
    test('a run in progress keeps the vacancy open', () {
      for (final s in [
        'analysis_queued',
        'analyzing',
        'cv_queued',
        'cv_generating',
      ]) {
        expect(keepSelectionOutsideFolder(s), isTrue, reason: s);
      }
    });

    test('a finished or moved vacancy clears the panel', () {
      for (final s in ['analyzed', 'cv_generated', 'declined', 'fetched']) {
        expect(keepSelectionOutsideFolder(s), isFalse, reason: s);
      }
    });

    test('a vacancy missing from the list clears the panel', () {
      expect(keepSelectionOutsideFolder(null), isFalse);
    });
  });
}
