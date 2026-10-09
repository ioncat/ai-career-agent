/// What is wrong with a vacancy right now — the backend's `failure` projection
/// (`GET /api/vacancies`, `GET /api/vacancies/{id}`; notifications phase 1,
/// 2026-10-09). One model for every failure kind, so the app has one card mark
/// and one panel block instead of a widget pair per failure type.
///
/// The mark is state, not an event: it stays until the failure is cleared on
/// the backend (a successful retry), and it carries the only Retry action.
library;

/// The backend call behind the one Retry button.
enum RetryCall {
  /// PATCH /restore — re-queues the fetch of a fetch_failed vacancy.
  restore,

  /// reset, then POST /analyze — same as the old "Reset & Retry".
  resetAndAnalyze,

  /// POST /generate-cv (with the failed run's language when known).
  generateCv,

  /// POST /generate-cover.
  generateCover,

  /// POST /render-pdf {target}.
  renderPdf,
}

/// Statuses in which a run for this vacancy is already going on: a retry would
/// only get "already in progress" back, and the shown failure is from the
/// previous run.
const _runningStatuses = {
  'queued',
  'fetching',
  'analysis_queued',
  'analyzing',
  'cv_queued',
  'cv_generating',
  'cover_generating',
};

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

  /// Language of the failed CV run (en | uk | ...), when the backend knows it.
  final String? lang;

  const VacancyFailure({
    required this.kind,
    this.target,
    this.reason = '',
    this.at = '',
    required this.retry,
    this.code = 'unknown',
    this.lang,
  });

  /// Tolerant parse: a field of an unexpected type is treated as missing, so
  /// one odd row never breaks the whole vacancy list.
  static VacancyFailure? fromJson(Object? json) {
    if (json is! Map) return null;
    String? str(String key) {
      final v = json[key];
      return v is String && v.isNotEmpty ? v : null;
    }

    final kind = str('kind');
    if (kind == null) return null;
    return VacancyFailure(
      kind: kind,
      target: str('target'),
      reason: str('reason') ?? '',
      at: str('at') ?? '',
      retry: str('retry') ?? '',
      code: str('code') ?? 'unknown',
      lang: str('lang'),
    );
  }

  Map<String, dynamic> toJson() => {
    'kind': kind,
    'target': target,
    'reason': reason,
    'at': at,
    'retry': retry,
    'code': code,
    'lang': lang,
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

  /// The backend call behind Retry; null when it cannot be retried from here
  /// (an unknown action, or a PDF failure without a target document).
  RetryCall? get retryCall => switch (retry) {
    'fetch' => RetryCall.restore,
    'analyze' => RetryCall.resetAndAnalyze,
    'cv' => RetryCall.generateCv,
    'cover' => RetryCall.generateCover,
    'pdf' when target == 'cv' || target == 'cover' => RetryCall.renderPdf,
    _ => null,
  };

  /// Label of the one Retry button; null when there is no retry call.
  String? get retryLabel => switch (retryCall) {
    RetryCall.restore => 'Retry fetch',
    RetryCall.resetAndAnalyze => 'Retry analysis',
    RetryCall.generateCv => 'Retry CV',
    RetryCall.generateCover => 'Retry cover',
    RetryCall.renderPdf => 'Retry PDF',
    null => null,
  };

  /// No job description exists, so the JD view has nothing to show.
  bool get hidesJd => kind == 'fetch';

  /// A run for this vacancy is going on now (e.g. a retry was started): the
  /// failure shown is from the previous run and Retry must wait.
  static bool runInProgress(String? status) =>
      status != null && _runningStatuses.contains(status);
}
