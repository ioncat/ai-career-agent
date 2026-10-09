import 'package:flutter_test/flutter_test.dart';
import 'package:career_agent/models/vacancy.dart';
import 'package:career_agent/models/vacancy_failure.dart';

Map<String, dynamic> _f(
  String kind,
  String retry,
  String code, {
  String? target,
}) => {
  'kind': kind,
  'target': target,
  'reason': 'raw detail',
  'at': '2026-10-09T10:00:00Z',
  'retry': retry,
  'code': code,
};

void main() {
  test('null or empty json gives no failure', () {
    expect(VacancyFailure.fromJson(null), isNull);
    expect(VacancyFailure.fromJson(<String, dynamic>{}), isNull);
  });

  test('each kind has its own short title and retry label', () {
    final cases = {
      _f('fetch', 'fetch', 'fetch_gave_up'): ('Fetch failed', 'Retry fetch'),
      _f('analysis', 'analyze', 'analysis_failed'): (
        'Analysis failed',
        'Retry analysis',
      ),
      _f('cv', 'cv', 'llm_timeout'): ('CV failed', 'Retry CV'),
      _f('cover', 'cover', 'llm_error'): ('Cover failed', 'Retry cover'),
      _f('pdf', 'pdf', 'pdf_invalid', target: 'cv'): (
        'CV PDF failed',
        'Retry PDF',
      ),
      _f('pdf', 'pdf', 'pdf_service_unreachable', target: 'cover'): (
        'Cover PDF failed',
        'Retry PDF',
      ),
    };
    cases.forEach((json, expected) {
      final f = VacancyFailure.fromJson(json)!;
      expect(f.shortTitle, expected.$1);
      expect(f.retryLabel, expected.$2);
    });
  });

  test('known codes get a specific message, unknown ones a generic one', () {
    expect(
      VacancyFailure.fromJson(_f('cv', 'cv', 'llm_timeout'))!.message,
      contains('did not answer in time'),
    );
    expect(
      VacancyFailure.fromJson(_f('cv', 'cv', 'something_new'))!.message,
      'Something went wrong.',
    );
  });

  test('only a fetch failure hides the JD view', () {
    expect(
      VacancyFailure.fromJson(_f('fetch', 'fetch', 'fetch_gave_up'))!.hidesJd,
      isTrue,
    );
    expect(
      VacancyFailure.fromJson(
        _f('analysis', 'analyze', 'analysis_failed'),
      )!.hidesJd,
      isFalse,
    );
  });

  test('the vacancy list item parses the failure field', () {
    final v = VacancyListItem.fromJson({
      'id': 1,
      'title': 'PM',
      'company': 'Acme',
      'site': 'dou',
      'url': 'https://example.com/1',
      'status': 'cv_generated',
      'failure': _f('pdf', 'pdf', 'pdf_write_failed', target: 'cv'),
    });
    expect(v.failure?.kind, 'pdf');
    expect(v.failure?.target, 'cv');
    expect(
      VacancyListItem.fromJson({...v.toJson()}).failure?.code,
      'pdf_write_failed',
    );
  });

  test('each retry maps to exactly one backend call', () {
    RetryCall? call(String retry, {String? target}) =>
        VacancyFailure(kind: 'x', retry: retry, target: target).retryCall;
    expect(call('fetch'), RetryCall.restore);
    expect(call('analyze'), RetryCall.resetAndAnalyze);
    expect(call('cv'), RetryCall.generateCv);
    expect(call('cover'), RetryCall.generateCover);
    expect(call('pdf', target: 'cover'), RetryCall.renderPdf);
    expect(call('pdf'), isNull, reason: 'a PDF failure needs its target');
    expect(call('something_new'), isNull);
  });

  test('no retry call means no Retry button', () {
    expect(
      VacancyFailure.fromJson(_f('pdf', 'pdf', 'pdf_invalid'))!.retryLabel,
      isNull,
    );
  });

  test('a run in progress blocks Retry', () {
    for (final s in [
      'cv_generating',
      'cover_generating',
      'analyzing',
      'queued',
    ]) {
      expect(VacancyFailure.runInProgress(s), isTrue, reason: s);
    }
    for (final s in ['analyzed', 'cv_generated', 'fetch_failed', null]) {
      expect(VacancyFailure.runInProgress(s), isFalse, reason: '$s');
    }
  });

  test('a field of the wrong type does not break the parse', () {
    final f = VacancyFailure.fromJson({
      'kind': 'cv',
      'reason': 42,
      'retry': 'cv',
      'code': null,
      'lang': 'uk',
    })!;
    expect(f.reason, '');
    expect(f.code, 'unknown');
    expect(f.lang, 'uk');
    expect(VacancyFailure.fromJson({'kind': 7}), isNull);
  });
}
