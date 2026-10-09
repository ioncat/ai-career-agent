import 'dart:async';
import 'dart:io';
import 'package:flutter/services.dart' show Clipboard, ClipboardData;
import 'package:file_picker/file_picker.dart';
import 'package:fl_chart/fl_chart.dart';
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
import '../utils/salary_kind.dart';
import '../utils/toast.dart';
import '../utils/analyze_guard.dart';
import '../utils/error_snackbar.dart';

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
  final capitalized = category.isEmpty
      ? category
      : category[0].toUpperCase() + category.substring(1);
  return Text.rich(
    TextSpan(
      style: style,
      children: [
        const TextSpan(text: '•  '),
        TextSpan(
          text: '$capitalized: ',
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        TextSpan(text: rest),
      ],
    ),
  );
}

// ── Shared header pieces (2026-09-07) ───────────────────────────────────────
// Used by both _JdModeView (pre-analysis) and _ActionBar (post-analysis) so
// the vacancy id and the compact title always look and behave identically in
// both states — the whole point of the header-unification pass: fix once,
// works everywhere. See docs/discovery/vacancy-detail-header-unification-
// 2026-09-06.md for the full design rationale (gitignored, local only).

/// Vacancy id — always its own dedicated line, never sharing a row with
/// anything else, in both pre- and post-analysis states. User's own framing
/// (2026-09-07): "это важная штука, должна быть на самом видном месте,
/// всегда в одном и том же месте" — quick self-orientation ("what vacancy
/// am I even looking at") shouldn't depend on which state you're in.
class _VacancyIdLine extends StatelessWidget {
  final int vacancyId;
  const _VacancyIdLine({required this.vacancyId});

  void _copyId(BuildContext context) {
    // Copied value deliberately excludes the leading "#" (2026-09-23, user
    // request) — the id is pasted elsewhere as a bare number (search boxes,
    // scripts, chat), where the "#" would just have to be stripped again.
    Clipboard.setData(ClipboardData(text: '$vacancyId'));
    showToast(context, 'ID copied');
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Tooltip(
        message: 'Copy ID',
        child: InkWell(
          borderRadius: BorderRadius.circular(4),
          onTap: () => _copyId(context),
          child: Text(
            '#$vacancyId',
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
              color: cs.onSurfaceVariant.withValues(alpha: 0.7),
            ),
          ),
        ),
      ),
    );
  }
}

/// Compact title (role + company + website icon) — Variant A from the
/// header-unification design doc. Rendered in the sticky header in BOTH
/// states so the title never scrolls out of view post-analysis the way it
/// used to (it lived only in the scrollable _VacancyHero before). The rich
/// hero treatment (tag badges, large 28px title, radar chart, inline-
/// editable salary/tags) stays exactly where it is today — this compact
/// line does not replace it, it just guarantees an always-visible anchor.
class _VacancyCompactTitle extends StatelessWidget {
  final String role;
  final String company;
  final String? companyWebsite;
  const _VacancyCompactTitle({
    required this.role,
    required this.company,
    this.companyWebsite,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    if (role.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          role,
          style: Theme.of(context).textTheme.titleSmall,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        if (company.isNotEmpty)
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Flexible(
                child: Text(
                  company,
                  style: Theme.of(
                    context,
                  ).textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (companyWebsite != null && companyWebsite!.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(left: 4),
                  child: Tooltip(
                    message: companyWebsite!,
                    child: InkWell(
                      onTap: () => launchUrl(
                        Uri.parse(companyWebsite!),
                        mode: LaunchMode.externalApplication,
                      ),
                      child: Icon(Icons.language, size: 14, color: cs.primary),
                    ),
                  ),
                ),
            ],
          ),
      ],
    );
  }
}

// ── JD mode — shown for status='fetched' ──────────────────────────────────────

class _JdModeView extends ConsumerStatefulWidget {
  final int vacancyId;
  final String url;
  final VacancyListItem? vacancy;

  /// When true: show "Restore to Inbox" instead of Analyze/Skip (used for declined-no-analysis).
  final bool restoreMode;
  final VoidCallback? onSkipped;
  final VoidCallback? onApplied;

  const _JdModeView({
    super.key,
    required this.vacancyId,
    required this.url,
    this.vacancy,
    this.restoreMode = false,
    this.onSkipped,
    this.onApplied,
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
  bool _loadingRefetch = false;
  // Kept for the "View details" affordance on _PrefilterBanner — the modal
  // is no longer shown automatically (found unreliable/easy-to-miss in
  // practice, 2026-07-17) but raw_output/error are still worth a drill-down.
  Map<String, dynamic>? _lastPrefilterResult;

  // Applied toggle (2026-09-02) — a fit worth applying to sometimes gets
  // submitted before or without ever running Phase 1+2 analysis here (e.g.
  // applied via LinkedIn Easy Apply, or on a whim before triage). Previously
  // "Applied" only existed in the post-analysis tabbed _ActionBar, so a vacancy
  // stuck in Inbox had no way to record that outside a DB edit.
  late bool _applied;
  bool _loadingApplied = false;

  // Star toggle (2026-09-07, header unification) — same reasoning as Applied
  // above: favouriting is a global function, shouldn't be gated on whether a
  // vacancy has been analyzed yet. Mirrors _ActionBarState's implementation
  // exactly (same repo call, same optimistic-update-then-revert-on-error
  // pattern).
  late bool _starred;
  bool _loadingStar = false;

  @override
  void initState() {
    super.initState();
    _applied = widget.vacancy?.applied ?? false;
    _starred = widget.vacancy?.starred ?? false;
  }

  @override
  void didUpdateWidget(_JdModeView old) {
    super.didUpdateWidget(old);
    if (old.vacancy?.applied != widget.vacancy?.applied)
      _applied = widget.vacancy?.applied ?? false;
    if (old.vacancy?.starred != widget.vacancy?.starred)
      _starred = widget.vacancy?.starred ?? false;
  }

  Future<void> _toggleStar() async {
    if (_loadingStar) return;
    final next = !_starred;
    setState(() {
      _starred = next;
      _loadingStar = true;
    });
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
    setState(() {
      _applied = next;
      _loadingApplied = true;
    });
    try {
      await _repo.setApplied(widget.vacancyId, next);
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
        // Same relocate-on-toggle-ON convention as the tabbed view's
        // _ActionBar — Applied moves the card, so keyboard selection should
        // advance the same way Skip/Delete already do.
        if (next) widget.onApplied?.call();
      }
    } catch (_) {
      if (mounted) setState(() => _applied = !next);
    } finally {
      if (mounted) setState(() => _loadingApplied = false);
    }
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

  VacancyRepository get _repo {
    final apiUrl =
        ref.read(settingsProvider).valueOrNull?.apiUrl ??
        'http://localhost:8080';
    return VacancyRepository(baseUrl: apiUrl);
  }

  Future<void> _analyze() async {
    setState(() => _loadingAnalyze = true);
    try {
      // Asks "Already applied as #X. Analyze anyway?" when a duplicate of this
      // job was already applied to; false = the user said no.
      final queued = await analyzeWithAppliedGuard(
        context,
        _repo,
        widget.vacancyId,
      );
      if (!queued) return;
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
        showToast(context, 'Analysis queued');
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, 'Error: $e');
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
        final providerUnavailable =
            result['provider_unavailable'] as bool? ?? false;
        if (providerUnavailable || !ok) {
          // Real failure — show the actual reason and keep it on screen
          // until the user closes it (see showErrorSnackBar docstring).
          final reason = result['error'] ?? 'unknown error';
          showErrorSnackBar(
            context,
            providerUnavailable
                ? 'LLM provider unavailable: $reason'
                : 'Check failed: $reason',
          );
        } else {
          final msg = blocked
              ? 'Possible blocker found — see below'
              : 'Checked — no blockers found';
          showToast(context, msg);
        }
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, 'Error: $e');
      }
    } finally {
      if (mounted) setState(() => _loadingPrefilter = false);
    }
  }

  /// Manual "Re-fetch from source" (2026-09-04) — re-pulls the JD directly
  /// from its posting URL, bypassing both the cached JD.md and the RSS feed.
  /// For a vacancy fetched before the job board finished moderating it
  /// (found live, vacancy #1471: DOU still showed "Перевіряється" in the
  /// title at fetch time) — lets the user force a fresh pull instead of
  /// waiting for job-monitor to notice a republish on its own.
  Future<void> _refetchFromSource() async {
    setState(() => _loadingRefetch = true);
    try {
      final result = await _repo.refetchFromSource(widget.vacancyId);
      if (mounted) {
        ref.invalidate(vacancyDetailProvider(widget.vacancyId));
        ref.invalidate(vacancyJdProvider(widget.vacancyId));
        ref.read(vacancyListProvider.notifier).refresh();
        final ok = result['ok'] as bool? ?? false;
        final blocked = result['blocked'] as bool? ?? false;
        final String msg;
        if (!ok) {
          msg = 'Re-fetch failed: ${result['error']}';
        } else {
          final changed = (result['changed_fields'] as List<dynamic>? ?? [])
              .join(', ');
          msg = blocked
              ? 'Re-fetched — possible blocker found'
              : (changed.isEmpty
                    ? 'Re-fetched — content unchanged'
                    : 'Re-fetched — updated: $changed');
        }
        showToast(
          context,
          msg,
          kind: ok ? ToastKind.info : ToastKind.error,
        );
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, 'Error: $e');
      }
    } finally {
      if (mounted) setState(() => _loadingRefetch = false);
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
    final providerUnavailable =
        result['provider_unavailable'] as bool? ?? false;

    final title = providerUnavailable
        ? '🔌 Provider unavailable'
        : (!ok
              ? '❌ Check failed'
              : (blocked ? '⚠️ Possible blocker found' : '✅ No blockers'));

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
                  Text(
                    error ?? 'Unknown error',
                    style: TextStyle(color: Theme.of(ctx).colorScheme.error),
                  ),
                  const SizedBox(height: 8),
                  if (providerUnavailable)
                    Text(
                      "The LLM provider configured for this phase couldn't be reached "
                      '(service not running, down, or rate-limited). Check it\'s running, '
                      'or switch provider in Settings → Advanced: Per-Phase Routing.',
                      style: Theme.of(ctx).textTheme.bodySmall,
                    )
                  else
                    Text(
                      'Full record (model, tokens, timing, or lack thereof) is in the Activity tab.',
                      style: Theme.of(ctx).textTheme.bodySmall,
                    ),
                ] else if (blocked)
                  ...reasons.map(
                    (r) => Padding(
                      padding: const EdgeInsets.only(bottom: 6),
                      child: _reasonLine(r),
                    ),
                  )
                else
                  const Text(
                    'The pre-filter found no explicit conflict with your Critical Blockers.',
                  ),
                if (rawOutput != null && rawOutput.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  ExpansionTile(
                    tilePadding: EdgeInsets.zero,
                    title: Text(
                      'Raw model output',
                      style: Theme.of(ctx).textTheme.labelMedium,
                    ),
                    children: [
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: Theme.of(
                            ctx,
                          ).colorScheme.surfaceContainerHighest,
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: SelectableText(
                          rawOutput,
                          style: const TextStyle(
                            fontSize: 11.5,
                            fontFamily: 'monospace',
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Close'),
          ),
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
                    Text(
                      'Activity — Vacancy #${widget.vacancyId}',
                      style: Theme.of(ctx).textTheme.titleMedium,
                    ),
                    const Spacer(),
                    IconButton(
                      icon: const Icon(Icons.close),
                      onPressed: () => Navigator.of(ctx).pop(),
                    ),
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
        showErrorSnackBar(context, 'Error: $e');
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
        showToast(context, 'Moved to inbox', kind: ToastKind.notice);
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, 'Error: $e');
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
    final companyWebsite = widget.vacancy?.companyWebsite;
    final health =
        ref.watch(healthProvider).valueOrNull ?? HealthStatus.checking;
    final workerAvailable = health == HealthStatus.online;

    return Column(
      children: [
        // Action bar
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: cs.surfaceContainerLowest.withValues(alpha: 0.9),
            border: Border(
              bottom: BorderSide(
                color: cs.outlineVariant.withValues(alpha: 0.15),
              ),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Vacancy id + compact title — shared with _ActionBar
              // (2026-09-07 header unification), always their own lines,
              // never sharing a row with the action controls below.
              _VacancyIdLine(vacancyId: widget.vacancyId),
              _VacancyCompactTitle(
                role: role,
                company: company,
                companyWebsite: companyWebsite,
              ),
              const SizedBox(height: 8),
              // Single Wrap for every action — icons and buttons together
              // (2026-09-07, header unification). Previously an icon Row and
              // a button Wrap were two separately-aligned widgets that had
              // to be kept in sync by hand; that broke 4 times (2026-09-05
              // x3, 2026-09-06 x1) because nothing structurally tied their
              // alignment together. One Wrap removes the failure mode
              // entirely — there is nothing left to desync.
              Wrap(
                alignment: WrapAlignment.start,
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: 8,
                runSpacing: 8,
                children: [
                  // Star — global function, everywhere (2026-09-07, user
                  // request), matching _ActionBar's convention of Star first.
                  Tooltip(
                    message: _starred
                        ? 'Remove from favourites'
                        : 'Add to favourites',
                    child: IconButton(
                      icon: Icon(
                        _starred
                            ? Icons.star_rounded
                            : Icons.star_outline_rounded,
                        size: 20,
                        color: _starred
                            ? const Color(0xFFFFB300)
                            : cs.onSurfaceVariant,
                      ),
                      onPressed: _toggleStar,
                      splashRadius: 18,
                    ),
                  ),
                  // Open JD — moved right after Star (2026-09-07, user
                  // request: "Звездочка, открыть ссылку на вакансию,
                  // вертикальный разделитель"). Was in the trailing utility
                  // cluster before.
                  if (widget.url.isNotEmpty)
                    IconButton(
                      icon: Icon(
                        Icons.open_in_new,
                        size: 18,
                        color: cs.onSurfaceVariant,
                      ),
                      tooltip: 'Open JD',
                      onPressed: () => launchUrl(
                        Uri.parse(widget.url),
                        mode: LaunchMode.externalApplication,
                      ),
                    ),
                  Container(width: 1, height: 24, color: cs.outlineVariant),
                  // Skip moved leftmost of this button cluster (2026-09-04,
                  // user request) — it's the heaviest-used action on this
                  // pre-analysis phase and Applied? sitting first was in the way.
                  if (widget.restoreMode)
                    OutlinedButton.icon(
                      onPressed: _loadingRestore ? null : _restore,
                      icon: _loadingRestore
                          ? const SizedBox(
                              width: 14,
                              height: 14,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.inbox_outlined, size: 16),
                      label: const Text('Restore to Inbox'),
                      style: OutlinedButton.styleFrom(
                        side: BorderSide(
                          color: cs.primary.withValues(alpha: 0.5),
                        ),
                        foregroundColor: cs.primary,
                        padding: const EdgeInsets.symmetric(horizontal: 12),
                        minimumSize: const Size(0, 36),
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                    )
                  else
                    OutlinedButton(
                      onPressed: _loadingDecline ? null : _decline,
                      style: OutlinedButton.styleFrom(
                        side: BorderSide(color: cs.error),
                        foregroundColor: cs.error,
                        padding: const EdgeInsets.symmetric(horizontal: 12),
                        minimumSize: const Size(0, 36),
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                      child: _loadingDecline
                          ? const SizedBox(
                              width: 14,
                              height: 14,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Skip'),
                    ),
                  // Divider after Skip removed (2026-09-07, user request) —
                  // the new divider after Star+Open JD already marks the
                  // "identity/global" cluster apart from the workflow
                  // buttons; a second one here was redundant.
                  // Applied toggle — same affordance the tabbed post-analysis
                  // view has always had, now also reachable pre-analysis
                  // (2026-09-02): applying happens outside this pipeline
                  // sometimes (LinkedIn Easy Apply, a quick manual submission
                  // before triage), and there was previously no way to record
                  // that without leaving Inbox first.
                  Tooltip(
                    message: _applied
                        ? 'Mark as not applied'
                        : 'Mark as applied',
                    child: _applied
                        ? FilledButton.icon(
                            onPressed: _loadingApplied ? null : _toggleApplied,
                            icon: const Icon(Icons.check_circle, size: 16),
                            label: const Text('Applied'),
                            style: FilledButton.styleFrom(
                              backgroundColor: const Color(0xFF2E7D32),
                              padding: const EdgeInsets.symmetric(
                                horizontal: 12,
                              ),
                              minimumSize: const Size(0, 36),
                              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                            ),
                          )
                        : OutlinedButton.icon(
                            onPressed: _loadingApplied ? null : _toggleApplied,
                            icon: const Icon(
                              Icons.check_circle_outline,
                              size: 16,
                            ),
                            label: const Text('Applied?'),
                            style: OutlinedButton.styleFrom(
                              foregroundColor: cs.onSurfaceVariant,
                              side: BorderSide(color: cs.outlineVariant),
                              padding: const EdgeInsets.symmetric(
                                horizontal: 12,
                              ),
                              minimumSize: const Size(0, 36),
                              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                            ),
                          ),
                  ),
                  if (!widget.restoreMode) ...[
                    Tooltip(
                      message:
                          'Run the critical-blocker pre-filter manually (EPIC-27) — not auto-triggered yet',
                      child: OutlinedButton.icon(
                        onPressed: _loadingPrefilter ? null : _checkBlockers,
                        icon: _loadingPrefilter
                            ? const SizedBox(
                                width: 14,
                                height: 14,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Icon(Icons.block_outlined, size: 16),
                        label: const Text('Check blockers'),
                        style: OutlinedButton.styleFrom(
                          side: BorderSide(color: cs.outlineVariant),
                          foregroundColor: cs.onSurfaceVariant,
                          padding: const EdgeInsets.symmetric(horizontal: 12),
                          minimumSize: const Size(0, 36),
                          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        ),
                      ),
                    ),
                    Tooltip(
                      message: workerAvailable
                          ? ''
                          : 'Analysis worker unavailable — start agent.py',
                      child: FilledButton.icon(
                        onPressed: _loadingAnalyze || !workerAvailable
                            ? null
                            : _analyze,
                        icon: _loadingAnalyze
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: Colors.white,
                                ),
                              )
                            : const Icon(Icons.analytics_outlined, size: 16),
                        label: const Text('Analyze'),
                        style: FilledButton.styleFrom(
                          padding: const EdgeInsets.symmetric(horizontal: 12),
                          minimumSize: const Size(0, 36),
                          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        ),
                      ),
                    ),
                  ],
                  // Utility/secondary actions — deliberately last in the Wrap
                  // (2026-09-07), lower visual priority than the workflow
                  // buttons above. Open JD moved out of this cluster to
                  // right after Star (see above) — Folder/Refresh/Refetch/
                  // Activity stay here.
                  Container(width: 1, height: 24, color: cs.outlineVariant),
                  if (widget.vacancy?.folderPath != null)
                    IconButton(
                      icon: Icon(
                        Icons.folder_open_outlined,
                        size: 18,
                        color: cs.onSurfaceVariant,
                      ),
                      tooltip: 'Open folder',
                      onPressed: () => Process.run('explorer.exe', [
                        widget.vacancy!.folderPath!,
                      ]),
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
                          : Icon(
                              Icons.sync_rounded,
                              size: 18,
                              color: cs.onSurfaceVariant,
                            ),
                      onPressed: _refreshing ? null : _refresh,
                    ),
                  ),
                  if (widget.url.isNotEmpty)
                    Tooltip(
                      message:
                          'Re-fetch from source — re-pull the JD from the live posting page '
                          '(not the cached copy, not the RSS feed). For a vacancy fetched too early, '
                          'e.g. while the job board was still moderating it.',
                      child: IconButton(
                        icon: _loadingRefetch
                            ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : Icon(
                                Icons.cloud_download_outlined,
                                size: 18,
                                color: cs.onSurfaceVariant,
                              ),
                        onPressed: _loadingRefetch ? null : _refetchFromSource,
                      ),
                    ),
                  Tooltip(
                    message:
                        'Activity log — pipeline runs + LLM calls (incl. pre-filter checks). '
                        'Only reachable from this JD view before analysis — the tabbed Activity tab '
                        'only appears once Phase 1+2 analysis exists.',
                    child: IconButton(
                      icon: Icon(
                        Icons.history_rounded,
                        size: 18,
                        color: cs.onSurfaceVariant,
                      ),
                      onPressed: () => _showActivityLog(context),
                    ),
                  ),
                ],
              ),
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
              bottom: BorderSide(
                color: cs.outlineVariant.withValues(alpha: 0.15),
              ),
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
              const SizedBox(width: 16),
              _TagsInline(
                tags: widget.vacancy?.tags ?? const [],
                fontSize: 16,
                onSave: (v) async {
                  await _repo.updateTags(widget.vacancyId, v);
                  ref.read(vacancyListProvider.notifier).refresh();
                },
              ),
            ],
          ),
        ),
        _PrefilterBanner(
          blocked: widget.vacancy?.blockerFlag ?? false,
          checked: widget.vacancy?.blockerChecked ?? false,
          reasons: widget.vacancy?.blockerReasons ?? const [],
          onTapDetails: (widget.vacancy?.blockerChecked ?? false)
              ? _showPrefilterDetails
              : null,
        ),
        // JD content
        Expanded(
          child: jdAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(
              child: Text(
                'Failed to load JD: $e',
                style: const TextStyle(color: Color(0xFFBA1A1A)),
              ),
            ),
            data: (jd) => SelectionArea(
              child: Markdown(
                data: jd,
                selectable: true,
                padding: const EdgeInsets.fromLTRB(24, 20, 24, 32),
                styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context))
                    .copyWith(
                      p: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: cs.onSurface,
                        height: 1.6,
                      ),
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
    final label = switch (status) {
      'analyzing' => 'Analyzing...',
      'fetching' => 'Fetching job description...',
      'queued' => 'Queued for fetching...',
      _ => 'In queue for analysis...',
    };
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
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant),
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
    final apiUrl =
        ref.read(settingsProvider).valueOrNull?.apiUrl ??
        'http://localhost:8080';
    return VacancyRepository(baseUrl: apiUrl);
  }

  Future<void> _retry() async {
    setState(() => _retrying = true);
    try {
      await _repo.reset(widget.vacancyId);
      await _repo.analyze(widget.vacancyId);
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
        showToast(context, 'Reset & queued for analysis');
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, 'Error: $e');
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
            Text(
              'Analysis failed',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            if (widget.errorMessage != null &&
                widget.errorMessage!.isNotEmpty) ...[
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
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
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
  ConsumerState<_AnalysisErrorBanner> createState() =>
      _AnalysisErrorBannerState();
}

class _AnalysisErrorBannerState extends ConsumerState<_AnalysisErrorBanner> {
  bool _retrying = false;

  Future<void> _retry() async {
    setState(() => _retrying = true);
    try {
      final apiUrl =
          ref.read(settingsProvider).valueOrNull?.apiUrl ??
          'http://localhost:8080';
      final repo = VacancyRepository(baseUrl: apiUrl);
      await repo.reset(widget.vacancyId);
      await repo.analyze(widget.vacancyId);
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
        widget.onDismiss();
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, 'Error: $e');
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
        border: Border(
          bottom: BorderSide(color: cs.error.withValues(alpha: 0.25)),
        ),
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
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant),
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
                ? const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
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
  // Fires after Applied is toggled ON (2026-08-25) — Applied relocates the
  // vacancy to a different folder just like Skip/Delete does, so the caller
  // (vacancy_inbox_screen.dart) advances the keyboard selection the same
  // way it does after _onSkipped. Does NOT fire on toggle-OFF — un-applying
  // doesn't necessarily move the card out of the folder currently in view.
  final VoidCallback? onApplied;

  const VacancyDetailScreen({
    super.key,
    required this.vacancyId,
    required this.url,
    this.vacancy,
    this.onSkipped,
    this.onNavigateTo,
    this.onApplied,
  });

  @override
  ConsumerState<VacancyDetailScreen> createState() =>
      _VacancyDetailScreenState();
}

class _VacancyDetailScreenState extends ConsumerState<VacancyDetailScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  Timer? _cvPollingTimer;
  bool _errorBannerDismissed = false;

  static bool _needsPolling(String? status) =>
      status == 'cv_queued' ||
      status == 'cv_generating' ||
      status == 'cover_generating';

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

    // queued / fetching — webhook already inserted the DB row (card shows
    // instantly) but RSSWatcher hasn't written JD.md yet (polls every 30s,
    // core/rss_watcher.py). Opening the detail view in that window used to
    // hit GET /api/vacancies/{id}/jd before the file existed and surface a
    // raw "Failed to load JD: Exception: JD not found" — same data, just not
    // there yet. Spinner instead; parent list polling flips status once
    // fetch_jd() finishes, which rebuilds this into the real JD view.
    if (status == 'queued' || status == 'fetching') {
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
          return _JdModeView(
            key: ValueKey(widget.vacancyId),
            vacancyId: widget.vacancyId,
            url: widget.url,
            vacancy: widget.vacancy,
            restoreMode: true,
          );
        }
        return _JdModeView(
          key: ValueKey(widget.vacancyId),
          vacancyId: widget.vacancyId,
          url: widget.url,
          vacancy: widget.vacancy,
          onSkipped: widget.onSkipped,
          onApplied: widget.onApplied,
        );
      },
      data: (analysis) {
        final p1 = analysis.p1;
        final p2 = analysis.p2;

        if (p2 == null) {
          // No analysis yet — show JD view with context-appropriate buttons
          if (status == 'declined') {
            return _JdModeView(
              key: ValueKey(widget.vacancyId),
              vacancyId: widget.vacancyId,
              url: widget.url,
              vacancy: widget.vacancy,
              restoreMode: true,
            );
          }
          return _JdModeView(
            key: ValueKey(widget.vacancyId),
            vacancyId: widget.vacancyId,
            url: widget.url,
            vacancy: widget.vacancy,
            onSkipped: widget.onSkipped,
            onApplied: widget.onApplied,
          );
        }

        final role = p1?.role.isNotEmpty == true
            ? p1!.role
            : widget.vacancy?.role ?? '';
        final company = p1?.company.isNotEmpty == true
            ? p1!.company
            : widget.vacancy?.company ?? '';

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
            _ActionBar(
              vacancyId: widget.vacancyId,
              url: widget.url,
              role: role,
              company: company,
              status: status,
              vacancy: widget.vacancy,
              tabController: _tabController,
              onApplied: widget.onApplied,
            ),
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
              // SelectionArea unifies text selection across every tab's
              // content into one continuous drag-select, instead of each
              // Markdown block/SelectableText being its own isolated
              // island (found live 2026-09-21 — could select within one
              // paragraph but dragging into the next selected nothing).
              child: SelectionArea(
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
                            analyzedAt: analysis.analyzedAt,
                            salary: widget.vacancy?.salary,
                            onSalaryChanged: (v) async {
                              final apiUrl =
                                  ref
                                      .read(settingsProvider)
                                      .valueOrNull
                                      ?.apiUrl ??
                                  'http://localhost:8080';
                              await VacancyRepository(
                                baseUrl: apiUrl,
                              ).updateSalary(widget.vacancyId, v);
                              ref.invalidate(vacancyListProvider);
                            },
                            onTagsChanged: (v) async {
                              final apiUrl =
                                  ref
                                      .read(settingsProvider)
                                      .valueOrNull
                                      ?.apiUrl ??
                                  'http://localhost:8080';
                              await VacancyRepository(
                                baseUrl: apiUrl,
                              ).updateTags(widget.vacancyId, v);
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
                              tooltip:
                                  'Fit scored across 5 axes (0–10 each):\ndomain, execution, strategy, systems, stakeholder',
                              child: _FitDimsTable(dims: p2.fitDimensions!),
                            ),
                          if (p1 != null) ...[
                            const SizedBox(height: 16),
                            _CollapsibleSection(
                              title: 'Attraction Breakdown',
                              tooltip:
                                  'How attractive this vacancy is for you\nacross 8 factors: company tier, seniority,\nscope, compensation and more',
                              child: _VacScoreTable(dims: p1.vacscoreDims),
                            ),
                            // Role Balance moved into _VacancyHero as a radar
                            // chart (2026-09-06) — replaces this bar-list
                            // rendering, not duplicated alongside it.
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
                  label:
                      'Original · ${original.role.isNotEmpty ? original.role : '#${original.id}'}',
                  sublabel: original.company.isNotEmpty
                      ? original.company
                      : null,
                  id: original.id,
                  icon: Icons.arrow_upward_rounded,
                  tooltip:
                      'This vacancy is a duplicate — the original posting is #${original.id}.\nTap to open the original.',
                  onTap: onNavigateTo != null
                      ? () => onNavigateTo!(original.id)
                      : null,
                ),
              for (final dup in duplicates)
                _RelatedChip(
                  label:
                      '${dup.site.isNotEmpty ? dup.site[0].toUpperCase() + dup.site.substring(1) : 'Dup'} · ${dup.role.isNotEmpty ? dup.role : '#${dup.id}'}',
                  sublabel: dup.company.isNotEmpty ? dup.company : null,
                  id: dup.id,
                  icon: Icons.copy_rounded,
                  tooltip:
                      'The same job was also found on ${dup.site.isNotEmpty ? dup.site : 'another source'} (vacancy #${dup.id}).\nTap to open it.',
                  onTap: onNavigateTo != null
                      ? () => onNavigateTo!(dup.id)
                      : null,
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
                Icon(
                  icon,
                  size: 13,
                  color: onTap != null ? cs.primary : cs.onSurfaceVariant,
                ),
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
        error: (e, _) =>
            Text('Failed to load JD: $e', style: TextStyle(color: cs.error)),
        data: (jd) => MarkdownBody(
          data: jd,
          selectable: true,
          styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
            p: Theme.of(
              context,
            ).textTheme.bodyMedium?.copyWith(color: cs.onSurface, height: 1.6),
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
    final apiUrl =
        ref.read(settingsProvider).valueOrNull?.apiUrl ??
        'http://localhost:8080';
    try {
      final result = await VacancyRepository(
        baseUrl: apiUrl,
      ).getActivity(widget.vacancyId);
      if (mounted)
        setState(() {
          _runs = result.runs;
          _entries = result.entries;
          _loading = false;
        });
    } catch (e) {
      if (mounted)
        setState(() {
          _error = '$e';
          _loading = false;
        });
    }
  }

  static DateTime _asUtc(String iso) => parseBackendUtc(iso).toLocal();

  // Convert ISO UTC string → device local time, formatted DD.MM.YYYY HH:mm
  String _fmtTs(String? iso) {
    if (iso == null || iso.isEmpty) return '—';
    try {
      final dt = _asUtc(iso);
      final dd = dt.day.toString().padLeft(2, '0');
      final mm = dt.month.toString().padLeft(2, '0');
      final yy = dt.year.toString();
      final hh = dt.hour.toString().padLeft(2, '0');
      final min = dt.minute.toString().padLeft(2, '0');
      return '$dd.$mm.$yy $hh:$min';
    } catch (_) {
      return iso.length >= 16 ? iso.substring(0, 16).replaceAll('T', ' ') : iso;
    }
  }

  String _fmtMs(int ms) =>
      ms >= 1000 ? '${(ms / 1000).toStringAsFixed(1)}s' : '${ms}ms';
  String _k(int n) => n >= 1000 ? '${(n / 1000).toStringAsFixed(1)}k' : '$n';

  // ── Shared container ──────────────────────────────────────────────────────────

  Widget _section(BuildContext context, String label, Widget body) {
    final cs = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
            color: cs.onSurfaceVariant,
            letterSpacing: 0.8,
          ),
        ),
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
    const hStyle = TextStyle(
      fontSize: 10.5,
      fontWeight: FontWeight.w600,
      letterSpacing: 0.4,
    );
    const dStyle = TextStyle(fontSize: 11.5, height: 1.6);

    Widget hcell(String t, {TextAlign a = TextAlign.left}) => Padding(
      padding: const EdgeInsets.fromLTRB(4, 2, 14, 5),
      child: Text(
        t,
        style: hStyle.copyWith(color: cs.onSurfaceVariant),
        textAlign: a,
      ),
    );
    Widget cell(
      String t, {
      TextAlign a = TextAlign.left,
      Color? color,
      bool bold = false,
    }) => Padding(
      padding: const EdgeInsets.fromLTRB(4, 2, 14, 2),
      child: Text(
        t,
        style: dStyle.copyWith(
          color: color,
          fontWeight: bold ? FontWeight.w600 : null,
        ),
        textAlign: a,
      ),
    );

    return Table(
      columnWidths: const {
        0: IntrinsicColumnWidth(), // time
        1: IntrinsicColumnWidth(), // phase
        2: IntrinsicColumnWidth(), // icon
        3: IntrinsicColumnWidth(), // status
        4: IntrinsicColumnWidth(), // duration
        5: FlexColumnWidth(), // error
      },
      defaultVerticalAlignment: TableCellVerticalAlignment.middle,
      children: [
        TableRow(
          decoration: BoxDecoration(
            border: Border(
              bottom: BorderSide(
                color: cs.outlineVariant.withValues(alpha: 0.5),
              ),
            ),
          ),
          children: [
            hcell('Time'),
            hcell('Phase'),
            hcell(''),
            hcell('Status'),
            hcell('Duration', a: TextAlign.right),
            hcell('Error'),
          ],
        ),
        ...runs.map((r) {
          final ok = r.status == 'done';
          final isErr = r.status == 'error';
          final icon = ok ? '✓' : (isErr ? '✗' : '·');
          final icColor = ok
              ? cs.primary
              : (isErr ? cs.error : cs.onSurfaceVariant);
          final err =
              (!ok && r.errorMessage != null && r.errorMessage!.isNotEmpty)
              ? r.errorMessage!
              : '';
          return TableRow(
            children: [
              cell(_fmtTs(r.startedAt), color: cs.onSurfaceVariant),
              cell(r.phase, bold: true),
              cell(icon, color: icColor),
              cell(r.status),
              cell(
                r.durationMs != null ? _fmtMs(r.durationMs!) : '—',
                a: TextAlign.right,
              ),
              cell(err, color: err.isNotEmpty ? cs.error : null),
            ],
          );
        }),
      ],
    );
  }

  // ── LLM Calls table ──────────────────────────────────────────────────────────

  Widget _entriesTable(BuildContext context, List<ActivityEntry> entries) {
    final cs = Theme.of(context).colorScheme;
    const hStyle = TextStyle(
      fontSize: 10.5,
      fontWeight: FontWeight.w600,
      letterSpacing: 0.4,
    );
    const dStyle = TextStyle(fontSize: 11.5, height: 1.6);

    Widget hcell(String t, {TextAlign a = TextAlign.left}) => Padding(
      padding: const EdgeInsets.fromLTRB(4, 2, 14, 5),
      child: Text(
        t,
        style: hStyle.copyWith(color: cs.onSurfaceVariant),
        textAlign: a,
      ),
    );
    Widget cell(
      String t, {
      TextAlign a = TextAlign.left,
      Color? color,
      bool bold = false,
    }) => Padding(
      padding: const EdgeInsets.fromLTRB(4, 2, 14, 2),
      child: Text(
        t,
        style: dStyle.copyWith(
          color: color,
          fontWeight: bold ? FontWeight.w600 : null,
        ),
        textAlign: a,
      ),
    );

    final totalCost = entries.fold(0.0, (s, e) => s + e.costUsd);
    final totalMs = entries.fold(0, (s, e) => s + e.elapsedMs);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Table(
          columnWidths: const {
            0: IntrinsicColumnWidth(), // time
            1: IntrinsicColumnWidth(), // phase
            2: IntrinsicColumnWidth(), // provider
            3: FlexColumnWidth(), // model
            4: IntrinsicColumnWidth(), // elapsed
            5: IntrinsicColumnWidth(), // tokens
            6: IntrinsicColumnWidth(), // cost
          },
          defaultVerticalAlignment: TableCellVerticalAlignment.middle,
          children: [
            TableRow(
              decoration: BoxDecoration(
                border: Border(
                  bottom: BorderSide(
                    color: cs.outlineVariant.withValues(alpha: 0.5),
                  ),
                ),
              ),
              children: [
                hcell('Time'),
                hcell('Phase'),
                hcell('Provider'),
                hcell('Model'),
                hcell('Elapsed', a: TextAlign.right),
                hcell('Tokens', a: TextAlign.right),
                hcell('Cost', a: TextAlign.right),
              ],
            ),
            ...entries.map((e) {
              final tok = e.provider == 'claude_cli'
                  ? '—'
                  : '${_k(e.inputTokens)}→${_k(e.outputTokens)}';
              final cost = e.costUsd > 0
                  ? '\$${e.costUsd.toStringAsFixed(4)}'
                  : '—';
              final modelText =
                  e.thinkingEffort.isNotEmpty && e.thinkingEffort != 'off'
                  ? '${e.model}  [${e.thinkingEffort}]'
                  : e.model;
              return TableRow(
                children: [
                  cell(_fmtTs(e.createdAt), color: cs.onSurfaceVariant),
                  cell(e.phase, bold: true),
                  cell(e.provider),
                  cell(modelText),
                  cell(_fmtMs(e.elapsedMs), a: TextAlign.right),
                  cell(tok, a: TextAlign.right),
                  cell(cost, a: TextAlign.right),
                ],
              );
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
      return Center(
        child: Text('Error: $_error', style: TextStyle(color: cs.error)),
      );
    }

    final runs = _runs ?? [];
    final entries = _entries ?? [];

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (runs.isEmpty && entries.isEmpty)
            Text(
              'No activity recorded for this vacancy yet.',
              style: Theme.of(
                context,
              ).textTheme.bodyMedium?.copyWith(color: cs.onSurfaceVariant),
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
            onPressed: () {
              setState(() {
                _loading = true;
                _error = null;
              });
              _load();
            },
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
  final String company;
  final String status;
  final VacancyListItem? vacancy;
  final TabController tabController;
  final VoidCallback? onApplied;

  const _ActionBar({
    required this.vacancyId,
    required this.url,
    required this.role,
    required this.tabController,
    this.company = '',
    this.status = 'analyzed',
    this.vacancy,
    this.onApplied,
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
    if (old.vacancy?.starred != widget.vacancy?.starred)
      _starred = widget.vacancy?.starred ?? false;
    if (old.vacancy?.applied != widget.vacancy?.applied)
      _applied = widget.vacancy?.applied ?? false;
  }

  VacancyRepository get _repo {
    final apiUrl =
        ref.read(settingsProvider).valueOrNull?.apiUrl ??
        'http://localhost:8080';
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
    setState(() {
      _starred = next;
      _loadingStar = true;
    });
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
    setState(() {
      _applied = next;
      _loadingApplied = true;
    });
    try {
      await _repo.setApplied(widget.vacancyId, next);
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
        // Only on toggle-ON: Applied relocates the vacancy to a different
        // folder, same as Skip/Delete, so the keyboard selection advances
        // the same way (2026-08-25). Toggle-OFF doesn't get the same
        // treatment — un-applying doesn't necessarily move the card.
        if (next) widget.onApplied?.call();
      }
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
        _showRunQueuedToast(
          'CV generation queued',
          'Generating CV for #${widget.vacancyId}. It is in Inbox while '
              'running and moves to Processed when done.',
        );
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, 'Error: $e');
      }
    } finally {
      if (mounted) setState(() => _loadingCv = false);
    }
  }

  Future<void> _analyze() async {
    setState(() => _loadingAnalyze = true);
    try {
      // Asks "Already applied as #X. Analyze anyway?" when a duplicate of this
      // job was already applied to; false = the user said no.
      final queued = await analyzeWithAppliedGuard(
        context,
        _repo,
        widget.vacancyId,
      );
      if (!queued) return;
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
        _showRunQueuedToast(
          'Analysis queued',
          'Re-analyzing #${widget.vacancyId}. It is in Inbox while running '
              'and returns to Analyzed when done.',
        );
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, 'Error: $e');
      }
    } finally {
      if (mounted) setState(() => _loadingAnalyze = false);
    }
  }

  /// A run moves the vacancy to Inbox until it finishes (core/vacancy_stage.py
  /// maps in-progress statuses there). Say so, unless it stays put anyway:
  /// Applied and Archive win over the run's status. No "Show in Inbox"
  /// action: the detail panel keeps the vacancy open during the run, so
  /// jumping to Inbox adds nothing (owner, 2026-10-08).
  void _showRunQueuedToast(String plain, String moved) {
    final staysPut = _applied || widget.status == 'declined';
    if (staysPut) {
      showToast(context, plain);
      return;
    }
    showToast(context, moved, kind: ToastKind.notice);
  }

  Future<void> _resetAndRetry() async {
    setState(() => _loadingReset = true);
    try {
      await _repo.reset(widget.vacancyId);
      await _repo.analyze(widget.vacancyId);
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
        ref.invalidate(vacancyDetailProvider(widget.vacancyId));
        showToast(context, 'Reset & queued for analysis');
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, 'Error: $e');
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
        showToast(context, 'Cover generation queued');
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, 'Error: $e');
      }
    } finally {
      if (mounted) setState(() => _loadingCv = false);
    }
  }

  Future<void> _downloadPdf(String type) async {
    final toaster = Toaster.of(context);
    final preparing = toaster.show(
      'Preparing PDF...',
      duration: const Duration(minutes: 1),
    );
    try {
      final bytes = type == 'cv'
          ? await _repo.getCvPdfBytes(widget.vacancyId)
          : await _repo.getCoverPdfBytes(widget.vacancyId);
      preparing.dismiss();
      if (!mounted) return;
      final label = type == 'cv' ? 'CV' : 'Cover Letter';
      final fileName =
          '${type == 'cv' ? 'CV' : 'Cover'}_${widget.vacancyId}.pdf';
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
          toaster.show('Saved: $path');
        }
      }
    } catch (e) {
      preparing.dismiss();
      if (mounted) {
        showErrorSnackBar(context, 'PDF error: $e');
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
        showErrorSnackBar(context, 'Error: $e');
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
        showToast(context, 'Moved to inbox', kind: ToastKind.notice);
      }
    } catch (e) {
      if (mounted) {
        showErrorSnackBar(context, 'Error: $e');
        setState(() => _loadingRestore = false);
      }
    }
  }

  Widget _buildCta(
    BuildContext context,
    ColorScheme cs,
    AsyncValue<VacancyCv> cvAsync, {
    required bool workerAvailable,
  }) {
    final tab = widget.tabController.index;
    final isDeclined = widget.status == 'declined';
    final isCvInProgress =
        widget.status == 'cv_queued' || widget.status == 'cv_generating';

    if (isDeclined) {
      if (tab == 0) {
        return OutlinedButton.icon(
          onPressed: _loadingRestore ? null : _restore,
          icon: _loadingRestore
              ? const SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
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
                  side: BorderSide(color: cs.error),
                  foregroundColor: cs.error,
                ),
                child: _loadingDecline
                    ? const SizedBox(
                        width: 14,
                        height: 14,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Decline'),
              ),
              const SizedBox(width: 8),
              Tooltip(
                message: workerAvailable
                    ? ''
                    : 'Analysis worker unavailable — start agent.py',
                child: FilledButton.icon(
                  onPressed: _loadingAnalyze || !workerAvailable
                      ? null
                      : _analyze,
                  icon: _loadingAnalyze
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Icon(Icons.refresh_rounded, size: 16),
                  label: Text(_loadingAnalyze ? 'Queuing...' : 'Re-analyze'),
                ),
              ),
            ] else ...[
              Tooltip(
                message: 'Reset stuck analysis and retry from scratch',
                child: FilledButton.icon(
                  onPressed: _loadingReset ? null : _resetAndRetry,
                  style: FilledButton.styleFrom(
                    backgroundColor: Colors.orange.shade700,
                  ),
                  icon: _loadingReset
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
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
          label: isCvInProgress
              ? 'Generating...'
              : (hasCv ? 'Regenerate CV' : 'Generate CV'),
          icon: Icons.description_outlined,
          loading: _loadingCv || isCvInProgress,
          onPressed: (isCvInProgress || _loadingCv) ? null : _generateCv,
          menuItems: [
            MenuItemButton(
              onPressed: (isCvInProgress || _loadingCv)
                  ? null
                  : () => _generateCv(language: 'en'),
              leadingIcon: const Icon(Icons.translate, size: 16),
              child: const Text('Generate in English'),
            ),
            MenuItemButton(
              onPressed: (isCvInProgress || _loadingCv)
                  ? null
                  : () => _generateCv(language: 'uk'),
              leadingIcon: const Icon(Icons.translate, size: 16),
              child: const Text('Generate in Ukrainian'),
            ),
            MenuItemButton(
              onPressed: hasCv && !isCvInProgress
                  ? () => _downloadPdf('cv')
                  : null,
              leadingIcon: const Icon(Icons.picture_as_pdf_outlined, size: 16),
              child: const Text('Download PDF'),
            ),
          ],
        );

      case 2: // Cover
        final hasCover = cvAsync.valueOrNull?.hasCover ?? false;
        final isCoverInProgress = widget.status == 'cover_generating';
        return _SplitButton(
          label: isCoverInProgress
              ? 'Generating...'
              : (hasCover ? 'Regenerate Cover' : 'Generate Cover'),
          icon: Icons.mail_outline,
          loading: _loadingCv || isCoverInProgress,
          onPressed: (isCoverInProgress || _loadingCv) ? null : _generateCover,
          menuItems: hasCover
              ? [
                  MenuItemButton(
                    onPressed: () => _downloadPdf('cover'),
                    leadingIcon: const Icon(
                      Icons.picture_as_pdf_outlined,
                      size: 16,
                    ),
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
    final health =
        ref.watch(healthProvider).valueOrNull ?? HealthStatus.checking;
    final workerAvailable = health == HealthStatus.online;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: cs.surfaceContainerLowest.withValues(alpha: 0.9),
        border: Border(
          bottom: BorderSide(color: cs.outlineVariant.withValues(alpha: 0.15)),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Vacancy id + compact title — shared with _JdModeView (2026-09-07
          // header unification), own lines, same treatment in both states.
          // The compact title guarantees the role/company is always visible
          // here — previously it lived only in _VacancyHero, which scrolls
          // away with the rest of the Analysis tab's content.
          _VacancyIdLine(vacancyId: widget.vacancyId),
          _VacancyCompactTitle(role: widget.role, company: widget.company),
          const SizedBox(height: 8),
          Row(
            children: [
              // Star toggle
              Tooltip(
                message: _starred
                    ? 'Remove from favourites'
                    : 'Add to favourites',
                child: IconButton(
                  icon: Icon(
                    _starred ? Icons.star_rounded : Icons.star_outline_rounded,
                    size: 20,
                    color: _starred
                        ? const Color(0xFFFFB300)
                        : cs.onSurfaceVariant,
                  ),
                  onPressed: _toggleStar,
                  splashRadius: 18,
                ),
              ),
              // Open JD — moved right after Star (2026-09-07, user request:
              // "Звездочка, открыть ссылку на вакансию, вертикальный
              // разделитель").
              if (widget.url.isNotEmpty)
                IconButton(
                  icon: Icon(
                    Icons.open_in_new,
                    size: 18,
                    color: cs.onSurfaceVariant,
                  ),
                  tooltip: 'Open JD',
                  onPressed: () => launchUrl(
                    Uri.parse(widget.url),
                    mode: LaunchMode.externalApplication,
                  ),
                ),
              // Row (unlike the Wrap in _JdModeView) has no automatic gap
              // between children — explicit horizontal margin here so the
              // divider doesn't sit flush against Applied (2026-09-07, user
              // feedback: "разделитель слишком близко к кнопке Applied").
              Container(
                width: 1,
                height: 24,
                margin: const EdgeInsets.symmetric(horizontal: 8),
                color: cs.outlineVariant,
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
              // Open vacancy folder in Explorer
              if (widget.vacancy?.folderPath != null)
                IconButton(
                  icon: Icon(
                    Icons.folder_open_outlined,
                    size: 18,
                    color: cs.onSurfaceVariant,
                  ),
                  tooltip: 'Open folder',
                  onPressed: () => Process.run('explorer.exe', [
                    widget.vacancy!.folderPath!,
                  ]),
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
                      : Icon(
                          Icons.sync_rounded,
                          size: 18,
                          color: cs.onSurfaceVariant,
                        ),
                  onPressed: _refreshing ? null : _refresh,
                ),
              ),
              const SizedBox(width: 4),
              // Context-sensitive CTA — changes per tab
              AnimatedBuilder(
                animation: widget.tabController,
                builder: (context, _) => _buildCta(
                  context,
                  cs,
                  cvAsync,
                  workerAvailable: workerAvailable,
                ),
              ),
            ],
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
  final String? analyzedAt;
  final Future<void> Function(String)? onSalaryChanged;
  final Future<void> Function(String)? onTagsChanged;

  const _VacancyHero({
    required this.p1,
    required this.p2,
    required this.vacancyId,
    this.vacancy,
    this.salary,
    this.analyzedAt,
    this.onSalaryChanged,
    this.onTagsChanged,
  });

  static void _openWebsite(String url) =>
      launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final role = p1?.role.isNotEmpty == true ? p1!.role : (vacancy?.role ?? '');
    final company = p1?.company.isNotEmpty == true
        ? p1!.company
        : (vacancy?.company ?? '');
    final publishedAt = vacancy?.publishedAt;
    final appliedAt = vacancy?.appliedAt;
    // category moves to Quick Overview block, not used in hero

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 24),
        // Title + Subtitle
        // IntrinsicHeight — required for VerticalDivider to render inside a
        // Row; without it, the divider has no bounded height to fill and
        // either collapses to zero or throws a layout error.
        IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // User tag badges (e.g. "DEFTECH") — shown above the title
                    // itself, the most prominent spot on the screen, so a batch
                    // of similarly-tagged vacancies stays identifiable at a
                    // glance (2026-08-27).
                    if ((vacancy?.tags ?? const []).isNotEmpty) ...[
                      Wrap(
                        spacing: 6,
                        runSpacing: 4,
                        children: [
                          for (final tag in vacancy!.tags)
                            _HeroTagBadge(tag: tag),
                        ],
                      ),
                      const SizedBox(height: 6),
                    ],
                    // Vacancy id moved out of here (2026-09-06, user request)
                    // — now shown once, top-left, in the _ActionBar/_JdModeView
                    // row above, not duplicated next to the title too.
                    Text(
                      role,
                      style: Theme.of(context).textTheme.displaySmall?.copyWith(
                        fontSize: 28,
                        fontWeight: FontWeight.w700,
                        color: cs.onSurface,
                        height: 1.2,
                      ),
                    ),
                    if (company.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Flexible(
                            child: Text(
                              company,
                              style: Theme.of(context).textTheme.titleMedium
                                  ?.copyWith(
                                    color: cs.onSurfaceVariant,
                                    fontWeight: FontWeight.w500,
                                    fontSize: 18,
                                  ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          if (vacancy?.companyWebsite != null &&
                              vacancy!.companyWebsite!.isNotEmpty)
                            Padding(
                              padding: const EdgeInsets.only(left: 8),
                              child: Tooltip(
                                message: vacancy!.companyWebsite!,
                                child: InkWell(
                                  onTap: () =>
                                      _openWebsite(vacancy!.companyWebsite!),
                                  child: Icon(
                                    Icons.language,
                                    size: 22,
                                    color: cs.primary,
                                  ),
                                ),
                              ),
                            ),
                        ],
                      ),
                    ],
                    const SizedBox(height: 10),
                    // Salary/tags — enlarged (2026-09-06, user request: "легче
                    // кликалось, легче редактировалось, легче читалось") now
                    // that removing the leading icon box and adding the radar's
                    // own column freed up the bottom-left quarter of this
                    // header entirely.
                    Row(
                      children: [
                        if (onSalaryChanged != null)
                          _SalaryInline(
                            salary: salary,
                            onSave: onSalaryChanged!,
                            fontSize: 18,
                          ),
                        if (onTagsChanged != null) ...[
                          const SizedBox(width: 20),
                          _TagsInline(
                            tags: vacancy?.tags ?? const [],
                            onSave: onTagsChanged!,
                            fontSize: 18,
                          ),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
              // Vertical divider between the text block and the radar
              // (2026-09-06, user request).
              if (p1 != null && p1!.roleBalance.isNotEmpty) ...[
                const SizedBox(width: 20),
                VerticalDivider(
                  width: 1,
                  thickness: 1,
                  color: cs.outlineVariant.withValues(alpha: 0.3),
                ),
                const SizedBox(width: 20),
                // Role-balance radar — right-aligned in the space the text
                // block doesn't need (2026-09-06, user request). Replaces the
                // old "Role Balance" collapsible bar-list section further down
                // the page, not duplicated alongside it.
                _RoleBalanceRadar(balance: p1!.roleBalance),
              ],
            ],
          ),
        ),
        const SizedBox(height: 20),
        // Recommendation card — primary go/no-go decision
        _RecommendationCard(
          recommendation: p2.recommendation,
          recommendationLabel: p2.recommendationLabel,
          archetype: p1?.primaryArchetype ?? '',
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
                    message:
                        'Candidate-to-role fit across domain, execution,\nstrategy, systems & stakeholder (0–10)',
                    child: _ScoreDotsRow(
                      label: 'Fit',
                      score: p2.fitScore.toDouble(),
                      max: 10,
                    ),
                  ),
                  if (p1 != null) ...[
                    const SizedBox(height: 5),
                    Tooltip(
                      message:
                          'How attractive this role is for you —\nseniority, company tier, scope, compensation (0–10)',
                      child: _ScoreDotsRow(
                        label: 'Attraction',
                        score: p1!.vacancyScore,
                        max: 10,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            if (publishedAt != null ||
                analyzedAt != null ||
                appliedAt != null) ...[
              const SizedBox(width: 8),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  if (publishedAt != null)
                    _PostedChip(
                      publishedAt: publishedAt,
                      createdAt: vacancy?.createdAt,
                      cs: cs,
                    ),
                  if (analyzedAt != null) ...[
                    if (publishedAt != null) const SizedBox(height: 4),
                    _AnalyzedChip(analyzedAt: analyzedAt!, cs: cs),
                  ],
                  if (appliedAt != null) ...[
                    if (publishedAt != null || analyzedAt != null)
                      const SizedBox(height: 4),
                    _AppliedChip(appliedAt: appliedAt, cs: cs),
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
        if (p2.warnings.isNotEmpty) ...[
          const SizedBox(height: 10),
          _WarningsBanner(warnings: p2.warnings),
        ],
        if (p2.keyBarriers.isNotEmpty) ...[
          const SizedBox(height: 10),
          _KeyBarriersBanner(barriers: p2.keyBarriers),
        ],
      ],
    );
  }
}

/// Standalone, high-visibility warnings block — pulled out of Quick Overview
/// (2026-08-26): a JD-structured warning (e.g. hybrid format tied to a specific
/// office city) was correctly flagged by Phase 2, but buried as one small row
/// among Category/Key Barriers/Hidden Risks in Quick Overview and went unnoticed
/// (vacancy #1228). Shown right under the Fit/Attraction + pre-filter block so
/// it can't be missed before the candidate decides to apply.
/// Key Barriers — gaps between the JD's requirements and the profile; they
/// decide "apply or not", so they get their own block right under Warnings
/// instead of a row in Quick Overview below the fold (2026-10-09, owner).
/// Red, a bulleted list and the count in the title, so several barriers do
/// not read as one sentence. Hidden Risks stay in Quick Overview: they are
/// in almost every analysis and a red block on each vacancy would be noise.
class _KeyBarriersBanner extends StatelessWidget {
  final List<String> barriers;

  const _KeyBarriersBanner({required this.barriers});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final fg = cs.onErrorContainer;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: cs.errorContainer.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: cs.error, width: 1.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.report_gmailerrorred_rounded, size: 20, color: cs.error),
              const SizedBox(width: 8),
              Text(
                'Key Barriers (${barriers.length})',
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  color: fg,
                  fontSize: 15,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ...barriers.map(
            (b) => Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: SelectableText(
                '•  $b',
                style: TextStyle(color: fg, fontSize: 13.5, height: 1.35),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _WarningsBanner extends StatelessWidget {
  final List<String> warnings;

  const _WarningsBanner({required this.warnings});

  @override
  Widget build(BuildContext context) {
    const bg = Color(0xFFFFF8E1);
    const border = Color(0xFFFFB300);
    const fg = Color(0xFF8D5A00);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: border, width: 1.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.warning_amber_rounded, size: 20, color: fg),
              SizedBox(width: 8),
              Text(
                'Warnings',
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  color: fg,
                  fontSize: 15,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ...warnings.map(
            (w) => Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text(
                '•  $w',
                style: const TextStyle(color: fg, fontSize: 13.5, height: 1.35),
              ),
            ),
          ),
        ],
      ),
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
    final icon = blocked
        ? Icons.block_rounded
        : Icons.check_circle_outline_rounded;
    final label = blocked
        ? 'Possible blocker — pre-filter check'
        : 'Pre-filter checked — no blockers';

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
                  child: Text(
                    'Details',
                    style: TextStyle(
                      fontSize: 11,
                      color: cs.primary,
                      decoration: TextDecoration.underline,
                    ),
                  ),
                ),
              ],
            ],
          ),
          if (blocked) ...[
            const SizedBox(height: 6),
            ...reasons.map(
              (r) => Padding(
                padding: const EdgeInsets.only(bottom: 3),
                child: _reasonLine(
                  r,
                  style: TextStyle(fontSize: compact ? 11.5 : 12.5),
                ),
              ),
            ),
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

  const _ScoreDotsRow({
    required this.label,
    required this.score,
    required this.max,
  });

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
    final scoreText = score % 1 == 0
        ? '${score.toInt()}'
        : score.toStringAsFixed(1);

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        SizedBox(
          width: 72,
          child: Text(
            label,
            style: Theme.of(
              context,
            ).textTheme.labelSmall?.copyWith(color: cs.onSurfaceVariant),
          ),
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
        Text(
          scoreText,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
            color: cs.onSurface,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}

class _RecommendationCard extends StatelessWidget {
  final String recommendation;
  final String recommendationLabel;
  final String archetype;
  final String whoTheyWant;

  const _RecommendationCard({
    required this.recommendation,
    required this.recommendationLabel,
    this.archetype = '',
    this.whoTheyWant = '',
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;

    final (bgColor, iconColor, icon) = switch (recommendation) {
      'apply' => (
        cs.primaryContainer.withValues(alpha: 0.5),
        cs.primary,
        Icons.check_circle_rounded,
      ),
      'take_a_chance' => (
        cs.tertiaryContainer.withValues(alpha: 0.5),
        cs.tertiary,
        Icons.bolt_rounded,
      ),
      _ => (
        cs.errorContainer.withValues(alpha: 0.5),
        cs.error,
        Icons.cancel_rounded,
      ),
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
                if (archetype.isNotEmpty) ...[
                  // Own pill so it doesn't blend into the surrounding prose
                  // (user: "искал, хотя он был у меня под носом") — mixes
                  // the neutral chip style already used by _AnalyzedChip
                  // with more breathing room above/below than a plain text
                  // line would get. No leading icon — every candidate tried
                  // (category/label/badge/psychology/psychology_alt) read as
                  // unclear or distracting at this size; text alone won.
                  const SizedBox(height: 10),
                  Tooltip(
                    message:
                        'Primary archetype — balance-intensity + role-shape, '
                        'from Phase 1 §1.4',
                    preferBelow: true,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10,
                        vertical: 6,
                      ),
                      decoration: BoxDecoration(
                        color: cs.surfaceContainer,
                        borderRadius: BorderRadius.circular(999),
                        border: Border.all(
                          color: cs.outlineVariant.withValues(alpha: 0.3),
                        ),
                      ),
                      child: Text(
                        archetype,
                        style: Theme.of(context).textTheme.labelMedium
                            ?.copyWith(color: cs.onSurfaceVariant),
                      ),
                    ),
                  ),
                  const SizedBox(height: 4),
                ],
                if (whoTheyWant.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Tooltip(
                    message:
                        'The ideal candidate archetype this vacancy targets',
                    preferBelow: true,
                    child: SelectableText(
                      whoTheyWant,
                      style: Theme.of(
                        context,
                      ).textTheme.bodyMedium?.copyWith(color: cs.onSurface),
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

class _AppliedChip extends StatelessWidget {
  // vacancy.appliedAt — the moment applied was actually toggled on
  // (db/database.py:set_vacancy_applied), NOT updatedAt (bumped by ~10
  // unrelated write paths — same class of bug the Analyzed chip already
  // dodges via pipeline_runs.finished_at, 2026-08-11).
  final String appliedAt;
  final ColorScheme cs;

  const _AppliedChip({required this.appliedAt, required this.cs});

  static DateTime _asUtc(String iso) => parseBackendUtc(iso).toLocal();

  String _fmtLocal() {
    try {
      final dt = _asUtc(appliedAt);
      final dd = dt.day.toString().padLeft(2, '0');
      final mm = dt.month.toString().padLeft(2, '0');
      final yy = dt.year.toString();
      final hh = dt.hour.toString().padLeft(2, '0');
      final min = dt.minute.toString().padLeft(2, '0');
      return '$dd.$mm.$yy $hh:$min';
    } catch (_) {
      return appliedAt;
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
          Icon(Icons.send_outlined, size: 14, color: cs.onSurfaceVariant),
          const SizedBox(width: 4),
          Text(
            'Applied ${_fmtLocal()}',
            style: Theme.of(
              context,
            ).textTheme.labelMedium?.copyWith(color: cs.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}

class _PostedChip extends StatelessWidget {
  final String publishedAt;
  final String? createdAt;
  final ColorScheme cs;

  const _PostedChip({
    required this.publishedAt,
    required this.createdAt,
    required this.cs,
  });

  static const _postedHint =
      'Posted: when the job board published this vacancy '
      '(the date comes from the RSS feed).';
  static const _addedHint =
      'Added: when this vacancy was added to Career Agent. '
      "For vacancies added by hand the job board's own publish date "
      'is not captured, so it may have been online for longer.';

  String _relativeTime() => relativeTimeFromBackend(publishedAt);

  @override
  Widget build(BuildContext context) {
    final added = isIngestionDate(publishedAt, createdAt);
    return Tooltip(
      message: added ? _addedHint : _postedHint,
      child: Container(
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
              '${added ? 'Added' : 'Posted'} ${_relativeTime()}',
              style: Theme.of(
                context,
              ).textTheme.labelMedium?.copyWith(color: cs.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}

class _AnalyzedChip extends StatelessWidget {
  // Real Phase 2 completion time (pipeline_runs.finished_at), NOT
  // vacancy.updatedAt — updatedAt is bumped by unrelated writes (applied/
  // starred toggle, salary edit, republish bump, dedup, ...) and falsely
  // implies re-analysis. Found live 2026-08-11, vacancy #597.
  final String analyzedAt;
  final ColorScheme cs;

  const _AnalyzedChip({required this.analyzedAt, required this.cs});

  static DateTime _asUtc(String iso) => parseBackendUtc(iso).toLocal();

  String _fmtLocal() {
    try {
      final dt = _asUtc(analyzedAt);
      final dd = dt.day.toString().padLeft(2, '0');
      final mm = dt.month.toString().padLeft(2, '0');
      final yy = dt.year.toString();
      final hh = dt.hour.toString().padLeft(2, '0');
      final min = dt.minute.toString().padLeft(2, '0');
      return '$dd.$mm.$yy $hh:$min';
    } catch (_) {
      return analyzedAt;
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
            style: Theme.of(
              context,
            ).textTheme.labelMedium?.copyWith(color: cs.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}

// ── Hero tag badge ────────────────────────────────────────────────────────────

class _HeroTagBadge extends StatelessWidget {
  final String tag;
  const _HeroTagBadge({required this.tag});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
      decoration: BoxDecoration(
        color: const Color(0xFFEDE7F6),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0xFF9575CD), width: 0.8),
      ),
      child: Text(
        tag.toUpperCase(),
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
          color: const Color(0xFF5E35B1),
          fontWeight: FontWeight.w700,
          fontSize: 11,
          letterSpacing: 0.3,
        ),
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
      if (mounted)
        setState(() => _committedSalary = value.isEmpty ? null : value);
    } finally {
      if (mounted)
        setState(() {
          _saving = false;
          _editing = false;
        });
    }
  }

  void _cancel() {
    setState(() {
      _editing = false;
      _ctrl.text = _committedSalary ?? '';
    });
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;

    if (_editing) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.attach_money,
            size: widget.fontSize + 2,
            color: cs.primary,
          ),
          const SizedBox(width: 4),
          SizedBox(
            width: 220,
            child: TextField(
              controller: _ctrl,
              autofocus: true,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: cs.onSurface,
                fontSize: widget.fontSize,
              ),
              decoration: InputDecoration(
                isDense: true,
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: 8,
                  vertical: 4,
                ),
                hintText: 'e.g. \$3k–5k USD/mo',
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(6),
                ),
              ),
              onSubmitted: (_) => _save(),
            ),
          ),
          const SizedBox(width: 4),
          if (_saving)
            const SizedBox(
              width: 16,
              height: 16,
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

    final kind = salaryKind(_committedSalary);
    final hasSalary = kind != SalaryKind.none;
    final muted = cs.onSurfaceVariant.withValues(alpha: 0.45);
    final (String tooltip, IconData icon, Color iconColor) = switch (kind) {
      SalaryKind.real => (
        'Salary from the vacancy. Click to edit.',
        Icons.attach_money,
        cs.primary,
      ),
      SalaryKind.estimate => (
        "Estimate: Djinni hides the salary; this is the highest value of "
            "Djinni's salary filter that still finds this vacancy. "
            'Click to edit.',
        Icons.attach_money,
        cs.tertiary,
      ),
      SalaryKind.note => (
        "Salary unknown: ${salaryDisplayText(_committedSalary!)}.\n"
            'The automatic search will try again on the next re-fetch. '
            'Click to enter it by hand.',
        Icons.info_outline,
        muted,
      ),
      SalaryKind.none => ('Click to add salary', Icons.attach_money, muted),
    };
    final text = switch (kind) {
      SalaryKind.real || SalaryKind.estimate => salaryDisplayText(
        _committedSalary!,
      ),
      SalaryKind.note => 'Salary unknown',
      SalaryKind.none => 'Add salary…',
    };
    final plain = kind == SalaryKind.real || kind == SalaryKind.estimate;
    return Tooltip(
      message: tooltip,
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        child: GestureDetector(
          onTap: () => setState(() => _editing = true),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: widget.fontSize + 2, color: iconColor),
              const SizedBox(width: 3),
              Text(
                text,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: plain ? cs.onSurfaceVariant : muted,
                  fontStyle: plain ? FontStyle.normal : FontStyle.italic,
                  fontSize: widget.fontSize,
                ),
              ),
              if (kind == SalaryKind.estimate) ...[
                const SizedBox(width: 4),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 5,
                    vertical: 1,
                  ),
                  decoration: BoxDecoration(
                    color: cs.tertiaryContainer.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    'est.',
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: cs.tertiary,
                      fontSize: widget.fontSize - 2,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
              if (hasSalary) ...[
                const SizedBox(width: 4),
                Icon(
                  Icons.edit,
                  size: widget.fontSize - 1,
                  color: cs.onSurfaceVariant.withValues(alpha: 0.4),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

// ── Tags inline edit ─────────────────────────────────────────────────────────
// Mirrors _SalaryInline's click-to-edit pattern. Stores/edits as one
// comma-separated string (matches the DB column and the PATCH payload);
// display renders each comma-separated piece as its own chip.

class _TagsInline extends StatefulWidget {
  final List<String> tags;
  final Future<void> Function(String) onSave;
  final double fontSize;

  const _TagsInline({
    this.tags = const [],
    required this.onSave,
    this.fontSize = 12,
  });

  @override
  State<_TagsInline> createState() => _TagsInlineState();
}

class _TagsInlineState extends State<_TagsInline> {
  bool _editing = false;
  bool _saving = false;
  late TextEditingController _ctrl;
  late List<String> _committedTags;

  @override
  void initState() {
    super.initState();
    _committedTags = widget.tags;
    _ctrl = TextEditingController(text: widget.tags.join(', '));
  }

  @override
  void didUpdateWidget(_TagsInline old) {
    super.didUpdateWidget(old);
    if (old.tags != widget.tags && !_editing) {
      _committedTags = widget.tags;
      _ctrl.text = widget.tags.join(', ');
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
      if (mounted) {
        setState(
          () => _committedTags = value
              .split(',')
              .map((t) => t.trim())
              .where((t) => t.isNotEmpty)
              .toList(),
        );
      }
    } finally {
      if (mounted)
        setState(() {
          _saving = false;
          _editing = false;
        });
    }
  }

  void _cancel() {
    setState(() {
      _editing = false;
      _ctrl.text = _committedTags.join(', ');
    });
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;

    if (_editing) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.label_outline,
            size: widget.fontSize + 2,
            color: cs.primary,
          ),
          const SizedBox(width: 4),
          SizedBox(
            width: 220,
            child: TextField(
              controller: _ctrl,
              autofocus: true,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: cs.onSurface,
                fontSize: widget.fontSize,
              ),
              decoration: InputDecoration(
                isDense: true,
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: 8,
                  vertical: 4,
                ),
                hintText: 'e.g. deftech, ai',
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(6),
                ),
              ),
              onSubmitted: (_) => _save(),
            ),
          ),
          const SizedBox(width: 4),
          if (_saving)
            const SizedBox(
              width: 16,
              height: 16,
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

    final hasTags = _committedTags.isNotEmpty;
    return Tooltip(
      message: 'Click to edit tags',
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        child: GestureDetector(
          onTap: () => setState(() => _editing = true),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.label_outline,
                size: widget.fontSize + 2,
                color: hasTags
                    ? cs.primary
                    : cs.onSurfaceVariant.withValues(alpha: 0.45),
              ),
              const SizedBox(width: 3),
              Text(
                hasTags ? _committedTags.join(', ') : 'Add tags…',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: hasTags
                      ? cs.onSurfaceVariant
                      : cs.onSurfaceVariant.withValues(alpha: 0.45),
                  fontStyle: hasTags ? FontStyle.normal : FontStyle.italic,
                  fontSize: widget.fontSize,
                ),
              ),
              if (hasTags) ...[
                const SizedBox(width: 4),
                Icon(
                  Icons.edit,
                  size: widget.fontSize - 1,
                  color: cs.onSurfaceVariant.withValues(alpha: 0.4),
                ),
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
    // Key Barriers moved to their own block under Warnings (_KeyBarriersBanner).
    final hasContent = p2.category.isNotEmpty || p2.hiddenRisks.isNotEmpty;

    if (!hasContent) return const SizedBox.shrink();

    return _SectionCard(
      title: 'Quick Overview',
      tooltip:
          'Key signals extracted from the JD —\nwho they want, barriers, hidden risks',
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
          if (p2.hiddenRisks.isNotEmpty) ...[
            const SizedBox(height: 10),
            _OverviewList(
              label: 'Hidden Risks',
              items: p2.hiddenRisks,
              icon: Icons.warning_amber_rounded,
              iconColor: const Color(0xFFB26A00),
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
    if (p2.whyApply.isEmpty && p2.whyNotApply.isEmpty)
      return const SizedBox.shrink();
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;

    Widget bullets(List<String> items, Color dotColor) => Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: items
          .map(
            (item) => Padding(
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
            ),
          )
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
            Row(
              children: [
                Icon(
                  Icons.check_circle_outline_rounded,
                  size: 14,
                  color: const Color(0xFF2E7D32),
                ),
                const SizedBox(width: 6),
                Text(
                  'Why apply',
                  style: tt.bodySmall?.copyWith(
                    color: const Color(0xFF2E7D32),
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            bullets(p2.whyApply, const Color(0xFF2E7D32)),
          ],
          if (p2.whyApply.isNotEmpty && p2.whyNotApply.isNotEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 10),
              child: Divider(height: 1),
            ),
          if (p2.whyNotApply.isNotEmpty) ...[
            Row(
              children: [
                Icon(Icons.cancel_outlined, size: 14, color: cs.error),
                const SizedBox(width: 6),
                Text(
                  'Why not apply',
                  style: tt.bodySmall?.copyWith(
                    color: cs.error,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            bullets(p2.whyNotApply, cs.error),
          ],
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

/// Like _OverviewRow, but one bullet per item: several items joined with "; "
/// read as one long sentence and hid how many there were.
class _OverviewList extends StatelessWidget {
  final String label;
  final List<String> items;
  final IconData icon;
  final Color iconColor;

  const _OverviewList({
    required this.label,
    required this.items,
    required this.icon,
    required this.iconColor,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final tt = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(icon, size: 13, color: iconColor),
            const SizedBox(width: 5),
            Text(
              '$label (${items.length})',
              style: tt.bodySmall?.copyWith(
                color: iconColor,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        ...items.map(
          (item) => Padding(
            padding: const EdgeInsets.only(left: 18, bottom: 3),
            child: SelectableText(
              '•  $item',
              style: tt.bodySmall?.copyWith(color: cs.onSurface, height: 1.35),
            ),
          ),
        ),
      ],
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
      ('Domain fit', dims.domainFit),
      ('Execution fit', dims.executionFit),
      ('Strategy fit', dims.strategyFit),
      ('Systems fit', dims.systemsFit),
      ('Stakeholder fit', dims.stakeholderFit),
      ('Overall fit', dims.overallFit),
    ];
    return Column(
      children: rows
          .map(
            (r) =>
                _ScoreBar(label: r.$1, value: r.$2, max: 10, color: cs.primary),
          )
          .toList(),
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
      ('Company tier', dims.companyTier, 4),
      ('Seniority', dims.seniority, 4),
      ('Market scope', dims.marketScope, 3),
      ('Company type', dims.companyType, 3),
      ('Stage fit', dims.companyStageFit, 3),
      ('Domain score', dims.domainScore, 5),
      ('Remote policy', dims.remotePolicy, 3),
      ('Compensation', dims.compensation, 3),
    ];
    return Column(
      children: rows
          .map(
            (r) => _ScoreBar(
              label: r.$1,
              value: r.$2.toDouble(),
              max: r.$3.toDouble(),
              color: cs.secondary,
            ),
          )
          .toList(),
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
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant),
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
                  ? '${value.toInt()}/${max.toInt()}'
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

// ── Role Balance (radar chart, 2026-09-06) ──────────────────────────────────
// Replaces the old _RoleBalanceBar (horizontal bar list) — see
// docs/discovery/role-balance-taxonomy-discovery-2026-09-06.md for how the
// 6-axis taxonomy itself was derived (keyword frequency + clustering + LLM
// open-coding, triangulated across 628 real PM/PO job descriptions).

class _RoleBalanceRadar extends StatelessWidget {
  final Map<String, int> balance;

  const _RoleBalanceRadar({required this.balance});

  // Fixed canonical order — always rendered in this order so the chart's
  // shape is visually comparable across vacancies, regardless of which keys
  // happen to be present in a given analysis_json (contracts/pipeline.py's
  // Phase1Data.role_balance normalizer already maps legacy names onto these).
  static const _axisOrder = [
    'strategy',
    'discovery',
    'delivery',
    'growth',
    'stakeholder',
    'operational',
  ];

  static const _axisLabels = {
    'strategy': 'Strategy',
    'discovery': 'Discovery',
    'delivery': 'Delivery',
    'growth': 'Growth',
    'stakeholder': 'Stakeholder',
    'operational': 'Operational',
  };

  // Deterministic role-shape classification (2026-09-21, revised twice
  // same day). No LLM, pure arithmetic over the already-saved role_balance
  // percentages. Three passes, in order:
  //
  // 1. Absolute >=30% threshold (validated against 88 applied vacancies:
  //    74% resolved to exactly one axis >=30%). Replaced after a live check
  //    on #1647 (delivery=25/strategy=20/stakeholder=20): an absolute
  //    cutoff can't tell a real lead apart from a genuine 3-way tie sitting
  //    at the same max value (several other applied vacancies split
  //    25/25/25) — both landed in "Diffuse" even though #1647's radar
  //    visually read as Delivery-led.
  // 2. Margin between #1 and #2 axis, >=5 points: cleanly resolved 84% of
  //    vacancies and correctly split #1647 (gap=5) from the 25/25/25 ties
  //    (gap=0). Then re-checked #1647 against its own JD text — the JD
  //    explicitly describes the role as combining three functions equally
  //    ("продуктового мислення, операційного управління та бізнес-
  //    аналітики"), and the user's own read of 25/20/20 was "genuinely
  //    blended, slight lean toward Delivery" — not confidently Sharp. A
  //    5-point margin was too lenient: it let a merely-25%-relative lead
  //    (5 of the runner-up's 20) count as decisive.
  // 3. Margin >=10: on the same 88-vacancy set, >=8 and >=10 produce the
  //    *identical* result (58/90, 64%, resolve to a clear #1 either way —
  //    no vacancy has a gap strictly between 8 and 10), so the two are
  //    interchangeable on data seen so far; picked the more conservative
  //    of the two deliberately — a false "Sharp" pushes Phase 3 to write a
  //    narrowly-focused CV for a role that's actually a genuine blend
  //    (the more costly error), while a false "Generalist" only costs a
  //    softer, blended CV for a role that was actually sharp (cheaper).
  //
  // Full history: docs/discovery/role-balance-concentration-analysis-2026-09-21.md §6-7.
  static const _margin = 10;

  List<String> _sortedByValue() {
    final order = [..._axisOrder];
    order.sort((a, b) {
      final cmp = (balance[b] ?? 0).compareTo(balance[a] ?? 0);
      // Ties broken by the fixed canonical axis order so a repeat tie is
      // deterministic rather than depending on sort-algorithm details.
      if (cmp != 0) return cmp;
      return _axisOrder.indexOf(a).compareTo(_axisOrder.indexOf(b));
    });
    return order;
  }

  ({String shape, List<String> axes}) _classifyShape() {
    final byValue = _sortedByValue();
    final v1 = balance[byValue[0]] ?? 0;
    final v2 = balance[byValue[1]] ?? 0;
    final v3 = balance[byValue[2]] ?? 0;
    if (v1 - v2 >= _margin) return (shape: 'Sharp', axes: [byValue[0]]);
    if (v2 - v3 >= _margin)
      return (shape: 'Dual', axes: byValue.take(2).toList());
    return (shape: 'Diffuse', axes: byValue.take(2).toList());
  }

  String _shapeLabel() {
    final s = _classifyShape();
    switch (s.shape) {
      case 'Sharp':
        final ax = s.axes.first;
        return 'Sharp — ${_axisLabels[ax]} (${balance[ax]}%)';
      case 'Dual':
        final pcts = s.axes
            .map((a) => '${_axisLabels[a]} ${balance[a]}%')
            .join(' + ');
        return 'Dual — $pcts';
      default:
        // "Diffuse" is correct here and stays — it names the *structural*
        // concentration parameter (how spread the numbers are), a
        // different layer from "Generalist" (a Phase-1-style *archetype*
        // label, describing what kind of PM this is). Briefly conflated
        // the two (2026-09-21) by displaying "Generalist" here directly —
        // reverted same day once the user drew the distinction. See
        // docs/discovery/role-balance-concentration-analysis-2026-09-21.md
        // §8's correction note for the reasoning; "Generalist" as an
        // archetype is a separate, not-yet-implemented candidate for
        // `phase1_analysis.md` §1.4's archetype vocabulary.
        final top2 = s.axes
            .map((a) => '${_axisLabels[a]} ${balance[a]}%')
            .join(' / ');
        return 'Diffuse — leaning $top2';
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    // Vacancies analyzed before 2026-09-06 have no "growth" value at all —
    // rendered as 0 on the chart, but called out explicitly below so it
    // doesn't silently read as "this role has no growth work" when the
    // truth is "this analysis predates the axis."
    final missingGrowth = !balance.containsKey('growth');

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        // Title + hover tooltip (2026-09-06, user request) — without this,
        // a viewer unfamiliar with the chart has no way to know what it
        // represents. Reuses the same _TooltipTitle pattern as the other
        // analysis sections (Attraction Breakdown, Fit Dimensions, ...).
        _TooltipTitle(
          context: context,
          cs: cs,
          title: 'Role Balance',
          // Bold + dark + larger (2026-09-06, user request) — bold+dark
          // alone still read as "вяло" (flat) at the original 12px; bumped
          // to 16px, the point where the monospace font actually reads as
          // a heading rather than a small label.
          fontWeight: FontWeight.w700,
          color: cs.onSurface,
          fontSize: 16,
          tooltip:
              'Estimated split of this role\'s day-to-day work across '
              '6 dimensions: Strategy (deciding what and why), Discovery '
              '(research), Delivery (shipping), Growth (data-driven '
              'iteration), Stakeholder (coordination), Operational '
              '(process/admin). Derived from the JD by Phase 1 analysis.',
        ),
        // Enlarged (2026-09-06, user request) — the chart's own "Strategy"
        // axis label sits right at the top of its box, so a small gap here
        // read as though the title and chart were one merged block.
        const SizedBox(height: 20),
        SizedBox(
          width: 240,
          height: 210,
          child: RadarChart(
            RadarChartData(
              radarShape: RadarShape.polygon,
              tickCount: 4,
              ticksTextStyle: const TextStyle(
                fontSize: 0,
                color: Colors.transparent,
              ),
              radarBorderData: BorderSide(
                color: cs.outlineVariant.withValues(alpha: 0.4),
              ),
              gridBorderData: BorderSide(
                color: cs.outlineVariant.withValues(alpha: 0.3),
              ),
              tickBorderData: BorderSide(
                color: cs.outlineVariant.withValues(alpha: 0.15),
              ),
              radarBackgroundColor: Colors.transparent,
              titlePositionPercentageOffset: 0.16,
              titleTextStyle: textTheme.labelSmall?.copyWith(
                color: cs.onSurfaceVariant,
              ),
              // Axis label + its own value together (2026-09-21, user
              // request) — a bare label forced the viewer to cross-reference
              // an unlabeled, auto-scaled grid to read off a number; showing
              // the % right on the chart removes that guesswork entirely.
              getTitle: (index, angle) {
                final key = _axisOrder[index];
                final label = _axisLabels[key] ?? key;
                final value = balance[key] ?? 0;
                return RadarChartTitle(text: '$label\n$value%');
              },
              dataSets: [
                RadarDataSet(
                  fillColor: cs.primary.withValues(alpha: 0.22),
                  borderColor: cs.primary,
                  borderWidth: 2,
                  entryRadius: 3,
                  dataEntries: [
                    for (final key in _axisOrder)
                      RadarEntry(value: (balance[key] ?? 0).toDouble()),
                  ],
                ),
              ],
            ),
          ),
        ),
        Padding(
          // Larger gap from the chart + a clear, saturated orange
          // (2026-09-21, user request — the first pick, reused from
          // _WarningsBanner's muted amber `fg`, read as swampy/olive
          // rather than warm on the user's actual screen).
          padding: const EdgeInsets.only(top: 32),
          child: Tooltip(
            message:
                'How the pipeline classifies this role\'s shape from '
                'the numbers above (by the gap between the #1 and #2 axis, '
                'not their absolute size — a >=10-point lead counts). Sharp '
                '= the top axis clearly leads, the CV should write to it '
                'directly. Dual = the top 2 axes are close to each other '
                'but both clearly ahead of the rest, the CV should carry '
                'both together, not pick one. Diffuse = no gap that big '
                'anywhere near the top — a genuine blend, not a clean '
                'lead signal, shown as a lean toward the top 2 axes.',
            preferBelow: true,
            constraints: const BoxConstraints(maxWidth: 260),
            child: Text(
              _shapeLabel(),
              style: textTheme.labelSmall?.copyWith(
                color: const Color(0xFFE65100),
                fontWeight: FontWeight.w700,
              ),
              textAlign: TextAlign.center,
            ),
          ),
        ),
        if (missingGrowth)
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text(
              'No growth-axis data (analyzed before 2026-09-06)',
              style: textTheme.labelSmall?.copyWith(
                color: cs.onSurfaceVariant.withValues(alpha: 0.55),
                fontStyle: FontStyle.italic,
              ),
              textAlign: TextAlign.center,
            ),
          ),
      ],
    );
  }
}

// ── Shared tooltip-aware title chip ──────────────────────────────────────────

class _TooltipTitle extends StatelessWidget {
  final String title;
  final String? tooltip;
  final BuildContext context;
  final ColorScheme cs;
  final FontWeight? fontWeight;
  final Color? color;
  final double? fontSize;

  const _TooltipTitle({
    required this.title,
    required this.tooltip,
    required this.context,
    required this.cs,
    this.fontWeight,
    this.color,
    this.fontSize,
  });

  @override
  Widget build(BuildContext ctx) {
    final text = Text(
      title,
      style: Theme.of(ctx).textTheme.labelMedium?.copyWith(
        color: color ?? cs.onSurfaceVariant,
        fontWeight: fontWeight,
        fontSize: fontSize,
      ),
    );
    if (tooltip == null) return text;
    return Tooltip(
      message: tooltip!,
      preferBelow: true,
      // Caps tooltip width so long descriptions wrap into a compact block
      // instead of stretching into a single line across the whole screen
      // (2026-09-06, user request — noticed on the Role Balance tooltip).
      constraints: const BoxConstraints(maxWidth: 260),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          text,
          const SizedBox(width: 4),
          Icon(
            Icons.info_outline,
            size: 12,
            color: cs.onSurfaceVariant.withValues(alpha: 0.55),
          ),
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
          _TooltipTitle(
            title: title,
            tooltip: tooltip,
            context: context,
            cs: cs,
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
                  _TooltipTitle(
                    title: widget.title,
                    tooltip: widget.tooltip,
                    context: context,
                    cs: cs,
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
                Padding(padding: const EdgeInsets.all(16), child: widget.child),
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
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: Colors.white,
              ),
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
        Container(
          width: 1,
          height: 36,
          color: Colors.white.withValues(alpha: 0.25),
        ),
        MenuAnchor(
          menuChildren: menuItems,
          builder: (context, controller, _) => FilledButton(
            onPressed: () =>
                controller.isOpen ? controller.close() : controller.open(),
            style: FilledButton.styleFrom(
              shape: const RoundedRectangleBorder(borderRadius: rightRadius),
              minimumSize: const Size(34, 36),
              maximumSize: const Size(34, 36),
              padding: EdgeInsets.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: const Icon(
              Icons.arrow_drop_down,
              size: 18,
              color: Colors.white,
            ),
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
      final label = status == 'cv_generating'
          ? 'Generating CV...'
          : 'CV in queue...';
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
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant),
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
            message:
                'CV not generated yet.\nUse Generate CV from the action bar.',
          );
        }
        return Markdown(
          data: cv.cvMd!,
          selectable: true,
          padding: const EdgeInsets.fromLTRB(24, 20, 24, 32),
          styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
            p: Theme.of(
              context,
            ).textTheme.bodyMedium?.copyWith(color: cs.onSurface, height: 1.6),
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
            Text(
              'CV in progress...',
              style: Theme.of(context).textTheme.bodyLarge,
            ),
            const SizedBox(height: 8),
            Text(
              'Cover letter will be available after CV is generated',
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant),
            ),
          ],
        ),
      );
    }

    final cvAsync = ref.watch(vacancyCvProvider(vacancyId));
    return cvAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: Text(
          'Failed to load cover: $e',
          style: TextStyle(color: cs.error),
        ),
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
            p: Theme.of(
              context,
            ).textTheme.bodyMedium?.copyWith(color: cs.onSurface, height: 1.6),
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
          Icon(
            icon,
            size: 48,
            color: cs.onSurfaceVariant.withValues(alpha: 0.4),
          ),
          const SizedBox(height: 12),
          Text(
            message,
            style: Theme.of(
              context,
            ).textTheme.bodyMedium?.copyWith(color: cs.onSurfaceVariant),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}
