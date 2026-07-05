import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/vacancy.dart';
import '../providers/settings_provider.dart';
import '../providers/vacancy_detail_provider.dart';
import '../providers/vacancy_list_provider.dart';
import '../repositories/vacancy_repository.dart';
import '../widgets/fit_dot_bar.dart';
import '../widgets/fit_score_chip.dart';
import '../widgets/vac_score_badge.dart';
import 'vacancy_cv_screen.dart';

// ── JD mode — shown for status='fetched' ──────────────────────────────────────

class _JdModeView extends ConsumerStatefulWidget {
  final int vacancyId;
  final String url;
  final VacancyListItem? vacancy;
  /// When true: show "Restore to Inbox" instead of Analyze/Skip (used for declined-no-analysis).
  final bool restoreMode;

  const _JdModeView({
    required this.vacancyId,
    required this.url,
    this.vacancy,
    this.restoreMode = false,
  });

  @override
  ConsumerState<_JdModeView> createState() => _JdModeViewState();
}

class _JdModeViewState extends ConsumerState<_JdModeView> {
  bool _loadingAnalyze = false;
  bool _loadingDecline = false;
  bool _loadingRestore = false;

  VacancyRepository get _repo {
    final apiUrl = ref.read(settingsProvider).valueOrNull?.apiUrl ?? 'http://localhost:8080';
    return VacancyRepository(baseUrl: apiUrl);
  }

  Future<void> _analyze() async {
    setState(() => _loadingAnalyze = true);
    try {
      await _repo.analyze(widget.vacancyId);
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Analysis queued'), duration: Duration(seconds: 2)),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _loadingAnalyze = false);
    }
  }

  Future<void> _decline() async {
    setState(() => _loadingDecline = true);
    try {
      await _repo.decline(widget.vacancyId);
      if (mounted) ref.read(vacancyListProvider.notifier).refresh();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
        setState(() => _loadingDecline = false);
      }
    }
  }

  Future<void> _restore() async {
    setState(() => _loadingRestore = true);
    try {
      await _repo.restore(widget.vacancyId);
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Moved to inbox'), duration: Duration(seconds: 2)),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
        setState(() => _loadingRestore = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final jdAsync = ref.watch(vacancyJdProvider(widget.vacancyId));
    final role = widget.vacancy?.role ?? '';
    final company = widget.vacancy?.company ?? '';

    return Column(
      children: [
        // Action bar
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: cs.surfaceContainerLowest.withValues(alpha: 0.9),
            border: Border(
              bottom: BorderSide(color: cs.outlineVariant.withValues(alpha: 0.15)),
            ),
          ),
          child: Row(
            children: [
              if (role.isNotEmpty)
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(role,
                          style: Theme.of(context).textTheme.titleSmall,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis),
                      if (company.isNotEmpty)
                        Text(company,
                            style: Theme.of(context)
                                .textTheme
                                .bodySmall
                                ?.copyWith(color: cs.onSurfaceVariant),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis),
                    ],
                  ),
                )
              else
                const Spacer(),
              if (widget.url.isNotEmpty)
                IconButton(
                  icon: Icon(Icons.open_in_new, size: 18, color: cs.onSurfaceVariant),
                  tooltip: 'Open JD',
                  onPressed: () => launchUrl(Uri.parse(widget.url),
                      mode: LaunchMode.externalApplication),
                ),
              if (widget.restoreMode) ...[
                OutlinedButton.icon(
                  onPressed: _loadingRestore ? null : _restore,
                  icon: _loadingRestore
                      ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.inbox_outlined, size: 16),
                  label: const Text('Restore to Inbox'),
                  style: OutlinedButton.styleFrom(
                    side: BorderSide(color: cs.primary.withValues(alpha: 0.5)),
                    foregroundColor: cs.primary,
                  ),
                ),
              ] else ...[
                OutlinedButton(
                  onPressed: _loadingDecline ? null : _decline,
                  style: OutlinedButton.styleFrom(
                    side: BorderSide(color: cs.outlineVariant),
                    foregroundColor: cs.onSurfaceVariant,
                  ),
                  child: _loadingDecline
                      ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('Skip'),
                ),
                const SizedBox(width: 8),
                FilledButton.icon(
                  onPressed: _loadingAnalyze ? null : _analyze,
                  icon: _loadingAnalyze
                      ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.analytics_outlined, size: 16),
                  label: const Text('Analyze'),
                ),
              ],
            ],
          ),
        ),
        // JD content
        Expanded(
          child: jdAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(
              child: Text('Failed to load JD: $e',
                  style: const TextStyle(color: Color(0xFFBA1A1A))),
            ),
            data: (jd) => Markdown(
              data: jd,
              selectable: true,
              padding: const EdgeInsets.fromLTRB(24, 20, 24, 32),
              styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
                p: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: cs.onSurface,
                      height: 1.6,
                    ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

// ── Analyzing view — shown for analysis_queued / analyzing ───────────────────

class _AnalyzingView extends StatelessWidget {
  final String status;

  const _AnalyzingView({required this.status});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final label = status == 'analyzing' ? 'Analyzing...' : 'In queue for analysis...';
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircularProgressIndicator(color: cs.primary),
          const SizedBox(height: 20),
          Text(label, style: Theme.of(context).textTheme.bodyLarge),
          const SizedBox(height: 8),
          Text(
            'Results will appear automatically',
            style: Theme.of(context)
                .textTheme
                .bodySmall
                ?.copyWith(color: cs.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}

// ── Analysis error view — shown for analysis_failed ──────────────────────────

class _AnalysisErrorView extends ConsumerStatefulWidget {
  final int vacancyId;
  final String? errorMessage;

  const _AnalysisErrorView({required this.vacancyId, this.errorMessage});

  @override
  ConsumerState<_AnalysisErrorView> createState() => _AnalysisErrorViewState();
}

class _AnalysisErrorViewState extends ConsumerState<_AnalysisErrorView> {
  bool _retrying = false;

  VacancyRepository get _repo {
    final apiUrl = ref.read(settingsProvider).valueOrNull?.apiUrl ?? 'http://localhost:8080';
    return VacancyRepository(baseUrl: apiUrl);
  }

  Future<void> _retry() async {
    setState(() => _retrying = true);
    try {
      await _repo.analyze(widget.vacancyId);
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Analysis queued'), duration: Duration(seconds: 2)),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
        setState(() => _retrying = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline_rounded, size: 48, color: cs.error),
            const SizedBox(height: 16),
            Text('Analysis failed', style: Theme.of(context).textTheme.titleMedium),
            if (widget.errorMessage != null && widget.errorMessage!.isNotEmpty) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: cs.errorContainer.withValues(alpha: 0.3),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: cs.error.withValues(alpha: 0.3)),
                ),
                child: Text(
                  widget.errorMessage!,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: cs.onSurfaceVariant,
                        fontFamily: 'monospace',
                      ),
                  maxLines: 6,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: _retrying ? null : _retry,
              icon: _retrying
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : const Icon(Icons.refresh_rounded),
              label: Text(_retrying ? 'Queuing...' : 'Retry Analysis'),
            ),
          ],
        ),
      ),
    );
  }
}

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
    final status = vacancy?.status ?? '';

    // analysis_queued / analyzing — spinner only, no point fetching analysis yet
    if (status == 'analysis_queued' || status == 'analyzing') {
      return _AnalyzingView(status: status);
    }

    // analysis_failed — show error + retry button
    if (status == 'analysis_failed') {
      return _AnalysisErrorView(
        vacancyId: vacancyId,
        errorMessage: vacancy?.analysisError,
      );
    }

    // For ALL other statuses (fetched, analyzed, declined): try to load analysis.
    // If analysis exists → show it regardless of status (handles restored vacancies,
    // or any status/analysis_json mismatch). If p2 == null → fall back to JD view.
    final async = ref.watch(vacancyDetailProvider(vacancyId));

    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) {
        // API error → fall back to JD view with context-appropriate buttons
        if (status == 'declined') {
          return _JdModeView(vacancyId: vacancyId, url: url, vacancy: vacancy, restoreMode: true);
        }
        return _JdModeView(vacancyId: vacancyId, url: url, vacancy: vacancy);
      },
      data: (analysis) {
        final p1 = analysis.p1;
        final p2 = analysis.p2;

        if (p2 == null) {
          // No analysis yet — show JD view with context-appropriate buttons
          if (status == 'declined') {
            return _JdModeView(vacancyId: vacancyId, url: url, vacancy: vacancy, restoreMode: true);
          }
          return _JdModeView(vacancyId: vacancyId, url: url, vacancy: vacancy);
        }

        final role = p1?.role.isNotEmpty == true
            ? p1!.role
            : vacancy?.role ?? '';

        return Column(
          children: [
            // Sticky action bar
            _ActionBar(vacancyId: vacancyId, url: url, role: role, status: status),
            // Scrollable content
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Hero header
                    _VacancyHero(p1: p1, p2: p2, vacancyId: vacancyId, vacancy: vacancy),
                    const SizedBox(height: 24),
                    // Quick Overview — who they want + barriers + risks + warnings
                    _QuickOverviewCard(p2: p2),
                    const SizedBox(height: 16),
                    // Fit dimensions
                    if (p2.fitDimensions != null)
                      _CollapsibleSection(
                        title: 'Fit Dimensions',
                        initiallyExpanded: true,
                        child: _FitDimsTable(dims: p2.fitDimensions!),
                      ),
                    if (p1 != null) ...[
                      const SizedBox(height: 16),
                      _CollapsibleSection(
                        title: 'Attraction Breakdown',
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
  final String role;
  final String status;

  const _ActionBar({
    required this.vacancyId,
    required this.url,
    required this.role,
    this.status = 'analyzed',
  });

  @override
  ConsumerState<_ActionBar> createState() => _ActionBarState();
}

class _ActionBarState extends ConsumerState<_ActionBar> {
  bool _loadingCv = false;
  bool _loadingDecline = false;
  bool _loadingRestore = false;

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

  Future<void> _restore() async {
    setState(() => _loadingRestore = true);
    try {
      await _repo.restore(widget.vacancyId);
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Moved to inbox'), duration: Duration(seconds: 2)),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
        setState(() => _loadingRestore = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final isDeclined = widget.status == 'declined';

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
          // View CV
          if (!isDeclined)
            IconButton(
              icon: Icon(Icons.article_outlined, size: 18, color: cs.onSurfaceVariant),
              tooltip: 'View CV',
              onPressed: () => showDialog<void>(
                context: context,
                builder: (_) => VacancyCvDialog(
                  vacancyId: widget.vacancyId,
                  role: widget.role,
                ),
              ),
            ),
          const SizedBox(width: 4),
          // Archive: Restore to inbox — replaces Decline button
          if (isDeclined) ...[
            OutlinedButton.icon(
              onPressed: _loadingRestore ? null : _restore,
              icon: _loadingRestore
                  ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.inbox_outlined, size: 16),
              label: const Text('Restore to Inbox'),
              style: OutlinedButton.styleFrom(
                side: BorderSide(color: cs.primary.withValues(alpha: 0.5)),
                foregroundColor: cs.primary,
              ),
            ),
          ] else ...[
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
        ],
      ),
    );
  }
}

// ── Hero header — role icon + title + verdict card + compact scores ───────────

class _VacancyHero extends StatelessWidget {
  final Phase1Data? p1;
  final Phase2Data p2;
  final VacancyListItem? vacancy;
  final int vacancyId;

  const _VacancyHero({required this.p1, required this.p2, required this.vacancyId, this.vacancy});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final role    = p1?.role.isNotEmpty == true ? p1!.role : (vacancy?.role ?? '');
    final company = p1?.company.isNotEmpty == true ? p1!.company : (vacancy?.company ?? '');
    final publishedAt = vacancy?.publishedAt;
    // category moves to Quick Overview block, not used in hero

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 24),
        // Icon + Title + Subtitle
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
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
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      Expanded(
                        child: Text(
                          role,
                          style: Theme.of(context).textTheme.displaySmall?.copyWith(
                                fontSize: 28,
                                fontWeight: FontWeight.w700,
                                color: cs.onSurface,
                                height: 1.2,
                              ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Text(
                        '#$vacancyId',
                        style: Theme.of(context).textTheme.labelSmall?.copyWith(
                              color: cs.onSurfaceVariant.withValues(alpha: 0.45),
                            ),
                      ),
                    ],
                  ),
                  if (company.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    Text(
                      company,
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
        const SizedBox(height: 20),
        // Verdict card — primary go/no-go decision
        _VerdictCard(
          recommendation: p2.recommendation,
          recommendationLabel: p2.recommendationLabel,
          northStar: p1?.northStar,
        ),
        const SizedBox(height: 12),
        // Scores left (wrap on narrow), date pinned right
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Expanded(
              child: Wrap(
                spacing: 8,
                runSpacing: 6,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  FitScoreChip(score: p2.fitScore),
                  FitDotBar(score: p2.fitScore),
                  if (p1 != null) VacScoreBadge(score: p1!.vacancyScore),
                ],
              ),
            ),
            if (publishedAt != null) ...[
              const SizedBox(width: 8),
              _PostedChip(publishedAt: publishedAt, cs: cs),
            ],
          ],
        ),
      ],
    );
  }
}

class _VerdictCard extends StatelessWidget {
  final String recommendation;
  final String recommendationLabel;
  final String? northStar;

  const _VerdictCard({
    required this.recommendation,
    required this.recommendationLabel,
    this.northStar,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;

    final (bgColor, iconColor, icon) = switch (recommendation) {
      'apply' => (cs.primaryContainer, cs.primary, Icons.check_circle_rounded),
      'take_a_chance' => (cs.tertiaryContainer, cs.tertiary, Icons.bolt_rounded),
      _ => (cs.errorContainer, cs.error, Icons.cancel_rounded),
    };

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Icon(icon, size: 36, color: iconColor),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  recommendationLabel.isNotEmpty
                      ? recommendationLabel
                      : recommendation,
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        color: cs.onSurface,
                        fontWeight: FontWeight.w700,
                      ),
                ),
                if (northStar != null && northStar!.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    northStar!,
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: cs.onSurface.withValues(alpha: 0.65),
                        ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
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

// ── Quick Overview ────────────────────────────────────────────────────────────

class _QuickOverviewCard extends StatelessWidget {
  final Phase2Data p2;

  const _QuickOverviewCard({required this.p2});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final hasContent = p2.category.isNotEmpty ||
        p2.whoTheyWant.isNotEmpty ||
        p2.keyBarriers.isNotEmpty ||
        p2.hiddenRisks.isNotEmpty ||
        p2.warnings.isNotEmpty;

    if (!hasContent) return const SizedBox.shrink();

    return _SectionCard(
      title: 'Quick Overview',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (p2.category.isNotEmpty)
            _OverviewRow(
              label: 'Category',
              text: p2.category,
              icon: Icons.label_outline,
              iconColor: const Color(0xFF2E7D32),
            ),
          if (p2.whoTheyWant.isNotEmpty) ...[
            const SizedBox(height: 10),
            _OverviewRow(
              label: 'Who they want',
              text: p2.whoTheyWant,
              icon: Icons.person_search_outlined,
              iconColor: const Color(0xFF1565C0),
            ),
          ],
          if (p2.keyBarriers.isNotEmpty) ...[
            const SizedBox(height: 10),
            _OverviewRow(
              label: 'Key Barriers',
              text: p2.keyBarriers.join('; '),
              icon: Icons.warning_amber_rounded,
              iconColor: cs.error,
            ),
          ],
          if (p2.hiddenRisks.isNotEmpty) ...[
            const SizedBox(height: 10),
            _OverviewRow(
              label: 'Hidden Risks',
              text: p2.hiddenRisks.join('; '),
              icon: Icons.warning_amber_rounded,
              iconColor: cs.error,
            ),
          ],
          if (p2.warnings.isNotEmpty) ...[
            const SizedBox(height: 10),
            _OverviewRow(
              label: 'Warnings',
              text: p2.warnings.join('; '),
              icon: Icons.info_outline,
              iconColor: const Color(0xFFF57F17),
            ),
          ],
        ],
      ),
    );
  }
}

class _OverviewRow extends StatelessWidget {
  final String label;
  final String text;
  final IconData? icon;
  final Color? iconColor;

  const _OverviewRow({
    required this.label,
    required this.text,
    this.icon,
    this.iconColor,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    final labelColor = iconColor ?? cs.onSurfaceVariant;

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (icon != null) ...[
          Padding(
            padding: const EdgeInsets.only(top: 1),
            child: Icon(icon, size: 13, color: labelColor),
          ),
          const SizedBox(width: 5),
        ],
        Expanded(
          child: RichText(
            text: TextSpan(
              children: [
                TextSpan(
                  text: '$label: ',
                  style: tt.bodySmall?.copyWith(
                    color: labelColor,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                TextSpan(
                  text: text,
                  style: tt.bodySmall?.copyWith(color: cs.onSurface),
                ),
              ],
            ),
          ),
        ),
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
