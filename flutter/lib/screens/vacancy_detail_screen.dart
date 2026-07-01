import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/vacancy.dart';
import '../providers/settings_provider.dart';
import '../providers/vacancy_detail_provider.dart';
import '../providers/vacancy_list_provider.dart';
import '../repositories/vacancy_repository.dart';
import '../widgets/fit_dot_bar.dart';
import '../widgets/recommendation_chip.dart';
import '../widgets/vac_score_badge.dart';

class VacancyDetailScreen extends ConsumerWidget {
  final int vacancyId;
  final String url;
  final VacancyListItem? vacancy;

  const VacancyDetailScreen({
    super.key,
    required this.vacancyId,
    required this.url,
    this.vacancy,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(vacancyDetailProvider(vacancyId));

    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: Text('Ошибка загрузки: $e',
            style: const TextStyle(color: Color(0xFFBA1A1A))),
      ),
      data: (analysis) {
        final p1 = analysis.p1;
        final p2 = analysis.p2;

        if (p2 == null) {
          return const Center(child: Text('Анализ ещё выполняется...'));
        }

        return Column(
          children: [
            // Sticky action bar
            _ActionBar(vacancyId: vacancyId, url: url),
            // Scrollable content
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Hero header
                    _VacancyHero(p1: p1, p2: p2, vacancy: vacancy),
                    const SizedBox(height: 24),
                    // Who they want
                    _SectionCard(
                      title: 'Who they want',
                      child: Text(p2.whoTheyWant,
                          style: Theme.of(context).textTheme.bodyMedium),
                    ),
                    const SizedBox(height: 16),
                    // Barriers
                    if (p2.keyBarriers.isNotEmpty ||
                        p2.hiddenRisks.isNotEmpty ||
                        p2.warnings.isNotEmpty)
                      _BarriersCard(p2: p2),
                    const SizedBox(height: 16),
                    // Fit dimensions
                    if (p2.fitDimensions != null)
                      _CollapsibleSection(
                        title: 'Fit Dimensions',
                        child: _FitDimsTable(dims: p2.fitDimensions!),
                      ),
                    if (p1 != null) ...[
                      const SizedBox(height: 16),
                      _CollapsibleSection(
                        title: 'VacScore Breakdown',
                        child: _VacScoreTable(dims: p1.vacscoreDims),
                      ),
                      const SizedBox(height: 16),
                      if (p1.roleBalance.isNotEmpty)
                        _CollapsibleSection(
                          title: 'Role Balance',
                          child: _RoleBalanceBar(balance: p1.roleBalance),
                        ),
                    ],
                    const SizedBox(height: 80),
                  ],
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _ActionBar extends ConsumerStatefulWidget {
  final int vacancyId;
  final String url;

  const _ActionBar({required this.vacancyId, required this.url});

  @override
  ConsumerState<_ActionBar> createState() => _ActionBarState();
}

class _ActionBarState extends ConsumerState<_ActionBar> {
  bool _loadingCv = false;
  bool _loadingDecline = false;

  VacancyRepository get _repo {
    final apiUrl = ref.read(settingsProvider).valueOrNull?.apiUrl ?? 'http://localhost:8080';
    return VacancyRepository(baseUrl: apiUrl);
  }

  Future<void> _generateCv() async {
    setState(() => _loadingCv = true);
    try {
      await _repo.generateCv(widget.vacancyId);
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('CV generation queued'), duration: Duration(seconds: 2)),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _loadingCv = false);
    }
  }

  Future<void> _decline() async {
    setState(() => _loadingDecline = true);
    try {
      await _repo.decline(widget.vacancyId);
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
        setState(() => _loadingDecline = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: cs.surfaceContainerLowest.withValues(alpha: 0.9),
        border: Border(
          bottom: BorderSide(color: cs.outlineVariant.withValues(alpha: 0.15)),
        ),
      ),
      child: Row(
        children: [
          const Spacer(),
          // Open JD
          if (widget.url.isNotEmpty)
            IconButton(
              icon: Icon(Icons.open_in_new, size: 18, color: cs.onSurfaceVariant),
              tooltip: 'Open JD',
              onPressed: () => launchUrl(
                Uri.parse(widget.url),
                mode: LaunchMode.externalApplication,
              ),
            ),
          const SizedBox(width: 4),
          // Decline
          OutlinedButton(
            onPressed: _loadingDecline ? null : _decline,
            style: OutlinedButton.styleFrom(
              side: BorderSide(color: cs.outlineVariant),
              foregroundColor: cs.onSurfaceVariant,
            ),
            child: _loadingDecline
                ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Decline'),
          ),
          const SizedBox(width: 8),
          // Generate CV — primary CTA
          FilledButton.icon(
            onPressed: _loadingCv ? null : _generateCv,
            icon: _loadingCv
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.description_outlined, size: 16),
            label: const Text('Generate CV'),
          ),
        ],
      ),
    );
  }
}

// ── Hero header — role icon + title + subtitle + chips + bento grid ───────────

class _VacancyHero extends StatelessWidget {
  final Phase1Data? p1;
  final Phase2Data p2;
  final VacancyListItem? vacancy;

  const _VacancyHero({required this.p1, required this.p2, this.vacancy});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final role    = p1?.role.isNotEmpty == true ? p1!.role : (vacancy?.role ?? '');
    final company = p1?.company.isNotEmpty == true ? p1!.company : (vacancy?.company ?? '');
    final category = p2.category;
    final publishedAt = vacancy?.publishedAt;

    // Subtitle: "Company • Category"
    final subtitleParts = [
      if (company.isNotEmpty) company,
      if (category.isNotEmpty) category,
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 24),
        // Icon + Title + Subtitle
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Company icon
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: cs.surfaceContainer,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: cs.outlineVariant.withValues(alpha: 0.3)),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.04),
                    blurRadius: 4,
                    offset: const Offset(0, 1),
                  ),
                ],
              ),
              child: Icon(Icons.code, color: cs.primary, size: 26),
            ),
            const SizedBox(width: 16),
            // Title + Subtitle
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    role,
                    style: Theme.of(context).textTheme.displaySmall?.copyWith(
                          fontSize: 28,
                          fontWeight: FontWeight.w700,
                          color: cs.onSurface,
                          height: 1.2,
                        ),
                  ),
                  if (subtitleParts.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Text(
                      subtitleParts.join(' • '),
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                            color: cs.onSurfaceVariant,
                            fontWeight: FontWeight.w400,
                          ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        // Chips row: recommendation + posted
        Wrap(
          spacing: 8,
          runSpacing: 6,
          children: [
            RecommendationChip(
              recommendation: p2.recommendation,
              label: p2.recommendationLabel,
            ),
            if (publishedAt != null)
              _PostedChip(publishedAt: publishedAt, cs: cs),
          ],
        ),
        const SizedBox(height: 24),
        // Bento grid
        _BentoGrid(p1: p1, p2: p2),
      ],
    );
  }
}

class _PostedChip extends StatelessWidget {
  final String publishedAt;
  final ColorScheme cs;

  const _PostedChip({required this.publishedAt, required this.cs});

  String _relativeTime() {
    try {
      final dt = DateTime.parse(publishedAt);
      final diff = DateTime.now().difference(dt);
      if (diff.inDays > 0) return '${diff.inDays}д назад';
      if (diff.inHours > 0) return '${diff.inHours}ч назад';
      if (diff.inMinutes > 0) return '${diff.inMinutes}м назад';
      return 'только что';
    } catch (_) {
      return publishedAt;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 28,
      padding: const EdgeInsets.symmetric(horizontal: 10),
      decoration: BoxDecoration(
        color: cs.surfaceContainer,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: cs.outlineVariant.withValues(alpha: 0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.schedule, size: 14, color: cs.onSurfaceVariant),
          const SizedBox(width: 4),
          Text(
            'Posted ${_relativeTime()}',
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: cs.onSurfaceVariant,
                ),
          ),
        ],
      ),
    );
  }
}

// ── Bento grid: Fit Score + VacScore + Category ───────────────────────────────

class _BentoGrid extends StatelessWidget {
  final Phase1Data? p1;
  final Phase2Data p2;

  const _BentoGrid({required this.p1, required this.p2});

  @override
  Widget build(BuildContext context) {
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Fit Score
          Expanded(child: _BentoCard(
            label: 'Overall Fit Score',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _BigScore(
                  value: p2.fitScore.toDouble(),
                  max: 10,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(height: 12),
                FitDotBar(score: p2.fitScore),
              ],
            ),
          )),
          const SizedBox(width: 12),
          // VacScore
          if (p1 != null)
            Expanded(child: _BentoCard(
              label: 'Vacancy Quality Score',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _BigScore(
                    value: p1!.vacancyScore,
                    max: 10,
                    color: Theme.of(context).colorScheme.onSurface,
                  ),
                  const SizedBox(height: 8),
                  VacScoreBadge(score: p1!.vacancyScore),
                  if (p1!.northStar.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(
                      p1!.northStar,
                      style: Theme.of(context).textTheme.labelMedium?.copyWith(
                            color: Theme.of(context).colorScheme.secondary,
                          ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ],
              ),
            )),
          const SizedBox(width: 12),
          // Category / Info
          Expanded(child: _BentoCard(
            label: 'Category',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: p2.category
                  .split('·')
                  .map((s) => s.trim())
                  .where((s) => s.isNotEmpty)
                  .map((s) => Padding(
                        padding: const EdgeInsets.only(bottom: 6),
                        child: Row(
                          children: [
                            Icon(Icons.check,
                                size: 16,
                                color: Theme.of(context).colorScheme.primary),
                            const SizedBox(width: 6),
                            Flexible(
                              child: Text(
                                s,
                                style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontSize: 13),
                              ),
                            ),
                          ],
                        ),
                      ))
                  .toList(),
            ),
          )),
        ],
      ),
    );
  }
}

class _BentoCard extends StatelessWidget {
  final String label;
  final Widget child;

  const _BentoCard({required this.label, required this.child});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cs.surfaceContainerLowest,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: cs.outlineVariant.withValues(alpha: 0.3)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 4,
            offset: const Offset(0, 1),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: cs.onSurfaceVariant,
                ),
          ),
          const SizedBox(height: 10),
          child,
        ],
      ),
    );
  }
}

class _BigScore extends StatelessWidget {
  final double value;
  final double max;
  final Color color;

  const _BigScore({required this.value, required this.max, required this.color});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.baseline,
      textBaseline: TextBaseline.alphabetic,
      children: [
        Text(
          value.toStringAsFixed(1),
          style: TextStyle(
            fontSize: 40,
            fontWeight: FontWeight.w700,
            color: color,
            height: 1.0,
          ),
        ),
        const SizedBox(width: 4),
        Text(
          '/ ${max.toInt()}',
          style: Theme.of(context).textTheme.titleSmall?.copyWith(
                color: Theme.of(context).colorScheme.secondary,
              ),
        ),
      ],
    );
  }
}

// ── Barriers & Risks ──────────────────────────────────────────────────────────

class _BarriersCard extends StatelessWidget {
  final Phase2Data p2;

  const _BarriersCard({required this.p2});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return _SectionCard(
      title: 'Barriers & Risks',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (p2.keyBarriers.isNotEmpty) ...[
            _BarrierGroup(
              label: 'Key Barriers',
              items: p2.keyBarriers,
              icon: Icons.warning_amber_rounded,
              iconColor: cs.error,
              bgColor: cs.errorContainer.withValues(alpha: 0.35),
            ),
          ],
          if (p2.hiddenRisks.isNotEmpty) ...[
            if (p2.keyBarriers.isNotEmpty) const SizedBox(height: 10),
            _BarrierGroup(
              label: 'Hidden Risks',
              items: p2.hiddenRisks,
              icon: Icons.block,
              iconColor: cs.onErrorContainer,
              bgColor: cs.errorContainer.withValues(alpha: 0.6),
            ),
          ],
          if (p2.warnings.isNotEmpty) ...[
            if (p2.keyBarriers.isNotEmpty || p2.hiddenRisks.isNotEmpty)
              const SizedBox(height: 10),
            _BarrierGroup(
              label: 'Warnings',
              items: p2.warnings,
              icon: Icons.info_outline,
              iconColor: cs.secondary,
              bgColor: cs.secondaryContainer.withValues(alpha: 0.4),
            ),
          ],
        ],
      ),
    );
  }
}

class _BarrierGroup extends StatelessWidget {
  final String label;
  final List<String> items;
  final IconData icon;
  final Color iconColor;
  final Color bgColor;

  const _BarrierGroup({
    required this.label,
    required this.items,
    required this.icon,
    required this.iconColor,
    required this.bgColor,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: cs.onSurfaceVariant,
                fontWeight: FontWeight.w600,
                letterSpacing: 0.5,
              ),
        ),
        const SizedBox(height: 6),
        ...items.map((item) => Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                decoration: BoxDecoration(
                  color: bgColor,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(icon, size: 14, color: iconColor),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        item,
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: cs.onSurface,
                            ),
                      ),
                    ),
                  ],
                ),
              ),
            )),
      ],
    );
  }
}

// ── Fit Dimensions ────────────────────────────────────────────────────────────

class _FitDimsTable extends StatelessWidget {
  final FitDimensions dims;

  const _FitDimsTable({required this.dims});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final rows = [
      ('Domain fit',      dims.domainFit),
      ('Execution fit',   dims.executionFit),
      ('Strategy fit',    dims.strategyFit),
      ('Systems fit',     dims.systemsFit),
      ('Stakeholder fit', dims.stakeholderFit),
      ('Overall fit',     dims.overallFit),
    ];
    return Column(
      children: rows.map((r) => _ScoreBar(
            label: r.$1,
            value: r.$2,
            max: 10,
            color: cs.primary,
          )).toList(),
    );
  }
}

// ── VacScore Breakdown ────────────────────────────────────────────────────────

class _VacScoreTable extends StatelessWidget {
  final VacScoreDims dims;

  const _VacScoreTable({required this.dims});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final rows = [
      ('Company tier',  dims.companyTier,      4),
      ('Seniority',     dims.seniority,        4),
      ('Market scope',  dims.marketScope,      3),
      ('Company type',  dims.companyType,      3),
      ('Stage fit',     dims.companyStageFit,  3),
      ('Domain score',  dims.domainScore,      5),
      ('Remote policy', dims.remotePolicy,     3),
      ('Compensation',  dims.compensation,     3),
    ];
    return Column(
      children: rows.map((r) => _ScoreBar(
            label: r.$1,
            value: r.$2.toDouble(),
            max: r.$3.toDouble(),
            color: cs.secondary,
          )).toList(),
    );
  }
}

// ── Shared score bar row ──────────────────────────────────────────────────────

class _ScoreBar extends StatelessWidget {
  final String label;
  final double value;
  final double max;
  final Color color;

  const _ScoreBar({
    required this.label,
    required this.value,
    required this.max,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          SizedBox(
            width: 116,
            child: Text(
              label,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: cs.onSurfaceVariant,
                  ),
            ),
          ),
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: max > 0 ? value / max : 0,
                minHeight: 6,
                backgroundColor: cs.surfaceContainerHighest,
                valueColor: AlwaysStoppedAnimation<Color>(color),
              ),
            ),
          ),
          const SizedBox(width: 10),
          SizedBox(
            width: 36,
            child: Text(
              value % 1 == 0
                  ? '${value.toInt()}/${ max.toInt()}'
                  : '${value.toStringAsFixed(1)}/${max.toInt()}',
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: cs.onSurface,
                    fontWeight: FontWeight.w600,
                  ),
              textAlign: TextAlign.end,
            ),
          ),
        ],
      ),
    );
  }
}

// ── Role Balance ──────────────────────────────────────────────────────────────

class _RoleBalanceBar extends StatelessWidget {
  final Map<String, int> balance;

  const _RoleBalanceBar({required this.balance});

  Color _colorForKey(String key, ColorScheme cs) {
    switch (key.toLowerCase()) {
      case 'strategy':    return cs.primary;
      case 'discovery':   return cs.tertiary;
      case 'execution':   return const Color(0xFF388E3C);
      case 'stakeholder': return cs.secondary;
      default:            return cs.outline;
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Column(
      children: balance.entries.map((e) {
        final color = _colorForKey(e.key, cs);
        return Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(
            children: [
              SizedBox(
                width: 116,
                child: Text(
                  e.key,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: cs.onSurfaceVariant,
                      ),
                ),
              ),
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: e.value / 100,
                    minHeight: 6,
                    backgroundColor: cs.surfaceContainerHighest,
                    valueColor: AlwaysStoppedAnimation<Color>(color),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              SizedBox(
                width: 36,
                child: Text(
                  '${e.value}%',
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                        color: cs.onSurface,
                        fontWeight: FontWeight.w600,
                      ),
                  textAlign: TextAlign.end,
                ),
              ),
            ],
          ),
        );
      }).toList(),
    );
  }
}

// ── Section card — bento style ────────────────────────────────────────────────

class _SectionCard extends StatelessWidget {
  final String title;
  final Widget child;

  const _SectionCard({required this.title, required this.child});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cs.surfaceContainerLowest,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: cs.outlineVariant.withValues(alpha: 0.3)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 4,
            offset: const Offset(0, 1),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: cs.onSurfaceVariant,
                ),
          ),
          const SizedBox(height: 12),
          child,
        ],
      ),
    );
  }
}

// ── Collapsible section — bento style ────────────────────────────────────────

class _CollapsibleSection extends StatefulWidget {
  final String title;
  final Widget child;
  final bool initiallyExpanded;

  const _CollapsibleSection({
    required this.title,
    required this.child,
    this.initiallyExpanded = false,
  });

  @override
  State<_CollapsibleSection> createState() => _CollapsibleSectionState();
}

class _CollapsibleSectionState extends State<_CollapsibleSection> {
  late bool _expanded;

  @override
  void initState() {
    super.initState();
    _expanded = widget.initiallyExpanded;
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      decoration: BoxDecoration(
        color: cs.surfaceContainerLowest,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: cs.outlineVariant.withValues(alpha: 0.3)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 4,
            offset: const Offset(0, 1),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InkWell(
            onTap: () => setState(() => _expanded = !_expanded),
            borderRadius: BorderRadius.circular(16),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
              child: Row(
                children: [
                  Text(
                    widget.title,
                    style: Theme.of(context).textTheme.labelMedium?.copyWith(
                          color: cs.onSurfaceVariant,
                        ),
                  ),
                  const Spacer(),
                  Icon(
                    _expanded ? Icons.expand_less : Icons.expand_more,
                    size: 16,
                    color: cs.onSurfaceVariant,
                  ),
                ],
              ),
            ),
          ),
          AnimatedCrossFade(
            firstChild: const SizedBox.shrink(),
            secondChild: Column(
              children: [
                Divider(
                  height: 1,
                  color: cs.outlineVariant.withValues(alpha: 0.3),
                ),
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: widget.child,
                ),
              ],
            ),
            crossFadeState: _expanded
                ? CrossFadeState.showSecond
                : CrossFadeState.showFirst,
            duration: const Duration(milliseconds: 180),
          ),
        ],
      ),
    );
  }
}
