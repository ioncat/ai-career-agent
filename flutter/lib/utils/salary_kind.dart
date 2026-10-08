/// The `salary` column is free text that holds one of three things: a figure
/// from the vacancy, a Djinni filter estimate written by the salary probe, or
/// a probe give-up note. The markers mirror the backend
/// (`tools/cv_fetch_jd.py`: `_is_real_salary()`, `_PROBE_NOTE_PREFIX`, and the
/// estimate format `~$N+ (Djinni filter estimate)`), so both sides agree on
/// what counts as a real value.
library;

enum SalaryKind { none, real, estimate, note }

const _notePrefix = '(';
const _estimateSuffix = '(Djinni filter estimate)';

SalaryKind salaryKind(String? salary) {
  final s = salary?.trim() ?? '';
  if (s.isEmpty) return SalaryKind.none;
  if (s.startsWith(_notePrefix)) return SalaryKind.note;
  if (s.endsWith(_estimateSuffix)) return SalaryKind.estimate;
  return SalaryKind.real;
}

/// The text to show: the estimate without its source suffix, the note
/// without its parentheses, a real value as is.
String salaryDisplayText(String salary) {
  final s = salary.trim();
  switch (salaryKind(s)) {
    case SalaryKind.estimate:
      return s.substring(0, s.length - _estimateSuffix.length).trim();
    case SalaryKind.note:
      final inner = s.substring(1);
      return (inner.endsWith(')')
              ? inner.substring(0, inner.length - 1)
              : inner)
          .trim();
    case SalaryKind.real:
    case SalaryKind.none:
      return s;
  }
}
