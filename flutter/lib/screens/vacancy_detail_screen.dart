import 'dart:async';
import 'dart:io';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/vacancy.dart';
import '../models/health.dart';
import '../providers/health_provider.dart';
import '../providers/settings_provider.dart';
import '../providers/vacancy_detail_provider.dart';
import '../providers/vacancy_list_provider.dart';
import '../repositories/vacancy_repository.dart';
import '../providers/vacancy_cv_provider.dart';
import '../utils/backend_time.dart';

/// Renders a pre-filter reason string ("category: explanation" — as produced by
/// prompts/pm|generic/prefilter.md) with the category bolded + capitalized,
/// e.g. "title: Product Marketing Lead is a Marketing function" →
/// "•  **Title:** Product Marketing Lead is a Marketing function".
Widget _reasonLine(String reason, {TextStyle? style}) {
  final colonIdx = reason.indexOf(':');
  if (colonIdx == -1) {
    return Text('•  $reason', style: style);
  }
  final category = reason.substring(0, colonIdx).trim();
  final rest = reason.substring(colonIdx + 1).trim();
  final capitalized = category.isEmpty ? category : category[0].toUpperCase() + category.substring(1);
  return Text.rich(
    TextSpan(
      style: style,
      children: [
        const TextSpan(text: '•  '),
        TextSpan(text: '$capitalized: ', style: const TextStyle(fontWeight: FontWeight.bold)),
        TextSpan(text: rest),
      ],
    ),
  );
}

// ── JD mode — shown for status='fetched' ──────────────────────────────────────

class _JdModeView extends ConsumerStatefulWidget {
  final int vacancyId;
  final String url;
  final VacancyListItem? vacancy;
  /// When true: show "Restore to Inbox" instead of Analyze/Skip (used for declined-no-analysis).
  final bool restoreMode;
  final VoidCallback? onSkipped;

  const _JdModeView({
    super.key,
    required this.vacancyId,
    required this.url,
    this.vacancy,
    this.restoreMode = false,
    this.onSkipped,
  });

  @override
  ConsumerState<_JdModeView> createState() => _JdModeViewState();
}

class _JdModeViewState extends ConsumerState<_JdModeView> {
  bool _loadingAnalyze = false;
  bool _loadingDecline = false;
  bool _loadingRestore = false;
  bool _loadingPrefilter = false;
  bool _refreshing = false;
  // Kept for the "View details" affordance on _PrefilterBanner — the modal
  // is no longer shown automatically (found unreliable/easy-to-miss in
  // practice, 2026-07-17) but raw_output/error are still worth a drill-down.
  Map<String, dynamic>? _lastPrefilterResult;

  Future<void> _refresh() async {
    setState(() => _refreshing = true);
    try {
      ref.invalidate(vacancyListProvider);
      ref.invalidate(vacancyDetailProvider(widget.vacancyId));
      ref.invalidate(vacancyCvProvider(widget.vacancyId));
      ref.invalidate(vacancyJdProvider(widget.vacancyId));
    } finally {
      if (mounted) setState(() => _refreshing = false);
    }
  }

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

  Future<void> _checkBlockers() async {
    setState(() => _loadingPrefilter = true);
    try {
      final result = await _repo.runPrefilter(widget.vacancyId);
      if (mounted) {
        setState(() => _lastPrefilterResult = result);
        // Persistent result now lives in _PrefilterBanner (driven by the
        // refreshed vacancy's blocker_flag/reasons) — the SnackBar here is
        // just immediate feedback for THIS click, not the record of what
        // happened. Record itself: banner (persisted) + Activity log (raw).
        ref.read(vacancyListProvider.notifier).refresh();
        final ok = result['ok'] as bool? ?? false;
        final blocked = result['blocked'] as bool? ?? false;
        // provider_unavailable is the SAME signal from every provider (Ollama
        // not running, Claude API down/rate-limited, claude CLI missing) — show
        // the actual reason immediately, not a generic "something failed"
        // (gap found 2026-07-17: Ollama being down looked like any other error).
        final providerUnavailable = result['provider_unavailable'] as bool? ?? false;
        final String msg;
        Color? bg;
        if (providerUnavailable) {
          msg = 'LLM provider unavailable: ${result['error']}';
          bg = Colors.orange.shade800;
        } else if (!ok) {
          msg = 'Check failed — see details below';
          bg = Colors.red;
        } else {
          msg = blocked ? 'Possible blocker found — see below' : 'Checked — no blockers found';
        }
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(msg),
            backgroundColor: bg,
            duration: Duration(seconds: providerUnavailable ? 6 : 3),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _loadingPrefilter = false);
    }
  }

  /// "Details" affordance — uses the session-fresh result if this click's
  /// _checkBlockers() already ran, otherwise fetches the persisted raw_output
  /// from the server (works after app restart/navigation, when the session
  /// state is gone but the vacancy's own record isn't).
  Future<void> _showPrefilterDetails() async {
    if (_lastPrefilterResult != null) {
      await _showPrefilterResult(_lastPrefilterResult!);
      return;
    }
    final rawOutput = await _repo.getVacancyBlockerRawOutput(widget.vacancyId);
    if (!mounted) return;
    await _showPrefilterResult({
      'ok': true,
      'blocked': widget.vacancy?.blockerFlag ?? false,
      'reasons': widget.vacancy?.blockerReasons ?? const [],
      'raw_output': rawOutput,
      'error': null,
      'provider_unavailable': false,
    });
  }

  Future<void> _showPrefilterResult(Map<String, dynamic> result) {
    // "ok" distinguishes a real, correctly-parsed answer from any failure (call
    // unreachable/model missing/output didn't match format) — collapsing these
    // into "no blockers" is exactly the bug found on vacancy #716 (2026-07-17).
    final ok = result['ok'] as bool? ?? false;
    final blocked = result['blocked'] as bool? ?? false;
    final reasons = (result['reasons'] as List<dynamic>? ?? []).cast<String>();
    final rawOutput = result['raw_output'] as String?;
    final error = result['error'] as String?;
    final providerUnavailable = result['provider_unavailable'] as bool? ?? false;

    final title = providerUnavailable
        ? '🔌 Provider unavailable'
        : (!ok ? '❌ Check failed' : (blocked ? '⚠️ Possible blocker found' : '✅ No blockers'));

    return showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: SizedBox(
          width: 460,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (!ok) ...[
                  Text(error ?? 'Unknown error', style: TextStyle(color: Theme.of(ctx).colorScheme.error)),
                  const SizedBox(height: 8),
                  if (providerUnavailable)
                    Text(
                      "The LLM provider configured for this phase couldn't be reached "
                      '(service not running, down, or rate-limited). Check it\'s running, '
                      'or switch provider in Settings → Advanced: Per-Phase Routing.',
                      style: Theme.of(ctx).textTheme.bodySmall,
                    )
                  else
                    Text('Full record (model, tokens, timing, or lack thereof) is in the Activity tab.',
                        style: Theme.of(ctx).textTheme.bodySmall),
                ] else if (blocked)
                  ...reasons.map((r) => Padding(
                        padding: const EdgeInsets.only(bottom: 6),
                        child: _reasonLine(r),
                      ))
                else
                  const Text('The pre-filter found no explicit conflict with your Critical Blockers.'),
                if (rawOutput != null && rawOutput.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  ExpansionTile(
                    tilePadding: EdgeInsets.zero,
                    title: Text('Raw model output', style: Theme.of(ctx).textTheme.labelMedium),
                    children: [
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: Theme.of(ctx).colorScheme.surfaceContainerHighest,
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: SelectableText(rawOutput, style: const TextStyle(fontSize: 11.5, fontFamily: 'monospace')),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(), child: const Text('Close')),
        ],
      ),
    );
  }

  /// Same pipeline_runs + llm_usage data as the tabbed Activity view — but that
  /// tab only exists once Phase 1+2 analysis exists (VacancyDetailScreen gates
  /// the whole TabBar on `p2 != null`). Before analysis (e.g. only a pre-filter
  /// check has run, like vacancy #716 — 2026-07-17), there was no way to see
  /// this data in the UI at all despite it being recorded. _ActivityLogView is
  /// self-contained (fetches its own data by vacancyId) — reused as-is here.
  void _showActivityLog(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => Dialog(
        child: SizedBox(
          width: 640,
          height: 480,
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 12, 0),
                child: Row(
                  children: [
                    Text('Activity — Vacancy #${widget.vacancyId}', style: Theme.of(ctx).textTheme.titleMedium),
                    const Spacer(),
                    IconButton(icon: const Icon(Icons.close), onPressed: () => Navigator.of(ctx).pop()),
                  ],
                ),
              ),
              Expanded(child: _ActivityLogView(vacancyId: widget.vacancyId)),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _decline() async {
    setState(() => _loadingDecline = true);
    try {
      await _repo.decline(widget.vacancyId);
      if (mounted) {
        widget.onSkipped?.call();
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
    final jdAsync = ref.watch(vacancyJdProvider(widget.vacancyId));
    final role = widget.vacancy?.role ?? '';
    final company = widget.vacancy?.company ?? '';
    final health = ref.watch(healthProvider).valueOrNull ?? HealthStatus.checking;
    final workerAvailable = health == HealthStatus.online;

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
              if (widget.vacancy?.folderPath != null)
                IconButton(
                  icon: Icon(Icons.folder_open_outlined, size: 18, color: cs.onSurfaceVariant),
                  tooltip: 'Open folder',
                  onPressed: () => Process.run('explorer.exe', [widget.vacancy!.folderPath!]),
                ),
              Tooltip(
                message: 'Refresh vacancy data',
                child: IconButton(
                  icon: _refreshing
                      ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                      : Icon(Icons.sync_rounded, size: 18, color: cs.onSurfaceVariant),
                  onPressed: _refreshing ? null : _refresh,
                ),
              ),
              Tooltip(
                message: 'Activity log — pipeline runs + LLM calls (incl. pre-filter checks). '
                    'Only reachable from this JD view before analysis — the tabbed Activity tab '
                    'only appears once Phase 1+2 analysis exists.',
                child: IconButton(
                  icon: Icon(Icons.history_rounded, size: 18, color: cs.onSurfaceVariant),
                  onPressed: () => _showActivityLog(context),
                ),
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
                    side: BorderSide(color: cs.error),
                    foregroundColor: cs.error,
                  ),
                  child: _loadingDecline
                      ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('Skip'),
                ),
                const SizedBox(width: 8),
                Tooltip(
                  message: 'Run the critical-blocker pre-filter manually (EPIC-27) — not auto-triggered yet',
                  child: OutlinedButton.icon(
                    onPressed: _loadingPrefilter ? null : _checkBlockers,
                    icon: _loadingPrefilter
                        ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.block_outlined, size: 16),
                    label: const Text('Check blockers'),
                    style: OutlinedButton.styleFrom(
                      side: BorderSide(color: cs.outlineVariant),
                      foregroundColor: cs.onSurfaceVariant,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Tooltip(
                  message: workerAvailable ? '' : 'Analysis worker unavailable — start agent.py',
                  child: FilledButton.icon(
                    onPressed: _loadingAnalyze || !workerAvailable ? null : _analyze,
                    icon: _loadingAnalyze
                        ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                        : const Icon(Icons.analytics_outlined, size: 16),
                    label: const Text('Analyze'),
                  ),
                ),
              ],
            ],
          ),
        ),
        // Salary / vacancy id — own full-width block, not squeezed into the
        // action bar's title column (was cramped + collided with the icon
        // row there, 2026-08-11 user feedback).
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          decoration: BoxDecoration(
            color: cs.surfaceContainerLowest.withValues(alpha: 0.9),
            border: Border(
              bottom: BorderSide(color: cs.outlineVariant.withValues(alpha: 0.15)),
            ),
          ),
          child: Row(
            children: [
              _SalaryInline(
                salary: widget.vacancy?.salary,
                fontSize: 16,
                onSave: (v) async {
                  await _repo.updateSalary(widget.vacancyId, v);
                  ref.read(vacancyListProvider.notifier).refresh();
                },
              ),
              const Spacer(),
              Text('#${widget.vacancyId}',
                  style: Theme.of(context)
                      .textTheme
                      .bodyMedium
                      ?.copyWith(color: cs.onSurfaceVariant.withValues(alpha: 0.6)),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis),
            ],
          ),
        ),
        _PrefilterBanner(
          blocked: widget.vacancy?.blockerFlag ?? false,
          checked: widget.vacancy?.blockerChecked ?? false,
          reasons: widget.vacancy?.blockerReasons ?? const [],
          onTapDetails: (widget.vacancy?.blockerChecked ?? false) ? _showPrefilterDetails : null,
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
      await _repo.reset(widget.vacancyId);
      await _repo.analyze(widget.vacancyId);
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Reset & queued for analysis'), duration: Duration(seconds: 2)),
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
              label: Text(_retrying ? 'Resetting...' : 'Reset & Retry'),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Analysis error banner — compact dismissible strip for retry-failed state ──

class _AnalysisErrorBanner extends ConsumerStatefulWidget {
  final int vacancyId;
  final String? errorMessage;
  final VoidCallback onDismiss;

  const _AnalysisErrorBanner({
    required this.vacancyId,
    required this.onDismiss,
    this.errorMessage,
  });

  @override
  ConsumerState<_AnalysisErrorBanner> createState() => _AnalysisErrorBannerState();
}

class _AnalysisErrorBannerState extends ConsumerState<_AnalysisErrorBanner> {
  bool _retrying = false;

  Future<void> _retry() async {
    setState(() => _retrying = true);
    try {
      final apiUrl = ref.read(settingsProvider).valueOrNull?.apiUrl ?? 'http://localhost:8080';
      final repo = VacancyRepository(baseUrl: apiUrl);
      await repo.reset(widget.vacancyId);
      await repo.analyze(widget.vacancyId);
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
        widget.onDismiss();
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
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: cs.errorContainer.withValues(alpha: 0.35),
        border: Border(bottom: BorderSide(color: cs.error.withValues(alpha: 0.25))),
      ),
      child: Row(
        children: [
          Icon(Icons.error_outline_rounded, size: 16, color: cs.error),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              widget.errorMessage?.isNotEmpty == true
                  ? 'Analysis failed: ${widget.errorMessage}'
                  : 'Analysis failed — previous results shown',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 8),
          TextButton(
            onPressed: _retrying ? null : _retry,
            style: TextButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              minimumSize: Size.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: _retrying
                ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Reset & Retry'),
          ),
          IconButton(
            icon: const Icon(Icons.close_rounded, size: 16),
            onPressed: widget.onDismiss,
            padding: const EdgeInsets.all(4),
            constraints: const BoxConstraints(),
            tooltip: 'Dismiss',
          ),
        ],
      ),
    );
  }
}

class VacancyDetailScreen extends ConsumerStatefulWidget {
  final int vacancyId;
  final String url;
  final VacancyListItem? vacancy;
  final VoidCallback? onSkipped;
  final void Function(int vacancyId)? onNavigateTo;

  const VacancyDetailScreen({
    super.key,
    required this.vacancyId,
    required this.url,
    this.vacancy,
    this.onSkipped,
    this.onNavigateTo,
  });

  @override
  ConsumerState<VacancyDetailScreen> createState() => _VacancyDetailScreenState();
}

class _VacancyDetailScreenState extends ConsumerState<VacancyDetailScreen>
    with SingleTickerProviderStateMixin {

  late TabController _tabController;
  Timer? _cvPollingTimer;
  bool _errorBannerDismissed = false;

  static bool _needsPolling(String? status) =>
      status == 'cv_queued' || status == 'cv_generating' || status == 'cover_generating';

  void _startPollingIfNeeded(String? status) {
    if (_needsPolling(status)) {
      _cvPollingTimer ??= Timer.periodic(const Duration(seconds: 3), (_) {
        if (mounted) ref.read(vacancyListProvider.notifier).refresh();
      });
    } else {
      _cvPollingTimer?.cancel();
      _cvPollingTimer = null;
    }
  }

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this);
    _startPollingIfNeeded(widget.vacancy?.status);
  }

  @override
  void didUpdateWidget(VacancyDetailScreen old) {
    super.didUpdateWidget(old);
    final oldStatus = old.vacancy?.status;
    final newStatus = widget.vacancy?.status;
    if (oldStatus != 'cv_generated' && newStatus == 'cv_generated') {
      ref.invalidate(vacancyCvProvider(widget.vacancyId));
      _tabController.animateTo(1);
    }
    if (oldStatus == 'cover_generating' && newStatus == 'cover_generated') {
      ref.invalidate(vacancyCvProvider(widget.vacancyId));
      _tabController.animateTo(2);
    }
    if ((oldStatus == 'analysis_queued' || oldStatus == 'analyzing') &&
        newStatus == 'analyzed') {
      ref.invalidate(vacancyDetailProvider(widget.vacancyId));
    }
    if (newStatus == 'analysis_failed' && oldStatus != 'analysis_failed') {
      setState(() => _errorBannerDismissed = false);
    }
    _startPollingIfNeeded(newStatus);
  }

  @override
  void dispose() {
    _cvPollingTimer?.cancel();
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final status = widget.vacancy?.status ?? '';

    // analysis_queued / analyzing — spinner only, no point fetching analysis yet
    if (status == 'analysis_queued' || status == 'analyzing') {
      return _AnalyzingView(status: status);
    }

    // analysis_failed — full blocker only when no prior data; otherwise fall through
    // to normal view and show a dismissible banner (previous analysis data remains visible)
    if (status == 'analysis_failed' && widget.vacancy?.fitScore == null) {
      return _AnalysisErrorView(
        vacancyId: widget.vacancyId,
        errorMessage: widget.vacancy?.analysisError,
      );
    }

    // For ALL other statuses (fetched, analyzed, declined): try to load analysis.
    // If analysis exists → show it regardless of status (handles restored vacancies,
    // or any status/analysis_json mismatch). If p2 == null → fall back to JD view.
    final async = ref.watch(vacancyDetailProvider(widget.vacancyId));

    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) {
        // API error → fall back to JD view with context-appropriate buttons
        if (status == 'declined') {
          return _JdModeView(key: ValueKey(widget.vacancyId), vacancyId: widget.vacancyId, url: widget.url, vacancy: widget.vacancy, restoreMode: true);
        }
        return _JdModeView(key: ValueKey(widget.vacancyId), vacancyId: widget.vacancyId, url: widget.url, vacancy: widget.vacancy, onSkipped: widget.onSkipped);
      },
      data: (analysis) {
        final p1 = analysis.p1;
        final p2 = analysis.p2;

        if (p2 == null) {
          // No analysis yet — show JD view with context-appropriate buttons
          if (status == 'declined') {
            return _JdModeView(key: ValueKey(widget.vacancyId), vacancyId: widget.vacancyId, url: widget.url, vacancy: widget.vacancy, restoreMode: true);
          }
          return _JdModeView(key: ValueKey(widget.vacancyId), vacancyId: widget.vacancyId, url: widget.url, vacancy: widget.vacancy, onSkipped: widget.onSkipped);
        }

        final role = p1?.role.isNotEmpty == true
            ? p1!.role
            : widget.vacancy?.role ?? '';

        return Column(
          children: [
            // Error banner for retry-failed state (has prior data, so show tabs)
            if (status == 'analysis_failed' && !_errorBannerDismissed)
              _AnalysisErrorBanner(
                vacancyId: widget.vacancyId,
                errorMessage: widget.vacancy?.analysisError,
                onDismiss: () => setState(() => _errorBannerDismissed = true),
              ),
            // Sticky action bar
            _ActionBar(vacancyId: widget.vacancyId, url: widget.url, role: role, status: status, vacancy: widget.vacancy, tabController: _tabController),
            // Tab bar
            TabBar(
              controller: _tabController,
              tabs: const [
                Tab(text: 'Analysis'),
                Tab(text: 'CV'),
                Tab(text: 'Cover'),
                Tab(text: 'Activity'),
              ],
              tabAlignment: TabAlignment.start,
              isScrollable: true,
              labelPadding: const EdgeInsets.symmetric(horizontal: 20),
            ),
            // Tab content
            Expanded(
              child: TabBarView(
                controller: _tabController,
                children: [
                  // Tab 0: Analysis
                  SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(24, 0, 24, 24),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _VacancyHero(
                          p1: p1,
                          p2: p2,
                          vacancyId: widget.vacancyId,
                          vacancy: widget.vacancy,
                          salary: widget.vacancy?.salary,
                          onSalaryChanged: (v) async {
                            final apiUrl = ref.read(settingsProvider).valueOrNull?.apiUrl ?? 'http://localhost:8080';
                            await VacancyRepository(baseUrl: apiUrl).updateSalary(widget.vacancyId, v);
                            ref.invalidate(vacancyListProvider);
                          },
                        ),
                        if (widget.vacancy != null)
                          _RelatedSection(
                            vacancy: widget.vacancy!,
                            onNavigateTo: widget.onNavigateTo,
                          ),
                        const SizedBox(height: 16),
                        _WhyCard(p2: p2),
                        const SizedBox(height: 16),
                        _QuickOverviewCard(p2: p2),
                        const SizedBox(height: 16),
                        if (p2.fitDimensions != null)
                          _CollapsibleSection(
                            title: 'Fit Dimensions',
                            tooltip: 'Fit scored across 5 axes (0–10 each):\ndomain, execution, strategy, systems, stakeholder',
                            child: _FitDimsTable(dims: p2.fitDimensions!),
                          ),
                        if (p1 != null) ...[
                          const SizedBox(height: 16),
                          _CollapsibleSection(
                            title: 'Attraction Breakdown',
                            tooltip: 'How attractive this vacancy is for you\nacross 8 factors: company tier, seniority,\nscope, compensation and more',
                            child: _VacScoreTable(dims: p1.vacscoreDims),
                          ),
                          const SizedBox(height: 16),
                          if (p1.roleBalance.isNotEmpty)
                            _CollapsibleSection(
                              title: 'Role Balance',
                              tooltip: 'Estimated split of responsibilities\nin this role (%)',
                              child: _RoleBalanceBar(balance: p1.roleBalance),
                            ),
                        ],
                        const SizedBox(height: 16),
                        _JdSection(vacancyId: widget.vacancyId),
                        const SizedBox(height: 80),
                      ],
                    ),
                  ),
                  // Tab 1: CV
                  _CvTab(vacancyId: widget.vacancyId, status: status),
                  // Tab 2: Cover
                  _CoverTab(vacancyId: widget.vacancyId, status: status),
                  // Tab 3: Activity
                  _ActivityLogView(vacancyId: widget.vacancyId),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}

// ── Related section — duplicates / original cross-links ──────────────────────

class _RelatedSection extends ConsumerWidget {
  final VacancyListItem vacancy;
  final void Function(int vacancyId)? onNavigateTo;

  const _RelatedSection({required this.vacancy, this.onNavigateTo});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final all = ref.watch(vacancyListProvider).valueOrNull?.vacancies ?? [];

    final VacancyListItem? original = vacancy.duplicateOf != null
        ? all.where((v) => v.id == vacancy.duplicateOf).firstOrNull
        : null;

    final duplicates = all.where((v) => v.duplicateOf == vacancy.id).toList();

    if (original == null && duplicates.isEmpty) return const SizedBox.shrink();

    final cs = Theme.of(context).colorScheme;

    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.link_rounded, size: 14, color: cs.onSurfaceVariant),
              const SizedBox(width: 6),
              Text(
                'Related',
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                      color: cs.onSurfaceVariant,
                      fontWeight: FontWeight.w600,
                    ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 6,
            children: [
              if (original != null)
                _RelatedChip(
                  label: 'Original · ${original.role.isNotEmpty ? original.role : '#${original.id}'}',
                  sublabel: original.company.isNotEmpty ? original.company : null,
                  id: original.id,
                  icon: Icons.arrow_upward_rounded,
                  tooltip: 'This vacancy is a duplicate — the original posting is #${original.id}.\nTap to open the original.',
                  onTap: onNavigateTo != null ? () => onNavigateTo!(original.id) : null,
                ),
              for (final dup in duplicates)
                _RelatedChip(
                  label: '${dup.site.isNotEmpty ? dup.site[0].toUpperCase() + dup.site.substring(1) : 'Dup'} · ${dup.role.isNotEmpty ? dup.role : '#${dup.id}'}',
                  sublabel: dup.company.isNotEmpty ? dup.company : null,
                  id: dup.id,
                  icon: Icons.copy_rounded,
                  tooltip: 'The same job was also found on ${dup.site.isNotEmpty ? dup.site : 'another source'} (vacancy #${dup.id}).\nTap to open it.',
                  onTap: onNavigateTo != null ? () => onNavigateTo!(dup.id) : null,
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _RelatedChip extends StatelessWidget {
  final String label;
  final String? sublabel;
  final int id;
  final IconData icon;
  final String tooltip;
  final VoidCallback? onTap;

  const _RelatedChip({
    required this.label,
    required this.id,
    required this.icon,
    required this.tooltip,
    this.sublabel,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Tooltip(
      message: tooltip,
      preferBelow: true,
      child: MouseRegion(
        cursor: onTap != null ? SystemMouseCursors.click : MouseCursor.defer,
        child: GestureDetector(
        onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: cs.surfaceContainerLow,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: onTap != null
                ? cs.primary.withValues(alpha: 0.35)
                : cs.outlineVariant,
            width: 1,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 13, color: onTap != null ? cs.primary : cs.onSurfaceVariant),
            const SizedBox(width: 6),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  '$label  #$id',
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                        color: onTap != null ? cs.primary : cs.onSurface,
                        fontWeight: FontWeight.w600,
                      ),
                ),
                if (sublabel != null)
                  Text(
                    sublabel!,
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                          color: cs.onSurfaceVariant,
                          fontSize: 10,
                        ),
                  ),
              ],
            ),
          ],
        ),
      ),
        ),
      ),
    );
  }
}

// ── JD section — always shown at the bottom of the detail view ───────────────

class _JdSection extends ConsumerWidget {
  final int vacancyId;

  const _JdSection({required this.vacancyId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;
    final jdAsync = ref.watch(vacancyJdProvider(vacancyId));

    return _CollapsibleSection(
      title: 'Job Description',
      tooltip: 'Original job description as fetched from the source',
      initiallyExpanded: true,
      child: jdAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Text('Failed to load JD: $e',
            style: TextStyle(color: cs.error)),
        data: (jd) => MarkdownBody(
          data: jd,
          selectable: true,
          styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
            p: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: cs.onSurface,
                  height: 1.6,
                ),
          ),
        ),
      ),
    );
  }
}

// ── Activity log tab ─────────────────────────────────────────────────────────

class _ActivityLogView extends ConsumerStatefulWidget {
  final int vacancyId;

  const _ActivityLogView({required this.vacancyId});

  @override
  ConsumerState<_ActivityLogView> createState() => _ActivityLogViewState();
}

class _ActivityLogViewState extends ConsumerState<_ActivityLogView> {
  List<PipelineRun>? _runs;
  List<ActivityEntry>? _entries;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final apiUrl = ref.read(settingsProvider).valueOrNull?.apiUrl ?? 'http://localhost:8080';
    try {
      final result = await VacancyRepository(baseUrl: apiUrl).getActivity(widget.vacancyId);
      if (mounted) setState(() { _runs = result.runs; _entries = result.entries; _loading = false; });
    } catch (e) {
      if (mounted) setState(() { _error = '$e'; _loading = false; });
    }
  }

  static DateTime _asUtc(String iso) => parseBackendUtc(iso).toLocal();

  // Convert ISO UTC string → device local time, formatted DD.MM.YYYY HH:mm
  String _fmtTs(String? iso) {
    if (iso == null || iso.isEmpty) return '—';
    try {
      final dt  = _asUtc(iso);
      final dd  = dt.day.toString().padLeft(2, '0');
      final mm  = dt.month.toString().padLeft(2, '0');
      final yy  = dt.year.toString();
      final hh  = dt.hour.toString().padLeft(2, '0');
      final min = dt.minute.toString().padLeft(2, '0');
      return '$dd.$mm.$yy $hh:$min';
    } catch (_) {
      return iso.length >= 16 ? iso.substring(0, 16).replaceAll('T', ' ') : iso;
    }
  }

  String _fmtMs(int ms) => ms >= 1000 ? '${(ms / 1000).toStringAsFixed(1)}s' : '${ms}ms';
  String _k(int n)       => n >= 1000  ? '${(n  / 1000).toStringAsFixed(1)}k' : '$n';

  // ── Shared container ──────────────────────────────────────────────────────────

  Widget _section(BuildContext context, String label, Widget body) {
    final cs = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: Theme.of(context).textTheme.labelSmall
            ?.copyWith(color: cs.onSurfaceVariant, letterSpacing: 0.8)),
        const SizedBox(height: 6),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: cs.surfaceContainerLow,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: cs.outlineVariant.withValues(alpha: 0.4)),
          ),
          child: body,
        ),
      ],
    );
  }

  // ── Pipeline Runs table ───────────────────────────────────────────────────────

  Widget _runsTable(BuildContext context, List<PipelineRun> runs) {
    final cs = Theme.of(context).colorScheme;
    const hStyle = TextStyle(fontSize: 10.5, fontWeight: FontWeight.w600, letterSpacing: 0.4);
    const dStyle = TextStyle(fontSize: 11.5, height: 1.6);

    Widget hcell(String t, {TextAlign a = TextAlign.left}) => Padding(
      padding: const EdgeInsets.fromLTRB(4, 2, 14, 5),
      child: Text(t, style: hStyle.copyWith(color: cs.onSurfaceVariant), textAlign: a),
    );
    Widget cell(String t, {TextAlign a = TextAlign.left, Color? color, bool bold = false}) => Padding(
      padding: const EdgeInsets.fromLTRB(4, 2, 14, 2),
      child: Text(t,
        style: dStyle.copyWith(color: color, fontWeight: bold ? FontWeight.w600 : null),
        textAlign: a),
    );

    return Table(
      columnWidths: const {
        0: IntrinsicColumnWidth(),  // time
        1: IntrinsicColumnWidth(),  // phase
        2: IntrinsicColumnWidth(),  // icon
        3: IntrinsicColumnWidth(),  // status
        4: IntrinsicColumnWidth(),  // duration
        5: FlexColumnWidth(),       // error
      },
      defaultVerticalAlignment: TableCellVerticalAlignment.middle,
      children: [
        TableRow(
          decoration: BoxDecoration(border: Border(
            bottom: BorderSide(color: cs.outlineVariant.withValues(alpha: 0.5)),
          )),
          children: [
            hcell('Time'), hcell('Phase'), hcell(''), hcell('Status'),
            hcell('Duration', a: TextAlign.right), hcell('Error'),
          ],
        ),
        ...runs.map((r) {
          final ok      = r.status == 'done';
          final isErr   = r.status == 'error';
          final icon    = ok ? '✓' : (isErr ? '✗' : '·');
          final icColor = ok ? cs.primary : (isErr ? cs.error : cs.onSurfaceVariant);
          final err     = (!ok && r.errorMessage != null && r.errorMessage!.isNotEmpty)
              ? r.errorMessage! : '';
          return TableRow(children: [
            cell(_fmtTs(r.startedAt), color: cs.onSurfaceVariant),
            cell(r.phase, bold: true),
            cell(icon, color: icColor),
            cell(r.status),
            cell(r.durationMs != null ? _fmtMs(r.durationMs!) : '—', a: TextAlign.right),
            cell(err, color: err.isNotEmpty ? cs.error : null),
          ]);
        }),
      ],
    );
  }

  // ── LLM Calls table ──────────────────────────────────────────────────────────

  Widget _entriesTable(BuildContext context, List<ActivityEntry> entries) {
    final cs = Theme.of(context).colorScheme;
    const hStyle = TextStyle(fontSize: 10.5, fontWeight: FontWeight.w600, letterSpacing: 0.4);
    const dStyle = TextStyle(fontSize: 11.5, height: 1.6);

    Widget hcell(String t, {TextAlign a = TextAlign.left}) => Padding(
      padding: const EdgeInsets.fromLTRB(4, 2, 14, 5),
      child: Text(t, style: hStyle.copyWith(color: cs.onSurfaceVariant), textAlign: a),
    );
    Widget cell(String t, {TextAlign a = TextAlign.left, Color? color, bool bold = false}) => Padding(
      padding: const EdgeInsets.fromLTRB(4, 2, 14, 2),
      child: Text(t,
        style: dStyle.copyWith(color: color, fontWeight: bold ? FontWeight.w600 : null),
        textAlign: a),
    );

    final totalCost = entries.fold(0.0, (s, e) => s + e.costUsd);
    final totalMs   = entries.fold(0,   (s, e) => s + e.elapsedMs);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Table(
          columnWidths: const {
            0: IntrinsicColumnWidth(),  // time
            1: IntrinsicColumnWidth(),  // phase
            2: IntrinsicColumnWidth(),  // provider
            3: FlexColumnWidth(),       // model
            4: IntrinsicColumnWidth(),  // elapsed
            5: IntrinsicColumnWidth(),  // tokens
            6: IntrinsicColumnWidth(),  // cost
          },
          defaultVerticalAlignment: TableCellVerticalAlignment.middle,
          children: [
            TableRow(
              decoration: BoxDecoration(border: Border(
                bottom: BorderSide(color: cs.outlineVariant.withValues(alpha: 0.5)),
              )),
              children: [
                hcell('Time'), hcell('Phase'), hcell('Provider'), hcell('Model'),
                hcell('Elapsed', a: TextAlign.right),
                hcell('Tokens',  a: TextAlign.right),
                hcell('Cost',    a: TextAlign.right),
              ],
            ),
            ...entries.map((e) {
              final tok = e.provider == 'claude_cli'
                  ? '—'
                  : '${_k(e.inputTokens)}→${_k(e.outputTokens)}';
              final cost      = e.costUsd > 0 ? '\$${e.costUsd.toStringAsFixed(4)}' : '—';
              final modelText = e.thinkingEffort.isNotEmpty && e.thinkingEffort != 'off'
                  ? '${e.model}  [${e.thinkingEffort}]'
                  : e.model;
              return TableRow(children: [
                cell(_fmtTs(e.createdAt), color: cs.onSurfaceVariant),
                cell(e.phase, bold: true),
                cell(e.provider),
                cell(modelText),
                cell(_fmtMs(e.elapsedMs), a: TextAlign.right),
                cell(tok,  a: TextAlign.right),
                cell(cost, a: TextAlign.right),
              ]);
            }),
          ],
        ),
        const Divider(height: 20),
        Padding(
          padding: const EdgeInsets.fromLTRB(4, 0, 4, 2),
          child: Text(
            'Total  ${entries.length} calls  ${_fmtMs(totalMs)}  \$${totalCost.toStringAsFixed(4)}',
            style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w600),
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;

    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(child: Text('Error: $_error', style: TextStyle(color: cs.error)));
    }

    final runs    = _runs    ?? [];
    final entries = _entries ?? [];

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (runs.isEmpty && entries.isEmpty)
            Text(
              'No activity recorded for this vacancy yet.',
              style: Theme.of(context).textTheme.bodyMedium
                  ?.copyWith(color: cs.onSurfaceVariant),
            )
          else ...[
            if (runs.isNotEmpty) ...[
              _section(context, 'PIPELINE RUNS', _runsTable(context, runs)),
              const SizedBox(height: 16),
            ],
            if (entries.isNotEmpty)
              _section(context, 'LLM CALLS', _entriesTable(context, entries)),
          ],
          const SizedBox(height: 8),
          TextButton.icon(
            onPressed: () { setState(() { _loading = true; _error = null; }); _load(); },
            icon: const Icon(Icons.refresh, size: 16),
            label: const Text('Refresh'),
          ),
        ],
      ),
    );
  }
}

// ── Action bar ────────────────────────────────────────────────────────────────

class _ActionBar extends ConsumerStatefulWidget {
  final int vacancyId;
  final String url;
  final String role;
  final String status;
  final VacancyListItem? vacancy;
  final TabController tabController;

  const _ActionBar({
    required this.vacancyId,
    required this.url,
    required this.role,
    required this.tabController,
    this.status = 'analyzed',
    this.vacancy,
  });

  @override
  ConsumerState<_ActionBar> createState() => _ActionBarState();
}

class _ActionBarState extends ConsumerState<_ActionBar> {
  bool _loadingCv = false;
  bool _loadingAnalyze = false;
  bool _loadingDecline = false;
  bool _loadingRestore = false;
  bool _loadingReset = false;
  late bool _starred;
  late bool _applied;
  bool _loadingStar = false;
  bool _loadingApplied = false;
  bool _refreshing = false;

  @override
  void initState() {
    super.initState();
    _starred = widget.vacancy?.starred ?? false;
    _applied = widget.vacancy?.applied ?? false;
  }

  @override
  void didUpdateWidget(_ActionBar old) {
    super.didUpdateWidget(old);
    if (old.vacancy?.starred != widget.vacancy?.starred) _starred = widget.vacancy?.starred ?? false;
    if (old.vacancy?.applied != widget.vacancy?.applied) _applied = widget.vacancy?.applied ?? false;
  }

  VacancyRepository get _repo {
    final apiUrl = ref.read(settingsProvider).valueOrNull?.apiUrl ?? 'http://localhost:8080';
    return VacancyRepository(baseUrl: apiUrl);
  }

  Future<void> _refresh() async {
    setState(() => _refreshing = true);
    try {
      ref.invalidate(vacancyListProvider);
      ref.invalidate(vacancyDetailProvider(widget.vacancyId));
      ref.invalidate(vacancyCvProvider(widget.vacancyId));
      ref.invalidate(vacancyJdProvider(widget.vacancyId));
    } finally {
      if (mounted) setState(() => _refreshing = false);
    }
  }

  Future<void> _toggleStar() async {
    if (_loadingStar) return;
    final next = !_starred;
    setState(() { _starred = next; _loadingStar = true; });
    try {
      await _repo.setStarred(widget.vacancyId, next);
      if (mounted) ref.read(vacancyListProvider.notifier).refresh();
    } catch (_) {
      if (mounted) setState(() => _starred = !next);
    } finally {
      if (mounted) setState(() => _loadingStar = false);
    }
  }

  Future<void> _toggleApplied() async {
    if (_loadingApplied) return;
    final next = !_applied;
    setState(() { _applied = next; _loadingApplied = true; });
    try {
      await _repo.setApplied(widget.vacancyId, next);
      if (mounted) ref.read(vacancyListProvider.notifier).refresh();
    } catch (_) {
      if (mounted) setState(() => _applied = !next);
    } finally {
      if (mounted) setState(() => _loadingApplied = false);
    }
  }

  Future<void> _generateCv({String language = 'auto'}) async {
    setState(() => _loadingCv = true);
    try {
      await _repo.generateCv(widget.vacancyId, language: language);
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

  Future<void> _resetAndRetry() async {
    setState(() => _loadingReset = true);
    try {
      await _repo.reset(widget.vacancyId);
      await _repo.analyze(widget.vacancyId);
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
        ref.invalidate(vacancyDetailProvider(widget.vacancyId));
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Reset & queued for analysis'), duration: Duration(seconds: 2)),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
      }
    } finally {
      if (mounted) setState(() => _loadingReset = false);
    }
  }

  Future<void> _generateCover() async {
    setState(() => _loadingCv = true);
    try {
      await _repo.generateCover(widget.vacancyId);
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Cover generation queued'), duration: Duration(seconds: 2)),
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

  Future<void> _downloadPdf(String type) async {
    final messenger = ScaffoldMessenger.of(context);
    messenger.showSnackBar(
      const SnackBar(content: Text('Preparing PDF...'), duration: Duration(minutes: 1)),
    );
    try {
      final bytes = type == 'cv'
          ? await _repo.getCvPdfBytes(widget.vacancyId)
          : await _repo.getCoverPdfBytes(widget.vacancyId);
      messenger.hideCurrentSnackBar();
      if (!mounted) return;
      final label = type == 'cv' ? 'CV' : 'Cover Letter';
      final fileName = '${type == 'cv' ? 'CV' : 'Cover'}_${widget.vacancyId}.pdf';
      final path = await FilePicker.platform.saveFile(
        dialogTitle: 'Save $label PDF',
        fileName: fileName,
        type: FileType.custom,
        allowedExtensions: ['pdf'],
        bytes: bytes,
      );
      if (path != null) {
        await File(path).writeAsBytes(bytes, flush: true);
        if (mounted) {
          messenger.showSnackBar(
            SnackBar(content: Text('Saved: $path'), duration: const Duration(seconds: 3)),
          );
        }
      }
    } catch (e) {
      messenger.hideCurrentSnackBar();
      if (mounted) {
        messenger.showSnackBar(
          SnackBar(
            content: Text('PDF error: $e'),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
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

  Widget _buildCta(BuildContext context, ColorScheme cs, AsyncValue<VacancyCv> cvAsync, {required bool workerAvailable}) {
    final tab = widget.tabController.index;
    final isDeclined = widget.status == 'declined';
    final isCvInProgress = widget.status == 'cv_queued' || widget.status == 'cv_generating';

    if (isDeclined) {
      if (tab == 0) {
        return OutlinedButton.icon(
          onPressed: _loadingRestore ? null : _restore,
          icon: _loadingRestore
              ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.inbox_outlined, size: 16),
          label: const Text('Restore to Inbox'),
          style: OutlinedButton.styleFrom(
            side: BorderSide(color: cs.primary.withValues(alpha: 0.5)),
            foregroundColor: cs.primary,
          ),
        );
      }
      return const SizedBox.shrink();
    }

    switch (tab) {
      case 0: // Analysis
        final isStuck = widget.status == 'analyzing';
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (!isStuck) ...[
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
              Tooltip(
                message: workerAvailable ? '' : 'Analysis worker unavailable — start agent.py',
                child: FilledButton.icon(
                  onPressed: _loadingAnalyze || !workerAvailable ? null : _analyze,
                  icon: _loadingAnalyze
                      ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.refresh_rounded, size: 16),
                  label: Text(_loadingAnalyze ? 'Queuing...' : 'Re-analyze'),
                ),
              ),
            ] else ...[
              Tooltip(
                message: 'Reset stuck analysis and retry from scratch',
                child: FilledButton.icon(
                  onPressed: _loadingReset ? null : _resetAndRetry,
                  style: FilledButton.styleFrom(backgroundColor: Colors.orange.shade700),
                  icon: _loadingReset
                      ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.restart_alt_rounded, size: 16),
                  label: Text(_loadingReset ? 'Resetting...' : 'Reset & Retry'),
                ),
              ),
            ],
          ],
        );

      case 1: // CV
        final hasCv = cvAsync.valueOrNull?.hasCv ?? false;
        return _SplitButton(
          label: isCvInProgress ? 'Generating...' : (hasCv ? 'Regenerate CV' : 'Generate CV'),
          icon: Icons.description_outlined,
          loading: _loadingCv || isCvInProgress,
          onPressed: (isCvInProgress || _loadingCv) ? null : _generateCv,
          menuItems: [
            MenuItemButton(
              onPressed: (isCvInProgress || _loadingCv) ? null : () => _generateCv(language: 'en'),
              leadingIcon: const Icon(Icons.translate, size: 16),
              child: const Text('Generate in English'),
            ),
            MenuItemButton(
              onPressed: (isCvInProgress || _loadingCv) ? null : () => _generateCv(language: 'uk'),
              leadingIcon: const Icon(Icons.translate, size: 16),
              child: const Text('Generate in Ukrainian'),
            ),
            MenuItemButton(
              onPressed: hasCv && !isCvInProgress ? () => _downloadPdf('cv') : null,
              leadingIcon: const Icon(Icons.picture_as_pdf_outlined, size: 16),
              child: const Text('Download PDF'),
            ),
          ],
        );

      case 2: // Cover
        final hasCover = cvAsync.valueOrNull?.hasCover ?? false;
        final isCoverInProgress = widget.status == 'cover_generating';
        return _SplitButton(
          label: isCoverInProgress ? 'Generating...' : (hasCover ? 'Regenerate Cover' : 'Generate Cover'),
          icon: Icons.mail_outline,
          loading: _loadingCv || isCoverInProgress,
          onPressed: (isCoverInProgress || _loadingCv) ? null : _generateCover,
          menuItems: hasCover
              ? [
                  MenuItemButton(
                    onPressed: () => _downloadPdf('cover'),
                    leadingIcon: const Icon(Icons.picture_as_pdf_outlined, size: 16),
                    child: const Text('Download PDF'),
                  ),
                ]
              : [],
        );

      default: // Activity
        return const SizedBox.shrink();
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final cvAsync = ref.watch(vacancyCvProvider(widget.vacancyId));
    final health = ref.watch(healthProvider).valueOrNull ?? HealthStatus.checking;
    final workerAvailable = health == HealthStatus.online;

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
          // Star toggle
          Tooltip(
            message: _starred ? 'Remove from favourites' : 'Add to favourites',
            child: IconButton(
              icon: Icon(
                _starred ? Icons.star_rounded : Icons.star_outline_rounded,
                size: 20,
                color: _starred ? const Color(0xFFFFB300) : cs.onSurfaceVariant,
              ),
              onPressed: _toggleStar,
              splashRadius: 18,
            ),
          ),
          // Applied toggle
          Tooltip(
            message: _applied ? 'Mark as not applied' : 'Mark as applied',
            child: _applied
                ? FilledButton.icon(
                    onPressed: _loadingApplied ? null : _toggleApplied,
                    icon: const Icon(Icons.check_circle, size: 16),
                    label: const Text('Applied'),
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF2E7D32),
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      minimumSize: const Size(0, 36),
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                  )
                : OutlinedButton.icon(
                    onPressed: _loadingApplied ? null : _toggleApplied,
                    icon: const Icon(Icons.check_circle_outline, size: 16),
                    label: const Text('Applied?'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: cs.onSurfaceVariant,
                      side: BorderSide(color: cs.outlineVariant),
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      minimumSize: const Size(0, 36),
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                  ),
          ),
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
          // Open vacancy folder in Explorer
          if (widget.vacancy?.folderPath != null)
            IconButton(
              icon: Icon(Icons.folder_open_outlined, size: 18, color: cs.onSurfaceVariant),
              tooltip: 'Open folder',
              onPressed: () => Process.run('explorer.exe', [widget.vacancy!.folderPath!]),
            ),
          Tooltip(
            message: 'Refresh vacancy data',
            child: IconButton(
              icon: _refreshing
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Icon(Icons.sync_rounded, size: 18, color: cs.onSurfaceVariant),
              onPressed: _refreshing ? null : _refresh,
            ),
          ),
          const SizedBox(width: 4),
          // Context-sensitive CTA — changes per tab
          AnimatedBuilder(
            animation: widget.tabController,
            builder: (context, _) => _buildCta(context, cs, cvAsync, workerAvailable: workerAvailable),
          ),
        ],
      ),
    );
  }
}

// ── Hero header — role icon + title + recommendation card + compact scores ─────

class _VacancyHero extends StatelessWidget {
  final Phase1Data? p1;
  final Phase2Data p2;
  final VacancyListItem? vacancy;
  final int vacancyId;
  final String? salary;
  final Future<void> Function(String)? onSalaryChanged;

  const _VacancyHero({
    required this.p1,
    required this.p2,
    required this.vacancyId,
    this.vacancy,
    this.salary,
    this.onSalaryChanged,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final role    = p1?.role.isNotEmpty == true ? p1!.role : (vacancy?.role ?? '');
    final company = p1?.company.isNotEmpty == true ? p1!.company : (vacancy?.company ?? '');
    final publishedAt = vacancy?.publishedAt;
    final updatedAt   = vacancy?.updatedAt;
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
                  const SizedBox(height: 6),
                  if (onSalaryChanged != null)
                    _SalaryInline(salary: salary, onSave: onSalaryChanged!),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 20),
        // Recommendation card — primary go/no-go decision
        _RecommendationCard(
          recommendation: p2.recommendation,
          recommendationLabel: p2.recommendationLabel,
          whoTheyWant: p2.whoTheyWant,
        ),
        const SizedBox(height: 12),
        // Score dot rows + date pinned right
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Tooltip(
                    message: 'Candidate-to-role fit across domain, execution,\nstrategy, systems & stakeholder (0–10)',
                    child: _ScoreDotsRow(label: 'Fit', score: p2.fitScore.toDouble(), max: 10),
                  ),
                  if (p1 != null) ...[
                    const SizedBox(height: 5),
                    Tooltip(
                      message: 'How attractive this role is for you —\nseniority, company tier, scope, compensation (0–10)',
                      child: _ScoreDotsRow(label: 'Attraction', score: p1!.vacancyScore, max: 10),
                    ),
                  ],
                ],
              ),
            ),
            if (publishedAt != null || updatedAt != null) ...[
              const SizedBox(width: 8),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  if (publishedAt != null)
                    _PostedChip(publishedAt: publishedAt, cs: cs),
                  if (updatedAt != null) ...[
                    if (publishedAt != null) const SizedBox(height: 4),
                    _AnalyzedChip(updatedAt: updatedAt, cs: cs),
                  ],
                ],
              ),
            ],
          ],
        ),
        // Pre-filter result — deprioritized here vs _JdModeView's prominent
        // placement: Phase 2's full analysis (above) is now the primary
        // signal, this is supplementary context, not the headline (2026-07-17).
        _PrefilterBanner(
          blocked: vacancy?.blockerFlag ?? false,
          checked: vacancy?.blockerChecked ?? false,
          reasons: vacancy?.blockerReasons ?? const [],
          compact: true,
        ),
      ],
    );
  }
}

/// Persistent pre-filter result — replaces the old "show a modal after
/// clicking Check blockers" pattern (found unreliable/easy-to-miss in
/// practice, 2026-07-17): the result is now driven by the vacancy's own
/// blocker_flag/blocker_reasons (survives navigation/reload), shown inline
/// wherever the vacancy is displayed. Renders nothing when not blocked —
/// a clean pre-filter result isn't noteworthy enough to take up space.
class _PrefilterBanner extends StatelessWidget {
  final bool blocked;
  final bool checked;
  final List<String> reasons;
  final bool compact;
  final VoidCallback? onTapDetails;

  const _PrefilterBanner({
    required this.blocked,
    required this.checked,
    required this.reasons,
    this.compact = false,
    this.onTapDetails,
  });

  @override
  Widget build(BuildContext context) {
    // Three distinct states — collapsing "checked, clean" into "nothing to
    // show" (the original design) is exactly the bug found on vacancy #716
    // (2026-07-17): a finished, clean check produced zero visible feedback,
    // indistinguishable from never having checked at all.
    if (!checked) return const SizedBox.shrink();

    final cs = Theme.of(context).colorScheme;
    final bg = blocked ? const Color(0xFFFFEBEE) : const Color(0xFFE8F5E9);
    final border = blocked ? const Color(0xFFE57373) : const Color(0xFF81C784);
    final fg = blocked ? const Color(0xFFC62828) : const Color(0xFF2E7D32);
    final icon = blocked ? Icons.block_rounded : Icons.check_circle_outline_rounded;
    final label = blocked ? 'Possible blocker — pre-filter check' : 'Pre-filter checked — no blockers';

    return Container(
      width: double.infinity,
      margin: EdgeInsets.only(
        left: compact ? 0 : 16,
        right: compact ? 0 : 16,
        top: compact ? 16 : 12,
        bottom: compact ? 0 : 8,
      ),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 15, color: fg),
              const SizedBox(width: 6),
              Text(
                label,
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  color: fg,
                  fontSize: compact ? 11.5 : 12.5,
                ),
              ),
              if (onTapDetails != null) ...[
                const Spacer(),
                InkWell(
                  onTap: onTapDetails,
                  child: Text('Details',
                      style: TextStyle(fontSize: 11, color: cs.primary, decoration: TextDecoration.underline)),
                ),
              ],
            ],
          ),
          if (blocked) ...[
            const SizedBox(height: 6),
            ...reasons.map((r) => Padding(
                  padding: const EdgeInsets.only(bottom: 3),
                  child: _reasonLine(r, style: TextStyle(fontSize: compact ? 11.5 : 12.5)),
                )),
          ],
        ],
      ),
    );
  }
}

class _ScoreDotsRow extends StatelessWidget {
  final String label;
  final double score;
  final double max;

  const _ScoreDotsRow({required this.label, required this.score, required this.max});

  Color _filledColor() {
    final ratio = score / max;
    if (ratio >= 0.70) return const Color(0xFF388E3C);
    if (ratio >= 0.40) return const Color(0xFFF57F17);
    return const Color(0xFFB71C1C);
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final filled = score.round().clamp(0, max.toInt());
    final filledColor = _filledColor();
    final emptyColor = cs.surfaceContainerHighest;
    final scoreText = score % 1 == 0 ? '${score.toInt()}' : score.toStringAsFixed(1);

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        SizedBox(
          width: 72,
          child: Text(label,
              style: Theme.of(context)
                  .textTheme
                  .labelSmall
                  ?.copyWith(color: cs.onSurfaceVariant)),
        ),
        ...List.generate(
          max.toInt(),
          (i) => Container(
            width: 8,
            height: 8,
            margin: const EdgeInsets.only(right: 3),
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: i < filled ? filledColor : emptyColor,
            ),
          ),
        ),
        const SizedBox(width: 6),
        Text(scoreText,
            style: Theme.of(context)
                .textTheme
                .labelSmall
                ?.copyWith(color: cs.onSurface, fontWeight: FontWeight.w600)),
      ],
    );
  }
}

class _RecommendationCard extends StatelessWidget {
  final String recommendation;
  final String recommendationLabel;
  final String whoTheyWant;

  const _RecommendationCard({
    required this.recommendation,
    required this.recommendationLabel,
    this.whoTheyWant = '',
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
                if (whoTheyWant.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Tooltip(
                    message: 'The ideal candidate archetype this vacancy targets',
                    preferBelow: true,
                    child: SelectableText(
                      whoTheyWant,
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                            color: cs.onSurface.withValues(alpha: 0.65),
                          ),
                    ),
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

  String _relativeTime() => relativeTimeFromBackend(publishedAt);

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

class _AnalyzedChip extends StatelessWidget {
  final String updatedAt;
  final ColorScheme cs;

  const _AnalyzedChip({required this.updatedAt, required this.cs});

  static DateTime _asUtc(String iso) => parseBackendUtc(iso).toLocal();

  String _fmtLocal() {
    try {
      final dt  = _asUtc(updatedAt);
      final dd  = dt.day.toString().padLeft(2, '0');
      final mm  = dt.month.toString().padLeft(2, '0');
      final yy  = dt.year.toString();
      final hh  = dt.hour.toString().padLeft(2, '0');
      final min = dt.minute.toString().padLeft(2, '0');
      return '$dd.$mm.$yy $hh:$min';
    } catch (_) {
      return updatedAt;
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
          Icon(Icons.analytics_outlined, size: 14, color: cs.onSurfaceVariant),
          const SizedBox(width: 4),
          Text(
            'Analyzed ${_fmtLocal()}',
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: cs.onSurfaceVariant,
                ),
          ),
        ],
      ),
    );
  }
}

// ── Salary inline edit ────────────────────────────────────────────────────────

class _SalaryInline extends StatefulWidget {
  final String? salary;
  final Future<void> Function(String) onSave;
  final double fontSize;

  const _SalaryInline({this.salary, required this.onSave, this.fontSize = 12});

  @override
  State<_SalaryInline> createState() => _SalaryInlineState();
}

class _SalaryInlineState extends State<_SalaryInline> {
  bool _editing = false;
  bool _saving = false;
  late TextEditingController _ctrl;
  String? _committedSalary; // tracks last saved value locally

  @override
  void initState() {
    super.initState();
    _committedSalary = widget.salary;
    _ctrl = TextEditingController(text: widget.salary ?? '');
  }

  @override
  void didUpdateWidget(_SalaryInline old) {
    super.didUpdateWidget(old);
    if (old.salary != widget.salary && !_editing) {
      _committedSalary = widget.salary;
      _ctrl.text = widget.salary ?? '';
    }
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final value = _ctrl.text.trim();
    setState(() => _saving = true);
    try {
      await widget.onSave(value);
      if (mounted) setState(() => _committedSalary = value.isEmpty ? null : value);
    } finally {
      if (mounted) setState(() { _saving = false; _editing = false; });
    }
  }

  void _cancel() {
    setState(() { _editing = false; _ctrl.text = _committedSalary ?? ''; });
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;

    if (_editing) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.attach_money, size: widget.fontSize + 2, color: cs.primary),
          const SizedBox(width: 4),
          SizedBox(
            width: 220,
            child: TextField(
              controller: _ctrl,
              autofocus: true,
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: cs.onSurface, fontSize: widget.fontSize),
              decoration: InputDecoration(
                isDense: true,
                contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                hintText: 'e.g. \$3k–5k USD/mo',
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(6)),
              ),
              onSubmitted: (_) => _save(),
            ),
          ),
          const SizedBox(width: 4),
          if (_saving)
            const SizedBox(
              width: 16, height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          else ...[
            IconButton(
              icon: const Icon(Icons.check, size: 16),
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
              onPressed: _save,
              tooltip: 'Save',
            ),
            IconButton(
              icon: const Icon(Icons.close, size: 16),
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
              onPressed: _cancel,
              tooltip: 'Cancel',
            ),
          ],
        ],
      );
    }

    final hasSalary = _committedSalary?.isNotEmpty == true;
    return Tooltip(
      message: 'Click to edit salary',
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        child: GestureDetector(
        onTap: () => setState(() => _editing = true),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.attach_money,
              size: widget.fontSize + 2,
              color: hasSalary ? cs.primary : cs.onSurfaceVariant.withValues(alpha: 0.45),
            ),
            const SizedBox(width: 3),
            Text(
              hasSalary ? _committedSalary! : 'Add salary…',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: hasSalary
                        ? cs.onSurfaceVariant
                        : cs.onSurfaceVariant.withValues(alpha: 0.45),
                    fontStyle: hasSalary ? FontStyle.normal : FontStyle.italic,
                    fontSize: widget.fontSize,
                  ),
            ),
            if (hasSalary) ...[
              const SizedBox(width: 4),
              Icon(Icons.edit, size: widget.fontSize - 1, color: cs.onSurfaceVariant.withValues(alpha: 0.4)),
            ],
          ],
        ),
        ),
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
        p2.keyBarriers.isNotEmpty ||
        p2.hiddenRisks.isNotEmpty ||
        p2.warnings.isNotEmpty;

    if (!hasContent) return const SizedBox.shrink();

    return _SectionCard(
      title: 'Quick Overview',
      tooltip: 'Key signals extracted from the JD —\nwho they want, barriers, hidden risks',
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

// ── Why apply / Why not apply card ───────────────────────────────────────────

class _WhyCard extends StatelessWidget {
  final Phase2Data p2;
  const _WhyCard({required this.p2});

  @override
  Widget build(BuildContext context) {
    if (p2.whyApply.isEmpty && p2.whyNotApply.isEmpty) return const SizedBox.shrink();
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    Widget bullets(List<String> items, Color dotColor) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: items
              .map((item) => Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                          padding: const EdgeInsets.only(top: 5),
                          child: Container(
                            width: 5,
                            height: 5,
                            decoration: BoxDecoration(
                              color: dotColor,
                              shape: BoxShape.circle,
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: SelectableText(
                            item,
                            style: tt.bodySmall?.copyWith(color: cs.onSurface),
                          ),
                        ),
                      ],
                    ),
                  ))
              .toList(),
        );

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
          if (p2.whyApply.isNotEmpty) ...[
            Row(children: [
              Icon(Icons.check_circle_outline_rounded, size: 14, color: const Color(0xFF2E7D32)),
              const SizedBox(width: 6),
              Text('Why apply',
                  style: tt.bodySmall?.copyWith(
                    color: const Color(0xFF2E7D32),
                    fontWeight: FontWeight.w700,
                  )),
            ]),
            const SizedBox(height: 8),
            bullets(p2.whyApply, const Color(0xFF2E7D32)),
          ],
          if (p2.whyApply.isNotEmpty && p2.whyNotApply.isNotEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 10),
              child: Divider(height: 1),
            ),
          if (p2.whyNotApply.isNotEmpty) ...[
            Row(children: [
              Icon(Icons.cancel_outlined, size: 14, color: cs.error),
              const SizedBox(width: 6),
              Text('Why not apply',
                  style: tt.bodySmall?.copyWith(
                    color: cs.error,
                    fontWeight: FontWeight.w700,
                  )),
            ]),
            const SizedBox(height: 8),
            bullets(p2.whyNotApply, cs.error),
          ],
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

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
          child: SelectableText.rich(
            TextSpan(
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

// ── Shared tooltip-aware title chip ──────────────────────────────────────────

class _TooltipTitle extends StatelessWidget {
  final String title;
  final String? tooltip;
  final BuildContext context;
  final ColorScheme cs;

  const _TooltipTitle({
    required this.title,
    required this.tooltip,
    required this.context,
    required this.cs,
  });

  @override
  Widget build(BuildContext ctx) {
    final text = Text(
      title,
      style: Theme.of(ctx).textTheme.labelMedium?.copyWith(color: cs.onSurfaceVariant),
    );
    if (tooltip == null) return text;
    return Tooltip(
      message: tooltip!,
      preferBelow: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          text,
          const SizedBox(width: 4),
          Icon(Icons.info_outline, size: 12, color: cs.onSurfaceVariant.withValues(alpha: 0.55)),
        ],
      ),
    );
  }
}

// ── Section card — bento style ────────────────────────────────────────────────

class _SectionCard extends StatelessWidget {
  final String title;
  final Widget child;
  final String? tooltip;

  const _SectionCard({required this.title, required this.child, this.tooltip});

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
          _TooltipTitle(title: title, tooltip: tooltip, context: context, cs: cs),
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
  final String? tooltip;

  const _CollapsibleSection({
    required this.title,
    required this.child,
    this.initiallyExpanded = false,
    this.tooltip,
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
            mouseCursor: SystemMouseCursors.click,
            borderRadius: BorderRadius.circular(16),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
              child: Row(
                children: [
                  _TooltipTitle(title: widget.title, tooltip: widget.tooltip, context: context, cs: cs),
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

// ── Split action button ───────────────────────────────────────────────────────

class _SplitButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final bool loading;
  final VoidCallback? onPressed;
  final List<MenuItemButton> menuItems;

  const _SplitButton({
    required this.label,
    required this.icon,
    required this.onPressed,
    this.loading = false,
    this.menuItems = const [],
  });

  @override
  Widget build(BuildContext context) {
    const leftRadius = BorderRadius.only(
      topLeft: Radius.circular(20),
      bottomLeft: Radius.circular(20),
    );
    const rightRadius = BorderRadius.only(
      topRight: Radius.circular(20),
      bottomRight: Radius.circular(20),
    );
    const fullRadius = BorderRadius.all(Radius.circular(20));

    final hasMenu = menuItems.isNotEmpty;

    final mainBtn = FilledButton.icon(
      onPressed: loading ? null : onPressed,
      icon: loading
          ? const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
            )
          : Icon(icon, size: 16),
      label: Text(label),
      style: FilledButton.styleFrom(
        shape: RoundedRectangleBorder(
          borderRadius: hasMenu ? leftRadius : fullRadius,
        ),
        minimumSize: const Size(0, 36),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
    );

    if (!hasMenu) return mainBtn;

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        mainBtn,
        Container(width: 1, height: 36, color: Colors.white.withValues(alpha: 0.25)),
        MenuAnchor(
          menuChildren: menuItems,
          builder: (context, controller, _) => FilledButton(
            onPressed: () => controller.isOpen ? controller.close() : controller.open(),
            style: FilledButton.styleFrom(
              shape: const RoundedRectangleBorder(borderRadius: rightRadius),
              minimumSize: const Size(34, 36),
              maximumSize: const Size(34, 36),
              padding: EdgeInsets.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: const Icon(Icons.arrow_drop_down, size: 18, color: Colors.white),
          ),
        ),
      ],
    );
  }
}

// ── CV tab ────────────────────────────────────────────────────────────────────

class _CvTab extends ConsumerWidget {
  final int vacancyId;
  final String status;

  const _CvTab({required this.vacancyId, required this.status});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;

    if (status == 'cv_queued' || status == 'cv_generating') {
      final label = status == 'cv_generating' ? 'Generating CV...' : 'CV in queue...';
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
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant),
            ),
          ],
        ),
      );
    }

    final cvAsync = ref.watch(vacancyCvProvider(vacancyId));
    return cvAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: Text('Failed to load CV: $e', style: TextStyle(color: cs.error)),
      ),
      data: (cv) {
        if (!cv.hasCv) {
          return const _EmptyTabState(
            icon: Icons.description_outlined,
            message: 'CV not generated yet.\nUse Generate CV from the action bar.',
          );
        }
        return Markdown(
          data: cv.cvMd!,
          selectable: true,
          padding: const EdgeInsets.fromLTRB(24, 20, 24, 32),
          styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
            p: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: cs.onSurface,
                  height: 1.6,
                ),
          ),
        );
      },
    );
  }
}

// ── Cover tab ─────────────────────────────────────────────────────────────────

class _CoverTab extends ConsumerWidget {
  final int vacancyId;
  final String status;

  const _CoverTab({required this.vacancyId, required this.status});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cs = Theme.of(context).colorScheme;

    if (status == 'cv_queued' || status == 'cv_generating') {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(color: cs.primary),
            const SizedBox(height: 20),
            Text('CV in progress...', style: Theme.of(context).textTheme.bodyLarge),
            const SizedBox(height: 8),
            Text(
              'Cover letter will be available after CV is generated',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant),
            ),
          ],
        ),
      );
    }

    final cvAsync = ref.watch(vacancyCvProvider(vacancyId));
    return cvAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: Text('Failed to load cover: $e', style: TextStyle(color: cs.error)),
      ),
      data: (cv) {
        if (!cv.hasCover) {
          return const _EmptyTabState(
            icon: Icons.mail_outline,
            message: 'Cover letter not generated yet.',
          );
        }
        return Markdown(
          data: cv.coverMd!,
          selectable: true,
          padding: const EdgeInsets.fromLTRB(24, 20, 24, 32),
          styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
            p: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: cs.onSurface,
                  height: 1.6,
                ),
          ),
        );
      },
    );
  }
}

// ── Empty tab state ───────────────────────────────────────────────────────────

class _EmptyTabState extends StatelessWidget {
  final IconData icon;
  final String message;

  const _EmptyTabState({required this.icon, required this.message});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 48, color: cs.onSurfaceVariant.withValues(alpha: 0.4)),
          const SizedBox(height: 12),
          Text(
            message,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: cs.onSurfaceVariant),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}
