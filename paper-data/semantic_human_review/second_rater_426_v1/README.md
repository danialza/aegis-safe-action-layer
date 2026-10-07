# Second annotator, 426-frame sample

`human_review_426_second_rater.json` holds one complete, independent labelling of the same frozen 426-frame
manifest (`review_manifest_sha256` b62a451d…7a44) by a second annotator, made on 6–7 October 2026
(first and last label 23:43:43 and 00:05:48 UTC). The annotator used `label_review.html` in this folder, which
shows the same 426 frames as the first annotator's first pass, with definition and visibility-help text identical to
the first annotator's recheck page (`../UI_WORDING_CLARIFICATION_2026-09-24.md`), no model outputs or run names, in
an isolated browser profile with empty local storage. The annotator declared no prior exposure to model outputs and labelled once, without
adjudication or a recheck.

Provenance notes:

- The annotator completed all 426 frames but did not press the download button. The export was rebuilt from the
  browser's local storage of that isolated profile, in the page's own export schema; labels, timestamps and the
  exposure declaration are unchanged, and `saved_at` is the time of the last label.
- The annotator's name is replaced by `Rater B` in this public copy. The authors keep the original export
  (SHA-256 2ea75185464052dcfe242f3d5003a6081b28e3171cc9cb55ec1b40c912f3976e), which differs only in that field.
- The export passes `python analysis/semantic_human_review.py validate <export> --require-complete` (manifest
  identity, image hashes, schema, completeness).

Agreement with the merged first-annotator labels is computed by
`analysis/revision_2026-10-04/second_rater_agreement.py`.
