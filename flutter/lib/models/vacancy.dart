List<String> _parseStringList(dynamic raw) {
  if (raw == null) return [];
  if (raw is List) return raw.map((e) => '$e').toList();
  if (raw is String && raw.isNotEmpty) return [raw];
  return [];
}

// vacancies.tags is a raw comma-separated DB column (e.g. "deftech,ai"),
// unlike role_tags/key_barriers which arrive as JSON arrays from analysis_json.
List<String> _parseTags(dynamic raw) {
  if (raw is! String || raw.isEmpty) return [];
  return raw.split(',').map((t) => t.trim()).where((t) => t.isNotEmpty).toList();
}

class VacancyListItem {
  final int id;
  final String role;
  final String company;
  // Public company profile-page website, fetched off the critical path and
  // cached per company — often absent right after a vacancy first arrives,
  // backfills a few seconds later (2026-08-12).
  final String? companyWebsite;
  final String site;
  final String url;
  final String status;
  final int? fitScore;
  final double? vacancyScore;
  final String? recommendation;
  final String? recommendationLabel;
  final String? category;
  final String? publishedAt;
  final String? updatedAt;
  final List<String> keyBarriers;
  final String? analysisError;
  final bool starred;
  final bool applied;
  // When applied was actually toggled on — Applied folder sorts by this,
  // not publishedAt/updatedAt (2026-08-13). Null when never applied.
  final String? appliedAt;
  final String? salary;
  final List<String> tags;
  final List<String> roleTags;
  final int? duplicateOf;
  final String? republishedAt;
  final String? folderPath;
  final String stage;
  final bool blockerFlag;
  final List<String> blockerReasons;
  // Distinguishes "checked, came back clean" from "never checked" — both look
  // identical via blockerFlag=false alone (gap found 2026-07-17, vacancy #716:
  // a finished, clean check produced zero visible UI change).
  final bool blockerChecked;
  // Which pre-filter phase set blockerFlag: 'title' (Stage 1, deterministic —
  // no LLM) | 'content' (Stage 2, LLM-judged) | null (not blocked / never
  // checked). A real field, not string-matching blockerReasons for a
  // "title:" prefix (considered and rejected as fragile, 2026-07-24).
  final String? blockerStage;

  const VacancyListItem({
    required this.id,
    required this.role,
    required this.company,
    this.companyWebsite,
    required this.site,
    required this.url,
    required this.status,
    this.fitScore,
    this.vacancyScore,
    this.recommendation,
    this.recommendationLabel,
    this.category,
    this.publishedAt,
    this.updatedAt,
    this.keyBarriers = const [],
    this.analysisError,
    this.starred = false,
    this.applied = false,
    this.appliedAt,
    this.salary,
    this.tags = const [],
    this.roleTags = const [],
    this.duplicateOf,
    this.republishedAt,
    this.folderPath,
    this.stage = 'inbox',
    this.blockerFlag = false,
    this.blockerReasons = const [],
    this.blockerChecked = false,
    this.blockerStage,
  });

  factory VacancyListItem.fromJson(Map<String, dynamic> json) {
    return VacancyListItem(
      id: json['id'] as int,
      // 'role' from p1 analysis; fallback to 'title' from DB row for unanalyzed vacancies
      role: json['role'] as String? ?? json['title'] as String? ?? '',
      company: json['company'] as String? ?? '',
      companyWebsite: json['company_website'] as String?,
      site: json['site'] as String? ?? '',
      url: json['url'] as String? ?? '',
      status: json['status'] as String? ?? '',
      fitScore: json['fit_score'] as int?,
      vacancyScore: (json['vacancy_score'] as num?)?.toDouble(),
      recommendation: json['recommendation'] as String?,
      recommendationLabel: json['recommendation_label'] as String?,
      category: json['category'] as String?,
      publishedAt: json['published_at'] as String?,
      updatedAt: json['updated_at'] as String?,
      keyBarriers: _parseStringList(json['key_barriers']),
      analysisError: json['analysis_error'] as String?,
      starred: json['starred'] as bool? ?? false,
      applied: json['applied'] as bool? ?? false,
      appliedAt: json['applied_at'] as String?,
      salary: json['salary'] as String?,
      tags: _parseTags(json['tags']),
      roleTags: _parseStringList(json['role_tags']),
      duplicateOf: json['duplicate_of'] as int?,
      republishedAt: json['republished_at'] as String?,
      folderPath: json['folder_path'] as String?,
      stage: json['stage'] as String? ?? 'inbox',
      blockerFlag: json['blocker_flag'] as bool? ?? false,
      blockerReasons: _parseStringList(json['blocker_reasons']),
      blockerChecked: json['blocker_checked'] as bool? ?? false,
      blockerStage: json['blocker_stage'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'role': role,
        'company': company,
        'company_website': companyWebsite,
        'site': site,
        'url': url,
        'status': status,
        'fit_score': fitScore,
        'vacancy_score': vacancyScore,
        'recommendation': recommendation,
        'recommendation_label': recommendationLabel,
        'category': category,
        'published_at': publishedAt,
        'updated_at': updatedAt,
        'key_barriers': keyBarriers,
        'analysis_error': analysisError,
        'starred': starred,
        'applied': applied,
        'applied_at': appliedAt,
        'salary': salary,
        'tags': tags.join(','),
        'role_tags': roleTags,
        'duplicate_of': duplicateOf,
        'republished_at': republishedAt,
        'stage': stage,
        'blocker_flag': blockerFlag,
        'blocker_reasons': blockerReasons,
        'blocker_checked': blockerChecked,
        'blocker_stage': blockerStage,
      };
}

class VacancyAnalysis {
  final Phase1Data? p1;
  final Phase2Data? p2;
  // Real Phase 2 completion time (pipeline_runs), NOT vacancy.updatedAt —
  // updatedAt is bumped by unrelated writes (applied/starred toggle, salary
  // edit, republish bump, dedup, ...) and falsely implies re-analysis.
  // Found live 2026-08-11, vacancy #597.
  final String? analyzedAt;

  const VacancyAnalysis({this.p1, this.p2, this.analyzedAt});

  factory VacancyAnalysis.fromJson(Map<String, dynamic> json) {
    return VacancyAnalysis(
      p1: json['p1'] != null
          ? Phase1Data.fromJson(json['p1'] as Map<String, dynamic>)
          : null,
      p2: json['p2'] != null
          ? Phase2Data.fromJson(json['p2'] as Map<String, dynamic>)
          : null,
      analyzedAt: json['analyzed_at'] as String?,
    );
  }
}

class Phase1Data {
  final String role;
  final String company;
  final String northStar;
  final String primaryArchetype;
  final String companyType;
  final double vacancyScore;
  final Map<String, int> roleBalance;
  final String dominantCulture;
  final VacScoreDims vacscoreDims;

  const Phase1Data({
    required this.role,
    required this.company,
    required this.northStar,
    required this.primaryArchetype,
    required this.companyType,
    required this.vacancyScore,
    required this.roleBalance,
    required this.dominantCulture,
    required this.vacscoreDims,
  });

  factory Phase1Data.fromJson(Map<String, dynamic> json) {
    return Phase1Data(
      role: json['role'] as String? ?? '',
      company: json['company'] as String? ?? '',
      northStar: json['north_star'] as String? ?? '',
      primaryArchetype: json['primary_archetype'] as String? ?? '',
      companyType: json['company_type'] as String? ?? '',
      vacancyScore: (json['vacancy_score'] as num?)?.toDouble() ?? 0.0,
      roleBalance: (json['role_balance'] as Map<String, dynamic>?)
              ?.map((k, v) => MapEntry(k, (v as num).toInt())) ??
          {},
      dominantCulture: json['dominant_culture'] as String? ?? '',
      vacscoreDims: json['vacscore_dims'] != null
          ? VacScoreDims.fromJson(
              json['vacscore_dims'] as Map<String, dynamic>)
          : const VacScoreDims(),
    );
  }
}

class VacScoreDims {
  final int companyTier;
  final int seniority;
  final int marketScope;
  final int companyType;
  final int companyStageFit;
  final int domainScore;
  final int remotePolicy;
  final int compensation;

  const VacScoreDims({
    this.companyTier = 0,
    this.seniority = 0,
    this.marketScope = 0,
    this.companyType = 0,
    this.companyStageFit = 0,
    this.domainScore = 0,
    this.remotePolicy = 0,
    this.compensation = 0,
  });

  factory VacScoreDims.fromJson(Map<String, dynamic> json) {
    return VacScoreDims(
      companyTier: json['company_tier'] as int? ?? 0,
      seniority: json['seniority'] as int? ?? 0,
      marketScope: json['market_scope'] as int? ?? 0,
      companyType: json['company_type'] as int? ?? 0,
      companyStageFit: json['company_stage_fit'] as int? ?? 0,
      domainScore: json['domain_score'] as int? ?? 0,
      remotePolicy: json['remote_policy'] as int? ?? 0,
      compensation: json['compensation'] as int? ?? 0,
    );
  }
}

class Phase2Data {
  final int fitScore;
  final String recommendation;
  final String recommendationLabel;
  final String category;
  final String whoTheyWant;
  final List<String> keyBarriers;
  final List<String> hiddenRisks;
  final List<String> warnings;
  final List<String> whyApply;
  final List<String> whyNotApply;
  final FitDimensions? fitDimensions;

  const Phase2Data({
    required this.fitScore,
    required this.recommendation,
    required this.recommendationLabel,
    required this.category,
    required this.whoTheyWant,
    this.keyBarriers = const [],
    this.hiddenRisks = const [],
    this.warnings = const [],
    this.whyApply = const [],
    this.whyNotApply = const [],
    this.fitDimensions,
  });

  factory Phase2Data.fromJson(Map<String, dynamic> json) {
    return Phase2Data(
      fitScore: json['fit_score'] as int? ?? 0,
      recommendation: json['recommendation'] as String? ?? '',
      recommendationLabel: json['recommendation_label'] as String? ?? '',
      category: json['category'] as String? ?? '',
      whoTheyWant: json['who_they_want'] as String? ?? '',
      keyBarriers: _parseStringList(json['key_barriers']),
      hiddenRisks: _parseStringList(json['hidden_risks']),
      warnings: _parseStringList(json['warnings']),
      whyApply: _parseStringList(json['why_apply']),
      whyNotApply: _parseStringList(json['why_not_apply']),
      fitDimensions: json['fit_dimensions'] != null
          ? FitDimensions.fromJson(
              json['fit_dimensions'] as Map<String, dynamic>)
          : null,
    );
  }
}

class VacancyCv {
  final String? cvMd;
  final String? coverMd;

  const VacancyCv({this.cvMd, this.coverMd});

  bool get hasCv => cvMd != null && cvMd!.isNotEmpty;
  bool get hasCover => coverMd != null && coverMd!.isNotEmpty;

  factory VacancyCv.fromJson(Map<String, dynamic> json) {
    return VacancyCv(
      cvMd: json['cv_md'] as String?,
      coverMd: json['cover_md'] as String?,
    );
  }
}

class FitDimensions {
  final double domainFit;
  final double executionFit;
  final double strategyFit;
  final double systemsFit;
  final double stakeholderFit;
  final double overallFit;

  const FitDimensions({
    required this.domainFit,
    required this.executionFit,
    required this.strategyFit,
    required this.systemsFit,
    required this.stakeholderFit,
    required this.overallFit,
  });

  factory FitDimensions.fromJson(Map<String, dynamic> json) {
    return FitDimensions(
      domainFit: (json['domain_fit'] as num?)?.toDouble() ?? 0.0,
      executionFit: (json['execution_fit'] as num?)?.toDouble() ?? 0.0,
      strategyFit: (json['strategy_fit'] as num?)?.toDouble() ?? 0.0,
      systemsFit: (json['systems_fit'] as num?)?.toDouble() ?? 0.0,
      stakeholderFit: (json['stakeholder_fit'] as num?)?.toDouble() ?? 0.0,
      overallFit: (json['overall_fit'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

// ── Pipeline run entry ───────────────────────────────────────────────────────

class PipelineRun {
  final String phase;
  final String status;
  final String? errorMessage;
  final String? startedAt;
  final int? durationMs;

  const PipelineRun({
    required this.phase,
    required this.status,
    this.errorMessage,
    this.startedAt,
    this.durationMs,
  });

  factory PipelineRun.fromJson(Map<String, dynamic> json) {
    return PipelineRun(
      phase: json['phase'] as String? ?? '',
      status: json['status'] as String? ?? '',
      errorMessage: json['error_message'] as String?,
      startedAt: json['started_at'] as String?,
      durationMs: json['duration_ms'] as int?,
    );
  }
}

// ── Activity log entry ────────────────────────────────────────────────────────

class ActivityEntry {
  final String phase;
  final String provider;
  final String model;
  final String thinkingEffort;
  final int elapsedMs;
  final int inputTokens;
  final int outputTokens;
  final int cacheReadTokens;
  final double costUsd;
  final String createdAt;

  const ActivityEntry({
    required this.phase,
    required this.provider,
    required this.model,
    required this.thinkingEffort,
    required this.elapsedMs,
    required this.inputTokens,
    required this.outputTokens,
    required this.cacheReadTokens,
    required this.costUsd,
    required this.createdAt,
  });

  factory ActivityEntry.fromJson(Map<String, dynamic> json) {
    return ActivityEntry(
      phase: json['phase'] as String? ?? '',
      provider: json['provider'] as String? ?? 'claude_api',
      model: json['model'] as String? ?? '',
      thinkingEffort: json['thinking_effort'] as String? ?? '',
      elapsedMs: json['elapsed_ms'] as int? ?? 0,
      inputTokens: json['input_tokens'] as int? ?? 0,
      outputTokens: json['output_tokens'] as int? ?? 0,
      cacheReadTokens: json['cache_read_tokens'] as int? ?? 0,
      costUsd: (json['cost_usd'] as num?)?.toDouble() ?? 0.0,
      createdAt: json['created_at'] as String? ?? '',
    );
  }
}
