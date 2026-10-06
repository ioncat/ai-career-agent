import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/settings_provider.dart';
import '../models/vacancy.dart';
import '../repositories/vacancy_repository.dart';
import '../utils/date_range.dart';

/// Primary-tag distribution across all vacancies. Tags are stored
/// non-exclusive in the DB (a vacancy can carry several, e.g. igaming +
/// mobile — see core/vacancy_tags.py), but this screen picks one "primary"
/// tag per vacancy via _kPriority so the chart sums to the total instead of
/// overlapping — a clean single picture of what the market is mostly made
/// of, which is what this screen is for.
// Mirrors core/vacancy_tags.py PRIORITY — kept as plain Dart here since this
// screen can't import the Python taxonomy module directly. Update alongside
// any change to that list.
//
// Fixed 2026-09-08: this list had drifted out of sync with the Python
// source — 'healthtech' (added there 2026-09-05) was missing here entirely,
// silently falling through to the generic tags.first fallback in
// _primaryTag() instead of following its intended priority position. Added
// 'b2c' (new 2026-09-08 category) in the same fix.
const _kPriority = [
  'deftech', 'igaming', 'fintech', 'healthtech', 'studio', 'mobile', 'b2c', 'b2b_saas', 'outsourcing',
];

String? _primaryTag(List<String> tags) {
  final tagSet = tags.toSet();
  for (final cat in _kPriority) {
    if (tagSet.contains(cat)) return cat;
  }
  return tags.isNotEmpty ? tags.first : null;
}

/// Counts for the summary cards at the top of the screen (2026-10-06).
/// "Analyzed" = ever analyzed: the vacancy carries a Phase 2 fit score, in
/// any status (analyzed, CV/cover ready, applied, declined after analysis) —
/// not just the ones currently sitting in the Analyzed folder, which would
/// shrink as vacancies move on. "Applied" = the `applied` flag, the same set
/// the Applied chart below uses.
///
/// `period` runs from the earliest to the latest recorded date across BOTH
/// metrics (analysis: `analyzedAt` from pipeline_runs; applied: `appliedAt`),
/// so it covers both even when their own ranges differ. Vacancies counted but
/// missing their date are reported in `*Undated` so the UI can say the period
/// does not cover them.
typedef AnalysisCounts = ({
  int analyzed,
  int applied,
  int appliedAnalyzed,
  ({DateTime from, DateTime to})? period,
  int analyzedUndated,
  int appliedUndated,
});

@visibleForTesting
AnalysisCounts analysisCounts(List<VacancyListItem> vacancies) {
  var analyzed = 0;
  var applied = 0;
  var appliedAnalyzed = 0;
  var analyzedUndated = 0;
  var appliedUndated = 0;
  final analyzedDates = <String?>[];
  final appliedDates = <String?>[];
  for (final v in vacancies) {
    final isAnalyzed = v.fitScore != null;
    if (isAnalyzed) {
      analyzed++;
      analyzedDates.add(v.analyzedAt);
      if (v.analyzedAt == null) analyzedUndated++;
    }
    if (v.applied) {
      applied++;
      appliedDates.add(v.appliedAt);
      if (v.appliedAt == null) appliedUndated++;
      if (isAnalyzed) appliedAnalyzed++;
    }
  }
  return (
    analyzed: analyzed,
    applied: applied,
    appliedAnalyzed: appliedAnalyzed,
    period: rangeOfBackendTimes([...analyzedDates, ...appliedDates]),
    analyzedUndated: analyzedUndated,
    appliedUndated: appliedUndated,
  );
}

String? _rangeText(({DateTime from, DateTime to})? r) =>
    r == null ? null : formatDateRange(r.from, r.to);

String _undatedNote(int n, String what) => n == 0
    ? ''
    : ' $n $what ${n == 1 ? 'has' : 'have'} no recorded date and ${n == 1 ? 'is' : 'are'} not in the range.';

class AnalyticsScreen extends ConsumerStatefulWidget {
  const AnalyticsScreen({super.key});

  @override
  ConsumerState<AnalyticsScreen> createState() => _AnalyticsScreenState();
}

class _AnalyticsScreenState extends ConsumerState<AnalyticsScreen> {
  bool _loaded = false;
  bool _loading = false;
  Object? _error;
  Map<String, int> _primaryCounts = {};
  int _total = 0;
  int _untagged = 0;
  // Same primary-tag slice, but only vacancies actually applied to (2026-08-24)
  // — "where did my CVs actually go", not just "what's the market made of".
  Map<String, int> _appliedCounts = {};
  int _appliedTotal = 0;
  int _appliedUntagged = 0;
  AnalysisCounts _counts = analysisCounts(const []);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_loaded && !_loading) {
      _load();
    }
  }

  Future<void> _load() async {
    final settings = ref.read(settingsProvider).valueOrNull;
    if (settings == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final repo = VacancyRepository(baseUrl: settings.apiUrl);
      final vacancies = await repo.listVacancies(limit: 5000);
      final primaryCounts = <String, int>{};
      var untagged = 0;
      final appliedCounts = <String, int>{};
      var appliedUntagged = 0;
      var appliedTotal = 0;
      for (final v in vacancies) {
        final primary = _primaryTag(v.tags);
        if (primary == null) {
          untagged++;
        } else {
          primaryCounts[primary] = (primaryCounts[primary] ?? 0) + 1;
        }
        if (v.applied) {
          appliedTotal++;
          if (primary == null) {
            appliedUntagged++;
          } else {
            appliedCounts[primary] = (appliedCounts[primary] ?? 0) + 1;
          }
        }
      }
      final counts = analysisCounts(vacancies);
      if (!mounted) return;
      setState(() {
        _counts = counts;
        _primaryCounts = primaryCounts;
        _total = vacancies.length;
        _untagged = untagged;
        _appliedCounts = appliedCounts;
        _appliedTotal = appliedTotal;
        _appliedUntagged = appliedUntagged;
        _loaded = true;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(32),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1100),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('Analytics', style: Theme.of(context).textTheme.headlineSmall),
                  IconButton(
                    tooltip: 'Refresh',
                    icon: const Icon(Icons.refresh),
                    onPressed: _loading ? null : _load,
                  ),
                ],
              ),
              const SizedBox(height: 24),
              if (_loading && !_loaded)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 40),
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (_error != null)
                Text(
                  'Failed to load: $_error',
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                )
              else ...[
                const _SectionTitle('Overview'),
                const SizedBox(height: 4),
                Text(
                  'How many vacancies were analyzed and applied to, and over what period.',
                  style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant),
                ),
                const SizedBox(height: 12),
                _StatsPanel(
                  period: _rangeText(_counts.period),
                  periodTooltip: 'From the first to the last analysis or application, '
                      'with the time span in brackets.'
                      '${_undatedNote(_counts.analyzedUndated, 'analyzed vacancies')}'
                      '${_undatedNote(_counts.appliedUndated, 'applied vacancies')}',
                  children: [
                    _StatCard(
                      label: 'Analyzed',
                      value: _counts.analyzed,
                      caption: 'of $_total vacancies seen',
                      tooltip: 'Vacancies that went through analysis (have a fit score), '
                          'in any status — including ones already applied to or declined.',
                    ),
                    _StatCard(
                      label: 'Applied',
                      value: _appliedTotal,
                      caption: _counts.analyzed == 0
                          ? 'no analyzed vacancies yet'
                          : '${(_counts.appliedAnalyzed / _counts.analyzed * 100).toStringAsFixed(0)}% of analyzed',
                      tooltip: 'Vacancies marked Applied. The percentage counts only applied '
                          'vacancies that were analyzed, relative to all analyzed ones.',
                    ),
                  ],
                ),
                const SizedBox(height: 32),
                ChartsRow(
                  left: _ChartSection(
                    title: 'Market',
                    subtitle: 'Every vacancy seen — what the market is mostly made of.',
                    chart: TagChart(
                      tagCounts: _primaryCounts,
                      total: _total,
                      untagged: _untagged,
                    ),
                  ),
                  right: _ChartSection(
                    title: 'Applied',
                    subtitle: 'Same slice, only vacancies actually applied to — where the CVs went.',
                    chart: TagChart(
                      tagCounts: _appliedCounts,
                      total: _appliedTotal,
                      untagged: _appliedUntagged,
                      emptyMessage: 'No applications yet.',
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// Section heading — larger and bolder than the captions around it so the
/// three blocks (Overview, Market, Applied) are easy to tell apart.
class _SectionTitle extends StatelessWidget {
  final String text;

  const _SectionTitle(this.text);

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
    );
  }
}

class _ChartSection extends StatelessWidget {
  final String title;
  final String subtitle;
  final Widget chart;

  const _ChartSection({required this.title, required this.subtitle, required this.chart});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _SectionTitle(title),
        const SizedBox(height: 4),
        Text(
          subtitle,
          style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant),
        ),
        const SizedBox(height: 16),
        chart,
      ],
    );
  }
}

/// Two chart sections side by side with a clearly visible vertical divider
/// between them; below [_kSideBySideMinWidth] they stack, separated by a
/// horizontal divider, so nothing is squeezed on a narrow window.
const _kSideBySideMinWidth = 760.0;

@visibleForTesting
class ChartsRow extends StatelessWidget {
  final Widget left;
  final Widget right;

  const ChartsRow({super.key, required this.left, required this.right});

  @override
  Widget build(BuildContext context) {
    final line = Theme.of(context).colorScheme.outline.withValues(alpha: 0.6);
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth < _kSideBySideMinWidth) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              left,
              const SizedBox(height: 24),
              Divider(key: const Key('charts-divider'), thickness: 2, height: 2, color: line),
              const SizedBox(height: 24),
              right,
            ],
          );
        }
        return IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: left),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: VerticalDivider(
                  key: const Key('charts-divider'),
                  thickness: 2,
                  width: 2,
                  color: line,
                ),
              ),
              Expanded(child: right),
            ],
          ),
        );
      },
    );
  }
}

/// Frame around the summary cards: the shared period on top, the cards side
/// by side below. The period is shown once because it covers both metrics.
class _StatsPanel extends StatelessWidget {
  final String? period;
  final String periodTooltip;
  final List<Widget> children;

  const _StatsPanel({
    required this.period,
    required this.periodTooltip,
    required this.children,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        border: Border.all(color: cs.outlineVariant),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Tooltip(
            message: periodTooltip,
            waitDuration: const Duration(milliseconds: 300),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('Period', style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                const SizedBox(width: 10),
                Flexible(
                  child: Text(
                    period ?? 'no dated analyses or applications yet',
                    key: const Key('stats-period'),
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (var i = 0; i < children.length; i++) ...[
                if (i > 0) const SizedBox(width: 16),
                Expanded(child: children[i]),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  final String label;
  final int value;
  final String caption;
  final String tooltip;

  const _StatCard({
    required this.label,
    required this.value,
    required this.caption,
    required this.tooltip,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Tooltip(
      message: tooltip,
      waitDuration: const Duration(milliseconds: 300),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: cs.surfaceContainerHighest.withValues(alpha: 0.5),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
            const SizedBox(height: 4),
            Text(
              '$value',
              key: Key('stat-$label'),
              style: const TextStyle(fontSize: 32, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 2),
            Text(caption, style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
          ],
        ),
      ),
    );
  }
}

@visibleForTesting
class TagChart extends StatelessWidget {
  final Map<String, int> tagCounts;
  final int total;
  final int untagged;
  final String emptyMessage;

  const TagChart({
    super.key,
    required this.tagCounts,
    required this.total,
    required this.untagged,
    this.emptyMessage = 'No vacancies loaded yet.',
  });

  // 9 colors — one per _kPriority tag, so all bars stay visually distinct
  // (was 8, one short since the healthtech/b2c additions, 2026-09-08).
  static const _palette = [
    Color(0xFF6750A4), Color(0xFF386A20), Color(0xFF8C4A2F),
    Color(0xFF006874), Color(0xFF984061), Color(0xFF7C5800),
    Color(0xFF4A6363), Color(0xFF5C5D72), Color(0xFF8B5000),
  ];

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;

    if (total == 0) {
      return Text(emptyMessage, style: TextStyle(color: cs.onSurfaceVariant));
    }

    final entries = tagCounts.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final maxCount = entries.isEmpty
        ? 1
        : [entries.first.value, untagged].reduce((a, b) => a > b ? a : b);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '$total vacancies · one primary tag each, bars sum to $total',
          style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
        ),
        const SizedBox(height: 20),
        for (var i = 0; i < entries.length; i++) ...[
          _BarRow(
            label: entries[i].key,
            count: entries[i].value,
            total: total,
            maxCount: maxCount,
            color: _palette[i % _palette.length],
          ),
          const SizedBox(height: 10),
        ],
        if (untagged > 0) ...[
          const SizedBox(height: 6),
          Divider(color: cs.outlineVariant.withValues(alpha: 0.3)),
          const SizedBox(height: 16),
          _BarRow(
            label: 'untagged',
            count: untagged,
            total: total,
            maxCount: maxCount,
            color: cs.onSurfaceVariant.withValues(alpha: 0.35),
          ),
        ],
        const SizedBox(height: 6),
        Divider(color: cs.outlineVariant.withValues(alpha: 0.3)),
        const SizedBox(height: 10),
        _TotalRow(total: total),
      ],
    );
  }
}

/// Sum line under the bars, laid out on the same columns as _BarRow (110 px
/// label, flexible bar area, 80 px count) so the number lines up with the
/// counts above it.
class _TotalRow extends StatelessWidget {
  final int total;

  const _TotalRow({required this.total});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Row(
      children: [
        SizedBox(
          width: 96,
          child: Tooltip(
            message: 'Sum of all bars above — each vacancy is counted once, '
                'under its primary tag (or untagged).',
            waitDuration: const Duration(milliseconds: 300),
            child: const Text(
              'Total',
              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
            ),
          ),
        ),
        const Expanded(child: SizedBox.shrink()),
        const SizedBox(width: 10),
        SizedBox(
          width: 80,
          child: Text(
            '$total (100%)',
            key: const Key('chart-total'),
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: cs.onSurface),
            textAlign: TextAlign.right,
          ),
        ),
      ],
    );
  }
}

// Mirrors the category intent from core/vacancy_tags.py — kept as plain
// text here since Dart can't import the Python taxonomy module directly.
// Update alongside any change to that file's _TAXONOMY comments.
const _kTagDescriptions = {
  'igaming': 'Gambling/betting products: casino, sportsbook, betting platforms.',
  'deftech': 'Defense/military technology: UAV, drones, defense systems.',
  'mobile': 'Mobile-native product: iOS/Android app.',
  'outsourcing': 'Client-services company (agency/outstaff/consulting) building for others, not its own product.',
  'b2b_saas': 'B2B SaaS platform or product.',
  'studio': 'Game development studio building its own games.',
  'fintech': 'Financial technology: payments, banking, crypto.',
  'healthtech': 'Healthcare-related product: telehealth, EHR/EMR, patient portal.',
  'b2c': 'Consumer-facing product: B2C, D2C, direct-to-consumer.',
  'untagged': 'JD text didn\'t match any known category keyword.',
};

class _BarRow extends StatelessWidget {
  final String label;
  final int count;
  final int total;
  final int maxCount;
  final Color color;

  const _BarRow({
    required this.label,
    required this.count,
    required this.total,
    required this.maxCount,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final pct = total == 0 ? 0.0 : count / total * 100;
    final fraction = maxCount == 0 ? 0.0 : count / maxCount;

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        SizedBox(
          width: 96,
          child: Tooltip(
            message: _kTagDescriptions[label] ?? label,
            waitDuration: const Duration(milliseconds: 300),
            child: Text(
              label,
              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
        Expanded(
          // FractionallySizedBox, not LayoutBuilder: ChartsRow wraps the charts
          // in IntrinsicHeight (full-height divider), which throws on a
          // LayoutBuilder anywhere below it.
          child: Stack(
            children: [
              Container(
                height: 22,
                decoration: BoxDecoration(
                  color: cs.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
              FractionallySizedBox(
                widthFactor: fraction.clamp(0.02, 1.0),
                alignment: Alignment.centerLeft,
                child: Container(
                  height: 22,
                  decoration: BoxDecoration(
                    color: color,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 10),
        SizedBox(
          width: 80,
          child: Text(
            '$count (${pct.toStringAsFixed(1)}%)',
            style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
            textAlign: TextAlign.right,
          ),
        ),
      ],
    );
  }
}
