/// Single source of truth for "work in progress" vacancy statuses.
///
/// Any status listed here triggers ProcessingWrapper animation + overlay.
/// Add new processing statuses here — UI updates automatically everywhere.
const Map<String, String> kActiveStatuses = {
  'analysis_queued': 'In queue…',
  'analyzing':       'Analyzing job description…',
  'cv_queued':       'CV in queue…',
  'cv_generating':   'Generating CV…',
};

bool isActiveStatus(String status) => kActiveStatuses.containsKey(status);

/// Whether the open vacancy should stay in the detail panel after it left
/// the current folder. A run (re-analysis, CV generation) moves a vacancy to
/// Inbox until it finishes, then back; clearing the panel then made it look
/// as if the vacancy had disappeared. Any other folder change still clears.
bool keepSelectionOutsideFolder(String? freshStatus) =>
    freshStatus != null && isActiveStatus(freshStatus);
