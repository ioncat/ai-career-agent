import 'package:flutter/material.dart';
import '../repositories/vacancy_repository.dart';

/// Queues analysis for one vacancy. When the backend refuses because the job was
/// already applied to under a duplicate (409 `already_applied`), asks the user
/// "Already applied as #X. Analyze anyway?" and on yes retries with force.
///
/// Returns true when analysis was queued, false when the user declined to
/// analyze anyway. Any other error is rethrown for the caller's usual handling.
Future<bool> analyzeWithAppliedGuard(
  BuildContext context,
  VacancyRepository repo,
  int vacancyId,
) async {
  try {
    await repo.analyze(vacancyId);
    return true;
  } on AlreadyAppliedException catch (e) {
    if (!context.mounted) return false;
    final proceed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Already applied'),
        content: Text(
          'Already applied as #${e.twinId} (its CV and cover are there). Analyze anyway?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Analyze anyway'),
          ),
        ],
      ),
    );
    if (proceed != true) return false;
    await repo.analyze(vacancyId, force: true);
    return true;
  }
}
