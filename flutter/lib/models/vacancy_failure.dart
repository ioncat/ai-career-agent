/// What is wrong with a vacancy right now — the backend's `failure` projection
/// (`GET /api/vacancies`, `GET /api/vacancies/{id}`; notifications phase 1,
/// 2026-10-09). One model for every failure kind, so the app has one card mark
/// and one panel block instead of a widget pair per failure type.
///
/// The mark is state, not an event: it stays until the failure is cleared on
/// the backend (a successful retry), and it carries the only Retry action.
library;

class VacancyFailure {
  /// fetch | analysis | cv | cover | pdf
  final String kind;

  /// cv | cover for kind "pdf" (which document's PDF failed), null otherwise.
  final String? target;

  /// Technical detail from the backend, shown as-is.
  final String reason;

  /// ISO 8601 UTC. Approximate (the vacancy's updated_at) for fetch/analysis.
  final String at;

  /// fetch | analyze | cv | cover | pdf — which action retries it.
  final String retry;

  /// Stable code (core/failure_codes.py); the text is picked from it.
  final String code;

  const VacancyFailure({
    required this.kind,
    this.target,
    this.reason = '',
    this.at = '',
    required this.retry,
    this.code = 'unknown',
  });

  static VacancyFailure? fromJson(Object? json) {
    if (json is! Map<String, dynamic>) return null;
    final kind = json['kind'] as String? ?? '';
    if (kind.isEmpty) return null;
    return VacancyFailure(
      kind: kind,
      target: json['target'] as String?,
      reason: json['reason'] as String? ?? '',
      at: json['at'] as String? ?? '',
      retry: json['retry'] as String? ?? '',
      code: json['code'] as String? ?? 'unknown',
    );
  }

  Map<String, dynamic> toJson() => {
    'kind': kind,
    'target': target,
    'reason': reason,
    'at': at,
    'retry': retry,
    'code': code,
  };

  String get _pdfDoc => target == 'cover' ? 'Cover' : 'CV';

  /// Short label for the card pill.
  String get shortTitle => switch (kind) {
    'fetch' => 'Fetch failed',
    'analysis' => 'Analysis failed',
    'cv' => 'CV failed',
    'cover' => 'Cover failed',
    'pdf' => '$_pdfDoc PDF failed',
    _ => 'Failed',
  };

  /// Title of the panel block.
  String get title => switch (kind) {
    'fetch' => 'Fetch failed',
    'analysis' => 'Analysis failed',
    'cv' => 'CV generation failed',
    'cover' => 'Cover generation failed',
    'pdf' => '$_pdfDoc PDF failed',
    _ => 'Something went wrong',
  };

  /// One plain sentence: what happened. Unknown (future) codes get a generic
  /// sentence; the raw `reason` is always shown next to it.
  String get message => switch (code) {
    'fetch_gave_up' =>
      'The system could not fetch this vacancy from its posting page after '
          'several attempts, so there is no job description yet.',
    'analysis_failed' => 'The analysis run failed.',
    'llm_error' => 'The AI model returned an error.',
    'llm_timeout' => 'The AI model did not answer in time.',
    'jd_missing' => 'The job description file is missing on disk.',
    'analysis_missing' => 'The analysis file is missing on disk.',
    'cv_missing' => 'The CV file is missing on disk.',
    'generation_failed' => 'The generation run failed.',
    'pdf_service_unreachable' =>
      'The PDF service is not reachable (down or too slow).',
    'pdf_service_error' => 'The PDF service returned an error.',
    'pdf_invalid' => 'The PDF service returned a file that is not a valid PDF.',
    'pdf_write_failed' => 'The PDF could not be saved to disk.',
    _ => 'Something went wrong.',
  };

  /// Label of the one Retry button; null when the retry action is unknown.
  String? get retryLabel => switch (retry) {
    'fetch' => 'Retry fetch',
    'analyze' => 'Retry analysis',
    'cv' => 'Retry CV',
    'cover' => 'Retry cover',
    'pdf' => 'Retry PDF',
    _ => null,
  };

  /// No job description exists, so the JD view has nothing to show.
  bool get hidesJd => kind == 'fetch';
}
