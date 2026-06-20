class VacancyListItem {
  final int id;
  final String role;
  final String company;
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

  const VacancyListItem({
    required this.id,
    required this.role,
    required this.company,
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
  });

  factory VacancyListItem.fromJson(Map<String, dynamic> json) {
    return VacancyListItem(
      id: json['id'] as int,
      role: json['role'] as String? ?? '',
      company: json['company'] as String? ?? '',
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
      keyBarriers: (json['key_barriers'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
    );
  }
}

class VacancyAnalysis {
  final Phase1Data? p1;
  final Phase2Data? p2;

  const VacancyAnalysis({this.p1, this.p2});

  factory VacancyAnalysis.fromJson(Map<String, dynamic> json) {
    return VacancyAnalysis(
      p1: json['p1'] != null
          ? Phase1Data.fromJson(json['p1'] as Map<String, dynamic>)
          : null,
      p2: json['p2'] != null
          ? Phase2Data.fromJson(json['p2'] as Map<String, dynamic>)
          : null,
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
    this.fitDimensions,
  });

  factory Phase2Data.fromJson(Map<String, dynamic> json) {
    return Phase2Data(
      fitScore: json['fit_score'] as int? ?? 0,
      recommendation: json['recommendation'] as String? ?? '',
      recommendationLabel: json['recommendation_label'] as String? ?? '',
      category: json['category'] as String? ?? '',
      whoTheyWant: json['who_they_want'] as String? ?? '',
      keyBarriers: (json['key_barriers'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      hiddenRisks: (json['hidden_risks'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      warnings: (json['warnings'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
      fitDimensions: json['fit_dimensions'] != null
          ? FitDimensions.fromJson(
              json['fit_dimensions'] as Map<String, dynamic>)
          : null,
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
