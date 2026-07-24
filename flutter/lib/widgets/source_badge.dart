import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class SourceBadge extends StatelessWidget {
  final String site;

  const SourceBadge({super.key, required this.site});

  @override
  Widget build(BuildContext context) {
    final color = SourceColors.forSite(site);
    final label = SourceColors.label(site);

    // IntrinsicWidth forces this subtree to be measured at its natural
    // (content) width before Container's own sizing runs. Needed because a
    // Container with `alignment` set and no explicit width EXPANDS to fill
    // any bounded parent constraint, even a loose one (documented Flutter
    // behavior) — this pill sat directly in a Row before 2026-07-24's
    // badge-cluster Wrap fix, where non-flex children get unbounded width,
    // so it stayed shrink-wrapped by luck. Wrap gives its children loose-
    // but-bounded constraints, which triggered the expand case and
    // stretched this badge to the full card width. IntrinsicWidth pins the
    // width to content regardless of what the parent allows, so `alignment`
    // can keep doing its actual job here — vertically centering the text
    // within the fixed 24px height.
    return IntrinsicWidth(
      child: Container(
        height: 24,
        padding: const EdgeInsets.symmetric(horizontal: 10),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(999),
        ),
        alignment: Alignment.center,
        // IntrinsicWidth (above) asks for this pill's natural width, but it
        // still has to cooperate with whatever max width the parent Wrap
        // actually has available — on a narrow card with the trailing time
        // text + star button also competing for space, that can be less
        // than "Djinni"'s natural width. Text wraps to a second line by
        // default when squeezed, breaking the pill's fixed 24px height.
        // maxLines/overflow make it ellipsize on one line instead — found
        // live 2026-07-24, right after the IntrinsicWidth fix above.
        child: Text(
          label,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          softWrap: false,
          style: Theme.of(context).textTheme.labelSmall?.copyWith(
                color: Colors.white,
                fontWeight: FontWeight.w500,
              ),
        ),
      ),
    );
  }
}
