import 'package:flutter/material.dart';

import 'toast.dart';

/// Shows an error toast that stays on screen until the user closes it —
/// never auto-dismisses after a few seconds.
///
/// Confirmed 2026-09-08 (vacancy #1504, "Check blockers" OAuth failure): the
/// default SnackBar duration made real failure reasons disappear before the
/// user could read them, especially on longer backend error messages.
/// Since 2026-10-08 it is a top toast (`toast.dart`), not a bottom SnackBar.
void showErrorSnackBar(BuildContext context, String message) {
  showToast(context, message, kind: ToastKind.error);
}
