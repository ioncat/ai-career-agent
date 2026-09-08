import 'package:flutter/material.dart';

/// Shows an error SnackBar that stays on screen until the user closes it
/// themselves (or it's replaced by another SnackBar) — never auto-dismisses
/// after a few seconds.
///
/// Confirmed 2026-09-08 (vacancy #1504, "Check blockers" OAuth failure): the
/// default SnackBar duration made real failure reasons disappear before the
/// user could read them, especially on longer backend error messages.
void showErrorSnackBar(BuildContext context, String message) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: Theme.of(context).colorScheme.error,
        duration: const Duration(days: 1),
        behavior: SnackBarBehavior.floating,
        action: SnackBarAction(
          label: 'Закрыть',
          textColor: Theme.of(context).colorScheme.onError,
          onPressed: () {
            ScaffoldMessenger.of(context).hideCurrentSnackBar();
          },
        ),
      ),
    );
}
