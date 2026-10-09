import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/vacancy.dart';
import '../providers/read_vacancies_provider.dart';
import '../providers/settings_provider.dart';
import '../providers/vacancy_list_provider.dart';
import '../repositories/vacancy_repository.dart';
import '../utils/backend_time.dart';
import '../utils/toast.dart';
import 'failure_widgets.dart';
import 'fit_score_chip.dart';
import 'vac_score_badge.dart';
import 'source_badge.dart';

class VacancyCard extends ConsumerStatefulWidget {
  final VacancyListItem vacancy;
  final bool selected;
  final VoidCallback onTap;
  final void Function(int vacancyId)? onTapRelated;

  /// Tap on an "already applied" line — opens that vacancy in the Applied folder.
  /// Falls back to [onTapRelated] when not given.
  final void Function(int vacancyId)? onTapApplied;

  /// Mass-action mode (BACKLOG "Batch Analysis Mode") — when true, the card
  /// shows a checkbox instead of opening the detail screen on tap.
  final bool multiSelectMode;
  final bool checked;
  final VoidCallback? onCheckToggle;
  final VoidCallback? onLongPress;

  const VacancyCard({
    super.key,
    required this.vacancy,
    required this.onTap,
    this.selected = false,
    this.onTapRelated,
    this.onTapApplied,
    this.multiSelectMode = false,
    this.checked = false,
    this.onCheckToggle,
    this.onLongPress,
  });

  @override
  ConsumerState<VacancyCard> createState() => _VacancyCardState();
}

class _VacancyCardState extends ConsumerState<VacancyCard> {
  bool _hovered = false;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final v = widget.vacancy;
    final readIds = ref.watch(readVacanciesProvider).valueOrNull ?? {};
    final isUnread = v.status == 'fetched' && !readIds.contains(v.id);
    // The "applied to this job: #X" line already says it all about vacancy X — a weaker
    // Dup/Maybe-dup badge pointing at the same X would be the same fact twice.
    final appliedTwin = v.appliedTwinId;
    final duplicatedByThisVacancy =
        (ref.watch(duplicatedByProvider)[v.id] ?? const <int>[])
            .where((id) => id != appliedTwin)
            .toList();
    final onTapApplied = widget.onTapApplied ?? widget.onTapRelated;
    // "applied to this company: #N" (same company, different job) — hidden when the
    // card already shows the this-job line for that very vacancy.
    final companyApplied = v.companyAppliedId;
    final showCompanyApplied =
        companyApplied != null && companyApplied != appliedTwin;
    // Row 3 (status & relations) only renders when it has something to show,
    // so an empty row adds no height.
    final hasStatusBadges =
        v.blockerFlag ||
        (v.duplicateOf != null && v.duplicateOf != appliedTwin) ||
        (v.possibleDuplicateOf != null &&
            v.possibleDuplicateOf != appliedTwin) ||
        duplicatedByThisVacancy.isNotEmpty;

    final highlighted = widget.multiSelectMode
        ? widget.checked
        : widget.selected;
    final bgColor = highlighted
        ? cs.surface
        : _hovered
        ? cs.surfaceContainerLow
        : cs.surface;

    final borderRadius = BorderRadius.circular(12);

    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _hovered = true),
      onExit: (_) => setState(() => _hovered = false),
      child: GestureDetector(
        onTap: widget.multiSelectMode ? widget.onCheckToggle : widget.onTap,
        onLongPress: widget.onLongPress,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          margin: EdgeInsets.zero,
          decoration: BoxDecoration(
            color: bgColor,
            borderRadius: borderRadius,
            border: highlighted
                ? Border.all(
                    color: cs.primary.withValues(alpha: 0.55),
                    width: 1.5,
                  )
                : Border.all(color: cs.outlineVariant.withValues(alpha: 0.3)),
            boxShadow: highlighted
                ? [
                    BoxShadow(
                      color: cs.primary.withValues(alpha: 0.14),
                      blurRadius: 10,
                      spreadRadius: 0,
                      offset: const Offset(0, 2),
                    ),
                  ]
                : [
                    BoxShadow(
                      color: Colors.black.withValues(
                        alpha: _hovered ? 0.08 : 0.04,
                      ),
                      blurRadius: _hovered ? 8 : 2,
                      offset: Offset(0, _hovered ? 2 : 1),
                    ),
                  ],
          ),
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              // Card layout, top to bottom (2026-10-05 — badges were crowding one Wrap):
              //   0  #id (left) · star (right)
              //   1  what it is: source, New, Republished
              //   2  domain tags
              //   3  status & relations: Blocker, Dup, Maybe dup
              //   4  role title        5  company (left) · posted time (right)        then role tags, scores, key barrier, and the red "already applied" lines
              // Rows 1-3 each get the full card width and wrap inside themselves, and an
              // empty row renders nothing, so badges of different kinds never compete.
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  if (widget.multiSelectMode) ...[
                    Icon(
                      widget.checked
                          ? Icons.check_box
                          : Icons.check_box_outline_blank,
                      size: 20,
                      color: widget.checked ? cs.primary : cs.onSurfaceVariant,
                    ),
                    const SizedBox(width: 8),
                  ],
                  // Click copies the bare number (no "#") to the clipboard; the inner
                  // GestureDetector wins over the card's own tap, so the card is not
                  // opened by it.
                  Tooltip(
                    message: 'Click to copy the ID',
                    child: MouseRegion(
                      cursor: SystemMouseCursors.click,
                      child: GestureDetector(
                        behavior: HitTestBehavior.opaque,
                        onTap: () {
                          Clipboard.setData(ClipboardData(text: '${v.id}'));
                          showToast(context, 'Copied ${v.id}');
                        },
                        child: Text(
                          '#${v.id}',
                          style: Theme.of(context).textTheme.bodyMedium
                              ?.copyWith(
                                color: cs.onSurface,
                                fontWeight: FontWeight.w700,
                                fontSize: 11,
                              ),
                        ),
                      ),
                    ),
                  ),
                  const Spacer(),
                  _StarButton(vacancyId: v.id, isStarred: v.starred),
                ],
              ),
              // Row 1: what it is
              if (v.site.isNotEmpty || isUnread || v.republishedAt != null) ...[
                const SizedBox(height: 6),
                Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    if (v.site.isNotEmpty) SourceBadge(site: v.site),
                    if (isUnread) _NewBadge(),
                    if (v.republishedAt != null)
                      Tooltip(
                        message:
                            'Re-published by the employer after being declined.\nMoved back to inbox for review.',
                        preferBelow: false,
                        child: _RepublishedBadge(),
                      ),
                  ],
                ),
              ],
              // Row 2: domain tags
              if (v.tags.isNotEmpty) ...[
                const SizedBox(height: 6),
                Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [for (final tag in v.tags) _TagBadge(tag: tag)],
                ),
              ],
              // Row 3: status & relations
              if (hasStatusBadges) ...[
                const SizedBox(height: 6),
                Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    // No hover tooltip here on purpose — the full reason list
                    // dwarfed the card (found 2026-07-24). Tap the card to see
                    // details instead.
                    if (v.blockerFlag) const _BlockerBadge(),
                    if (v.duplicateOf != null && v.duplicateOf != appliedTwin)
                      Tooltip(
                        message:
                            'Same job found on another source (duplicate of #${v.duplicateOf}).\nTap to view the original posting.',
                        preferBelow: false,
                        child: MouseRegion(
                          cursor: widget.onTapRelated != null
                              ? SystemMouseCursors.click
                              : MouseCursor.defer,
                          child: GestureDetector(
                            onTap: widget.onTapRelated != null
                                ? () => widget.onTapRelated!(v.duplicateOf!)
                                : null,
                            behavior: HitTestBehavior.opaque,
                            child: _DuplicateBadge(originalId: v.duplicateOf!),
                          ),
                        ),
                      ),
                    // Softer tier (2026-10-05): same title+company as #N but the
                    // JD texts differ — flagged side only, no reciprocal badge.
                    if (v.possibleDuplicateOf != null &&
                        v.possibleDuplicateOf != appliedTwin)
                      Tooltip(
                        message:
                            'Looks like the same job as #${v.possibleDuplicateOf}, but the texts differ — check before treating it as a duplicate',
                        preferBelow: false,
                        child: MouseRegion(
                          cursor: widget.onTapRelated != null
                              ? SystemMouseCursors.click
                              : MouseCursor.defer,
                          child: GestureDetector(
                            onTap: widget.onTapRelated != null
                                ? () => widget.onTapRelated!(
                                    v.possibleDuplicateOf!,
                                  )
                                : null,
                            behavior: HitTestBehavior.opaque,
                            child: _PossibleDuplicateBadge(
                              originalId: v.possibleDuplicateOf!,
                            ),
                          ),
                        ),
                      ),
                    // Reciprocal side: this card IS the canonical posting
                    // some other row points at via duplicateOf — same
                    // badge, reversed tooltip/direction, so the
                    // relationship reads from either card.
                    for (final dupId in duplicatedByThisVacancy)
                      Tooltip(
                        message:
                            'Same job also found on another source, posted as #$dupId.\nTap to view that posting.',
                        preferBelow: false,
                        child: MouseRegion(
                          cursor: widget.onTapRelated != null
                              ? SystemMouseCursors.click
                              : MouseCursor.defer,
                          child: GestureDetector(
                            onTap: widget.onTapRelated != null
                                ? () => widget.onTapRelated!(dupId)
                                : null,
                            behavior: HitTestBehavior.opaque,
                            child: _DuplicateBadge(originalId: dupId),
                          ),
                        ),
                      ),
                  ],
                ),
              ],
              const SizedBox(height: 8),
              // Row 4: role title
              Text(
                v.role,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  color: widget.selected ? cs.primary : cs.onSurface,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              const SizedBox(height: 2),
              // Row 5: company (left) · posted time (right). The time shrinks with an
              // ellipsis only after the company name has been given its space.
              if (v.company.isNotEmpty || v.publishedAt != null)
                Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Expanded(
                      child: Text(
                        v.company,
                        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: cs.onSurfaceVariant,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    if (v.publishedAt != null) ...[
                      const SizedBox(width: 8),
                      // Pill, same shape as the other badges: a plain coloured
                      // date blended into the surrounding dark text.
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 7,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: cs.secondaryContainer,
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Text(
                          _relativeTime(v.publishedAt!),
                          maxLines: 1,
                          style: Theme.of(context).textTheme.labelSmall
                              ?.copyWith(
                                color: cs.primary,
                                fontWeight: FontWeight.w700,
                              ),
                        ),
                      ),
                    ],
                  ],
                ),
              if (v.roleTags.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  v.roleTags.join('  '),
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: cs.secondary.withValues(alpha: 0.65),
                    letterSpacing: 0.2,
                  ),
                ),
              ],
              const SizedBox(height: 10),
              // Row 4: scores or status badge — show scores if present regardless of status
              if (v.fitScore != null || v.vacancyScore != null)
                Row(
                  children: [
                    if (v.fitScore != null) FitScoreChip(score: v.fitScore!),
                    if (v.vacancyScore != null) ...[
                      const SizedBox(width: 6),
                      VacScoreBadge(score: v.vacancyScore!),
                    ],
                  ],
                )
              else if (v.failure != null)
                FailurePill(failure: v.failure!),
              // A failure on an already-scored vacancy (CV / cover / PDF) still
              // gets its mark, under the scores.
              if (v.failure != null &&
                  (v.fitScore != null || v.vacancyScore != null)) ...[
                const SizedBox(height: 6),
                FailurePill(failure: v.failure!),
              ],
              // Row 5: key barrier — show if present regardless of status
              if (v.keyBarriers.isNotEmpty) ...[
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 6,
                  ),
                  decoration: BoxDecoration(
                    color: cs.errorContainer.withValues(alpha: 0.3),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: cs.error.withValues(alpha: 0.2)),
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(
                        Icons.warning_amber_rounded,
                        size: 14,
                        color: cs.error,
                      ),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(
                          v.keyBarriers.first,
                          style: Theme.of(context).textTheme.labelSmall
                              ?.copyWith(color: cs.onSurfaceVariant),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              // Plain-text applied notes (replace the old "Applied #N" /
              // "Applied before #N" badges, which nobody could decode at a glance).
              if (appliedTwin != null || showCompanyApplied) ...[
                const SizedBox(height: 8),
                if (appliedTwin != null)
                  _AppliedNote(
                    label: 'You already applied to this job:',
                    vacancyId: appliedTwin,
                    onTap: onTapApplied,
                  ),
                if (appliedTwin != null && showCompanyApplied)
                  const SizedBox(height: 2),
                if (showCompanyApplied)
                  _AppliedNote(
                    label: 'You already applied to this company:',
                    vacancyId: companyApplied,
                    onTap: onTapApplied,
                  ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  String _relativeTime(String iso) => relativeTimeFromBackend(iso);
}

class _NewBadge extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF3E0),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0xFFFFB300), width: 0.8),
      ),
      child: Text(
        'New',
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
          color: const Color(0xFFE65100),
          fontWeight: FontWeight.w700,
          fontSize: 10,
        ),
      ),
    );
  }
}

// User-assigned free-form tag (e.g. "deftech") — distinct from role_tags
// (auto-derived #discovery/#delivery/etc, shown lower on the card). Placed
// in the top badge row, next to source, so batches of similarly-tagged
// vacancies (e.g. a MilTech source) stay visually distinguishable at a
// glance without opening the detail screen. 2026-08-27.
class _TagBadge extends StatelessWidget {
  final String tag;
  const _TagBadge({required this.tag});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
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
          fontSize: 10,
        ),
      ),
    );
  }
}

class _RepublishedBadge extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF8E1),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0xFFFFCA28), width: 0.8),
      ),
      child: Text(
        '↑ Republished',
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
          color: const Color(0xFFF57F17),
          fontWeight: FontWeight.w700,
          fontSize: 10,
        ),
      ),
    );
  }
}

// Pre-filter (EPIC-27) — advisory only, distinct from Phase 2's Key Barriers
// (LLM-derived fit-gap analysis, shown lower in the card). This badge is the
// cheap gate that runs before any real analysis — deliberately more prominent
// (top row, always visible) since its whole point is "look twice before you
// spend time reading this one".
class _BlockerBadge extends StatelessWidget {
  const _BlockerBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: const Color(0xFFFFEBEE),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: const Color(0xFFE57373), width: 0.8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.block_rounded, size: 11, color: Color(0xFFC62828)),
          const SizedBox(width: 3),
          Text(
            // "Possible blocker" measured ~168px wide (2026-07-24) — wider
            // than the other badges combined, and the actual cause of the
            // badge-row overflow, not the layout itself. "Blocker" carries
            // the same meaning (red + block icon already signal "warning")
            // at roughly a third of the width. Full detail is a tap away —
            // see the removed hover tooltip note above.
            'Blocker',
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: const Color(0xFFC62828),
              fontWeight: FontWeight.w700,
              fontSize: 10,
            ),
          ),
        ],
      ),
    );
  }
}

// Red; amber looked washed out and green fought with the green source
// badge (owner, 2026-10-05).
const _kAppliedNoteColor = Color(0xFFC62828);

// One plain-text line at the bottom of the card: "You already applied to this exact
// job: #N" (an applied duplicate exists) or "... to this company: #N" (another job at
// the same company). Red; the whole line opens vacancy N.
class _AppliedNote extends StatelessWidget {
  final String label;
  final int vacancyId;
  final void Function(int vacancyId)? onTap;
  const _AppliedNote({
    required this.label,
    required this.vacancyId,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final base = Theme.of(
      context,
    ).textTheme.labelMedium?.copyWith(color: _kAppliedNoteColor, fontSize: 10);
    return MouseRegion(
      cursor: onTap != null ? SystemMouseCursors.click : MouseCursor.defer,
      child: GestureDetector(
        onTap: onTap != null ? () => onTap!(vacancyId) : null,
        behavior: HitTestBehavior.opaque,
        child: Row(
          children: [
            const Icon(Icons.check_circle, size: 11, color: _kAppliedNoteColor),
            const SizedBox(width: 4),
            Flexible(
              child: Text(
                label,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: base,
              ),
            ),
            const SizedBox(width: 4),
            Text(
              '#$vacancyId',
              style: base?.copyWith(
                fontWeight: FontWeight.w700,
                decoration: TextDecoration.underline,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DuplicateBadge extends StatelessWidget {
  final int originalId;
  const _DuplicateBadge({required this.originalId});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: cs.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: cs.outlineVariant, width: 0.8),
      ),
      child: Text(
        'Dup #$originalId',
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
          color: cs.onSurfaceVariant,
          fontWeight: FontWeight.w600,
          fontSize: 10,
        ),
      ),
    );
  }
}

// Visually weaker than _DuplicateBadge: no fill, faint outline, regular weight.
class _PossibleDuplicateBadge extends StatelessWidget {
  final int originalId;
  const _PossibleDuplicateBadge({required this.originalId});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        border: Border.all(
          color: cs.outlineVariant.withValues(alpha: 0.6),
          width: 0.8,
        ),
      ),
      child: Text(
        'Maybe dup #$originalId',
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
          color: cs.onSurfaceVariant.withValues(alpha: 0.75),
          fontWeight: FontWeight.w400,
          fontSize: 10,
        ),
      ),
    );
  }
}

// ─── Star toggle ─────────────────────────────────────────────────────────────

class _StarButton extends ConsumerStatefulWidget {
  final int vacancyId;
  final bool isStarred;

  const _StarButton({required this.vacancyId, required this.isStarred});

  @override
  ConsumerState<_StarButton> createState() => _StarButtonState();
}

class _StarButtonState extends ConsumerState<_StarButton> {
  late bool _starred;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _starred = widget.isStarred;
  }

  @override
  void didUpdateWidget(_StarButton old) {
    super.didUpdateWidget(old);
    if (old.isStarred != widget.isStarred) _starred = widget.isStarred;
  }

  Future<void> _toggle() async {
    if (_loading) return;
    final next = !_starred;
    setState(() {
      _starred = next;
      _loading = true;
    });
    try {
      final apiUrl =
          ref.read(settingsProvider).valueOrNull?.apiUrl ??
          'http://localhost:8080';
      await VacancyRepository(
        baseUrl: apiUrl,
      ).setStarred(widget.vacancyId, next);
      if (mounted) ref.read(vacancyListProvider.notifier).refresh();
    } catch (_) {
      if (mounted) setState(() => _starred = !next);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: _toggle,
        child: Padding(
          padding: const EdgeInsets.only(left: 4),
          child: Icon(
            _starred ? Icons.star_rounded : Icons.star_outline_rounded,
            // Sized and coloured like the bold #id on the other end of row 0, so
            // the star is not a faint counterweight to it. Still an outline.
            size: 18,
            color: _starred
                ? const Color(0xFFFFB300)
                : Theme.of(
                    context,
                  ).colorScheme.onSurface.withValues(alpha: 0.85),
          ),
        ),
      ),
    );
  }
}
