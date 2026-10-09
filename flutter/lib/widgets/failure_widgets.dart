import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/vacancy_failure.dart';
import '../providers/settings_provider.dart';
import '../providers/vacancy_list_provider.dart';
import '../repositories/vacancy_repository.dart';
import '../utils/backend_time.dart';
import '../utils/error_snackbar.dart';
import '../utils/toast.dart';

/// The one card mark for every failure kind (notifications phase 1). Replaces
/// the per-type badges ("Analysis failed · tap to retry", "Fetch failed").
class FailurePill extends StatelessWidget {
  final VacancyFailure failure;

  const FailurePill({super.key, required this.failure});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final detail = failure.reason.trim();
    return Tooltip(
      message: [
        failure.message,
        if (detail.isNotEmpty) detail,
        'Open it to retry.',
      ].join('\n'),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: cs.errorContainer,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: cs.error),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline_rounded, size: 13, color: cs.error),
            const SizedBox(width: 4),
            Text(
              failure.shortTitle,
              style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: cs.onErrorContainer,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// The one panel block for every failure kind, shown under the header in both
/// detail states (`_JdModeView` and the tabbed view) — the same widget in
/// both, per the header rule in CLAUDE.md. It is state, not a message: no
/// dismiss, it goes away when the backend clears the failure. It can be
/// collapsed to one line for the session.
class FailureBlock extends ConsumerStatefulWidget {
  final int vacancyId;
  final VacancyFailure failure;

  /// The vacancy's current status: while a run is in progress the failure is
  /// from the previous run, so Retry waits (a second click would only get
  /// "already in progress").
  final String? status;

  const FailureBlock({
    super.key,
    required this.vacancyId,
    required this.failure,
    this.status,
  });

  @override
  ConsumerState<FailureBlock> createState() => _FailureBlockState();
}

class _FailureBlockState extends ConsumerState<FailureBlock> {
  bool _collapsed = false;
  bool _retrying = false;

  VacancyRepository get _repo => VacancyRepository(
    baseUrl:
        ref.read(settingsProvider).valueOrNull?.apiUrl ??
        'http://localhost:8080',
  );

  /// One mapping from the failure's retry call to the backend.
  Future<void> _runRetry() async {
    final f = widget.failure;
    final id = widget.vacancyId;
    switch (f.retryCall) {
      case RetryCall.restore:
        await _repo.restore(id);
      case RetryCall.resetAndAnalyze:
        await _repo.reset(id);
        await _repo.analyze(id);
      case RetryCall.generateCv:
        await _repo.generateCv(id, language: f.lang ?? 'auto');
      case RetryCall.generateCover:
        await _repo.generateCover(id);
      case RetryCall.renderPdf:
        await _repo.renderPdf(id, f.target!);
      case null:
        throw Exception('This failure cannot be retried from here');
    }
  }

  Future<void> _retry() async {
    setState(() => _retrying = true);
    try {
      await _runRetry();
      if (mounted) {
        ref.read(vacancyListProvider.notifier).refresh();
        showToast(context, '${widget.failure.retryLabel ?? 'Retry'}: started');
      }
    } catch (e) {
      if (mounted) showErrorSnackBar(context, 'Error: $e');
    } finally {
      if (mounted) setState(() => _retrying = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final f = widget.failure;
    final detail = f.reason.trim();
    final fg = cs.onErrorContainer;
    final running = VacancyFailure.runInProgress(widget.status);
    final retryLabel = f.retryLabel;
    final when = f.at.isEmpty ? '' : relativeTimeFromBackend(f.at);

    final header = Row(
      children: [
        Icon(Icons.error_outline_rounded, size: 20, color: cs.error),
        const SizedBox(width: 8),
        Expanded(
          child: Text.rich(
            TextSpan(
              children: [
                TextSpan(
                  text: f.title,
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    color: fg,
                    fontSize: 15,
                  ),
                ),
                if (when.isNotEmpty)
                  TextSpan(
                    text: '  ·  $when',
                    style: TextStyle(
                      color: fg.withValues(alpha: 0.7),
                      fontSize: 12.5,
                    ),
                  ),
              ],
            ),
          ),
        ),
        if (retryLabel != null)
          FilledButton.icon(
            onPressed: _retrying || running ? null : _retry,
            icon: _retrying || running
                ? const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: Colors.white,
                    ),
                  )
                : const Icon(Icons.refresh_rounded, size: 16),
            label: Text(running ? 'Running…' : retryLabel),
            style: FilledButton.styleFrom(
              backgroundColor: cs.error,
              foregroundColor: cs.onError,
              padding: const EdgeInsets.symmetric(horizontal: 12),
              minimumSize: const Size(0, 34),
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
          ),
        IconButton(
          tooltip: _collapsed ? 'Show details' : 'Collapse',
          icon: Icon(
            _collapsed ? Icons.expand_more_rounded : Icons.expand_less_rounded,
            size: 20,
            color: fg,
          ),
          onPressed: () => setState(() => _collapsed = !_collapsed),
        ),
      ],
    );

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      padding: const EdgeInsets.fromLTRB(14, 8, 6, 10),
      decoration: BoxDecoration(
        color: cs.errorContainer,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: cs.error, width: 1.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          header,
          if (running) ...[
            const SizedBox(height: 4),
            Text(
              'A new run is in progress; this mark is from the previous one '
              'and clears when the new run succeeds.',
              style: TextStyle(
                color: fg,
                fontStyle: FontStyle.italic,
                height: 1.35,
              ),
            ),
          ],
          if (!_collapsed) ...[
            const SizedBox(height: 4),
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: Text(f.message, style: TextStyle(color: fg, height: 1.35)),
            ),
            if (detail.isNotEmpty) ...[
              const SizedBox(height: 6),
              Padding(
                padding: const EdgeInsets.only(right: 8),
                child: SelectableText(
                  detail,
                  style: TextStyle(
                    color: fg,
                    fontSize: 12.5,
                    fontFamily: 'JetBrains Mono',
                  ),
                ),
              ),
            ],
          ],
        ],
      ),
    );
  }
}
