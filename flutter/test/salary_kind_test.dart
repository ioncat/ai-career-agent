import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/utils/salary_kind.dart';

void main() {
  group('salaryKind', () {
    test('empty or null is none', () {
      expect(salaryKind(null), SalaryKind.none);
      expect(salaryKind(''), SalaryKind.none);
      expect(salaryKind('  '), SalaryKind.none);
    });

    test('a disclosed figure is real', () {
      expect(salaryKind(r'$2900-4600'), SalaryKind.real);
      expect(salaryKind(r'$3600'), SalaryKind.real);
    });

    test('the probe success format is an estimate', () {
      expect(
        salaryKind(r'~$3500+ (Djinni filter estimate)'),
        SalaryKind.estimate,
      );
    });

    test('a leading parenthesis is a give-up note', () {
      expect(
        salaryKind(r'(~$10,000+ or no salary listed at all)'),
        SalaryKind.note,
      );
      expect(salaryKind('(network error — will retry)'), SalaryKind.note);
    });

    test('a parenthesis mid-string does not make a note', () {
      expect(salaryKind(r'$3000 (gross)'), SalaryKind.real);
    });
  });

  group('salaryDisplayText', () {
    test('estimate drops its source suffix', () {
      expect(
        salaryDisplayText(r'~$3500+ (Djinni filter estimate)'),
        r'~$3500+',
      );
    });

    test('note drops its parentheses', () {
      expect(
        salaryDisplayText(r'(~$10,000+ or no salary listed at all)'),
        r'~$10,000+ or no salary listed at all',
      );
    });

    test('real value is unchanged', () {
      expect(salaryDisplayText(r'$2900-4600'), r'$2900-4600');
    });
  });
}
