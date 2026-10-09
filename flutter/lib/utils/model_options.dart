/// Options for a model DropdownButton. Flutter asserts that the selected
/// value matches exactly one item, so the list must have no duplicates and
/// must contain the value (2026-10-09: Ollama's /api/tags returned
/// "gemma4:e2b" twice and the Settings model box turned into a red assertion).
library;

/// The available models without duplicates (first occurrence wins, order
/// kept), plus [selected] at the end if it is set but missing from the list,
/// so the dropdown never asserts; `selectedMissing` tells the caller to mark it.
({List<String> items, bool selectedMissing}) modelDropdownOptions(
  List<String> available,
  String? selected,
) {
  final seen = <String>{};
  final items = [
    for (final m in available)
      if (m.isNotEmpty && seen.add(m)) m,
  ];
  final missing =
      selected != null && selected.isNotEmpty && !seen.contains(selected);
  if (missing) items.add(selected);
  return (items: items, selectedMissing: missing);
}
