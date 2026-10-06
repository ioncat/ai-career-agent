import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/models/vacancy.dart';
import 'package:career_agent/screens/analytics_screen.dart';

// Summary counters on the Analytics screen (2026-10-06). "Analyzed" = has a
// Phase 2 fit score in ANY status; "Applied" = the applied flag. Date ranges
// come from analyzed_at (pipeline_runs) and applied_at.

VacancyListItem _v(
  int id, {
  int? fit,
  bool applied = false,
  String status = 'fetched',
  String? analyzedAt,
  String? appliedAt,
}) =>
    VacancyListItem.fromJson({
      'id': id,
      'title': 'Product Owner',
      'company': 'Acme',
      'site': 'djinni',
      'url': 'https://example.com/$id',
      'status': status,
      'fit_score': ?fit,
      'applied': applied,
      'analyzed_at': analyzedAt,
      'applied_at': appliedAt,
    });

void main() {
  test('empty list gives zeros and no period', () {
    final c = analysisCounts([]);
    expect((c.analyzed, c.applied, c.appliedAnalyzed), (0, 0, 0));
    expect(c.period, isNull);
  });

  test('analyzed counts every status that carries a fit score, applied or not', () {
    final c = analysisCounts([
      _v(1, fit: 70, status: 'analyzed'),
      _v(2, fit: 55, status: 'cv_generated'),
      _v(3, fit: 80, applied: true, status: 'cover_generated'),
      _v(4, fit: 40, status: 'declined'),
      _v(5), // never analyzed
    ]);
    expect(c.analyzed, 4);
  });

  test('applied counts the flag, including vacancies applied to without analysis', () {
    final c = analysisCounts([
      _v(1, fit: 80, applied: true),
      _v(2, applied: true), // applied straight from Inbox
      _v(3, fit: 60),
    ]);
    expect(c.applied, 2);
    expect(c.appliedAnalyzed, 1);
  });

  test('period covers both metrics: earliest and latest across analyses and applications', () {
    final c = analysisCounts([
      _v(1, fit: 70, analyzedAt: '2026-08-10T12:00:00Z'),
      _v(2, fit: 70, analyzedAt: '2026-06-20T12:00:00Z'),
      _v(3, fit: 70, analyzedAt: '2026-10-05T12:00:00Z'),
      // applications reach further on both ends than the analyses do
      _v(4, applied: true, appliedAt: '2026-06-03T12:00:00Z'),
      _v(5, applied: true, appliedAt: '2026-10-06T12:00:00Z'),
    ]);
    expect((c.period!.from.month, c.period!.from.day), (6, 3));
    expect((c.period!.to.month, c.period!.to.day), (10, 6));
  });

  test('period ignores dates of vacancies that are neither analyzed nor applied', () {
    final c = analysisCounts([
      _v(1, fit: 70, analyzedAt: '2026-08-10T12:00:00Z'),
      _v(2, analyzedAt: '2026-01-01T12:00:00Z'), // no fit score: not analyzed
      _v(3, appliedAt: '2026-12-31T12:00:00Z'), // not applied
    ]);
    expect((c.period!.from.month, c.period!.from.day), (8, 10));
    expect(c.period!.to, c.period!.from);
  });

  test('vacancies without a date are counted but left out of the period', () {
    final c = analysisCounts([
      _v(1, fit: 70, analyzedAt: '2026-06-20T12:00:00Z'),
      _v(2, fit: 70),
      _v(3, fit: 70),
      _v(4, applied: true),
    ]);
    expect(c.analyzed, 3);
    expect(c.analyzedUndated, 2);
    expect(c.appliedUndated, 1);
    expect(c.period, isNotNull);
  });

  test('analyzedAt round-trips through fromJson / toJson', () {
    final v = _v(1, fit: 70, analyzedAt: '2026-06-20T12:00:00Z');
    expect(v.analyzedAt, '2026-06-20T12:00:00Z');
    expect(v.toJson()['analyzed_at'], '2026-06-20T12:00:00Z');
    expect(_v(2).analyzedAt, isNull);
  });
}
