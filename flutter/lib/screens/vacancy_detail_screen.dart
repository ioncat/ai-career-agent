import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';
import '../providers/vacancy_detail_provider.dart';
import '../widgets/fit_score_chip.dart';
import '../widgets/fit_dot_bar.dart';
import '../widgets/recommendation_chip.dart';

class VacancyDetailScreen extends ConsumerWidget {
  final int vacancyId;
  final String url;

  const VacancyDetailScreen({
    super.key,
    required this.vacancyId,
    required this.url,
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
            const Divider(height: 1),
            // Scrollable content
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Quick Scan
                    _QuickScanCard(p2: p2),
                    const SizedBox(height: 16),
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

class _ActionBar extends StatelessWidget {
  final int vacancyId;
  final String url;

  const _ActionBar({required this.vacancyId, required this.url});

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 52,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      color: Theme.of(context).colorScheme.surfaceContainerLow,
      child: Row(
        children: [
          FilledButton.icon(
            onPressed: () {},
            icon: const Icon(Icons.description_outlined, size: 16),
            label: const Text('Generate CV'),
          ),
          const SizedBox(width: 8),
          OutlinedButton(
            onPressed: () {},
            child: const Text('Decline'),
          ),
          const Spacer(),
          IconButton(
            icon: const Icon(Icons.open_in_new, size: 18),
            tooltip: 'Open JD',
            onPressed: url.isNotEmpty
                ? () => launchUrl(Uri.parse(url),
                      mode: LaunchMode.externalApplication)
                : null,
          ),
        ],
      ),
    );
  }
}

class _QuickScanCard extends StatelessWidget {
  final dynamic p2;

  const _QuickScanCard({required this.p2});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                FitDotBar(score: p2.fitScore),
                const Spacer(),
                FitScoreChip(score: p2.fitScore, large: true),
              ],
            ),
            const SizedBox(height: 12),
            RecommendationChip(
              recommendation: p2.recommendation,
              label: p2.recommendationLabel,
            ),
            const SizedBox(height: 8),
            Text(
              p2.category,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BarriersCard extends StatelessWidget {
  final dynamic p2;

  const _BarriersCard({required this.p2});

  @override
  Widget build(BuildContext context) {
    return _SectionCard(
      title: 'Barriers & Risks',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (p2.keyBarriers.isNotEmpty)
            _BulletList(
                items: p2.keyBarriers,
                icon: '⚠️',
                color: const Color(0xFFE65100)),
          if (p2.hiddenRisks.isNotEmpty) ...[
            const SizedBox(height: 8),
            _BulletList(
                items: p2.hiddenRisks,
                icon: '🔴',
                color: const Color(0xFFBA1A1A)),
          ],
          if (p2.warnings.isNotEmpty) ...[
            const SizedBox(height: 8),
            _BulletList(
                items: p2.warnings,
                icon: '💡',
                color: const Color(0xFF005DAC)),
          ],
        ],
      ),
    );
  }
}

class _BulletList extends StatelessWidget {
  final List<String> items;
  final String icon;
  final Color color;

  const _BulletList(
      {required this.items, required this.icon, required this.color});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: items
          .map((item) => Padding(
                padding: const EdgeInsets.only(bottom: 4),
                child: Text(
                  '$icon $item',
                  style: Theme.of(context)
                      .textTheme
                      .bodySmall
                      ?.copyWith(color: color),
                ),
              ))
          .toList(),
    );
  }
}

class _FitDimsTable extends StatelessWidget {
  final dynamic dims;

  const _FitDimsTable({required this.dims});

  @override
  Widget build(BuildContext context) {
    final rows = [
      ('Domain fit', dims.domainFit),
      ('Execution fit', dims.executionFit),
      ('Strategy fit', dims.strategyFit),
      ('Systems fit', dims.systemsFit),
      ('Stakeholder fit', dims.stakeholderFit),
      ('Overall fit', dims.overallFit),
    ];
    return Table(
      columnWidths: const {0: FlexColumnWidth(), 1: FixedColumnWidth(60)},
      children: rows
          .map((r) => TableRow(children: [
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Text(r.$1,
                      style: Theme.of(context).textTheme.bodySmall),
                ),
                Text('${r.$2.toStringAsFixed(1)}/10',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          fontWeight: FontWeight.w600,
                        )),
              ]))
          .toList(),
    );
  }
}

class _VacScoreTable extends StatelessWidget {
  final dynamic dims;

  const _VacScoreTable({required this.dims});

  @override
  Widget build(BuildContext context) {
    final rows = [
      ('Company tier', dims.companyTier, 4),
      ('Seniority', dims.seniority, 4),
      ('Market scope', dims.marketScope, 3),
      ('Company type', dims.companyType, 3),
      ('Stage fit', dims.companyStageFit, 3),
      ('Domain score', dims.domainScore, 5),
      ('Remote policy', dims.remotePolicy, 3),
      ('Compensation', dims.compensation, 3),
    ];
    return Table(
      columnWidths: const {0: FlexColumnWidth(), 1: FixedColumnWidth(60)},
      children: rows
          .map((r) => TableRow(children: [
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 3),
                  child: Text(r.$1,
                      style: Theme.of(context).textTheme.bodySmall),
                ),
                Text('${r.$2}/${r.$3}',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          fontWeight: FontWeight.w600,
                        )),
              ]))
          .toList(),
    );
  }
}

class _RoleBalanceBar extends StatelessWidget {
  final Map<String, int> balance;

  const _RoleBalanceBar({required this.balance});

  static const _colors = {
    'strategy': Color(0xFF1976D2),
    'discovery': Color(0xFF7B1FA2),
    'execution': Color(0xFF388E3C),
    'stakeholder': Color(0xFFF57C00),
    'operational': Color(0xFF757575),
  };

  @override
  Widget build(BuildContext context) {
    return Column(
      children: balance.entries.map((e) {
        final color = _colors[e.key.toLowerCase()] ?? const Color(0xFF757575);
        return Padding(
          padding: const EdgeInsets.only(bottom: 6),
          child: Row(
            children: [
              SizedBox(
                width: 100,
                child: Text(e.key,
                    style: Theme.of(context).textTheme.labelSmall),
              ),
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(3),
                  child: LinearProgressIndicator(
                    value: e.value / 100,
                    minHeight: 8,
                    backgroundColor: color.withOpacity(0.15),
                    valueColor: AlwaysStoppedAnimation<Color>(color),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text('${e.value}%',
                  style: Theme.of(context).textTheme.labelSmall),
            ],
          ),
        );
      }).toList(),
    );
  }
}

class _SectionCard extends StatelessWidget {
  final String title;
  final Widget child;

  const _SectionCard({required this.title, required this.child});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title,
                style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w600,
                    )),
            const SizedBox(height: 10),
            child,
          ],
        ),
      ),
    );
  }
}

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
    return Card(
      child: Column(
        children: [
          InkWell(
            onTap: () => setState(() => _expanded = !_expanded),
            borderRadius: BorderRadius.circular(8),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Text(widget.title,
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w600,
                          )),
                  const Spacer(),
                  Icon(_expanded ? Icons.expand_less : Icons.expand_more,
                      size: 18),
                ],
              ),
            ),
          ),
          AnimatedCrossFade(
            firstChild: const SizedBox.shrink(),
            secondChild: Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: widget.child,
            ),
            crossFadeState: _expanded
                ? CrossFadeState.showSecond
                : CrossFadeState.showFirst,
            duration: const Duration(milliseconds: 200),
          ),
        ],
      ),
    );
  }
}
