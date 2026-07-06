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
