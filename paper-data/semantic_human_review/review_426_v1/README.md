# Frozen human review / بازبینی انسانی

## فارسی

فقط `label_review.html` را برای برچسب‌گذاری باز کنید؛ فایل manifest برای تحلیل‌گر است و گروه نمونه‌گیری را آشکار می‌کند. ۴۲۶ تصویر به ترتیب مخلوط نمایش داده می‌شوند: تمام ۷۶ اختلاف دو مدل، تمام ۵۰ توافق مثبت و نمونهٔ تصادفی ۳۰۰تایی از ۲۰۳۲ توافق منفی. هیچ جواب مدل یا برچسب پیشنهادی در صفحه نمایش داده نمی‌شود.

برای هر تصویر فقط آنچه دیده می‌شود ثبت کنید: «دست هست»، «دست نیست» یا «نامشخص». دستکشِ پوشیده‌شده روی دست، دست محسوب می‌شود؛ گریپر و دستکش خالی دست نیستند. پوشش پوست با دستکش به‌تنهایی پوشیدگی دید نیست؛ پوشیدگی یعنی بخشی از دست پشت جسم، ربات یا لبهٔ تصویر پنهان باشد. اگر چند دست دیده می‌شود، وجود دست کافی است؛ «کامل» یعنی حداقل یک دست کامل دیده می‌شود. در صورت ترکیب پوست برهنه و دستکش در دست‌های دیده‌شده، گزینهٔ ترکیبی را ثبت کنید.

نام/شناسهٔ برچسب‌زن و اینکه قبلاً جواب مدل‌ها را دیده‌اید ثبت شود. اگر گزارش یا نمونه‌های دارای جواب مدل‌ها را قبلاً دیده‌اید، گزینهٔ «بله» را انتخاب کنید؛ صفحهٔ بدون جواب مدل، مواجههٔ قبلی را از بین نمی‌برد. ذخیرهٔ مرورگر جای فایل خروجی را نمی‌گیرد: مرتب خروجی JSON دانلود کنید. برای برچسب‌زن دوم فایل و شناسهٔ جدا و پروفایل مرورگر/ذخیرهٔ محلی خالی و مستقل نگه دارید؛ قبل از مقایسهٔ نظرها، پاسخ یکدیگر را نبینید. هنگام برچسب‌گذاری سراغ گزارش مدل‌ها نروید. این مرحله برچسب انسانی را خودکار تولید نمی‌کند و پاسخ تمام ایرادهای داوری نیست.

## English

The design is frozen before human review. Sampling: census of all 76 disagreements and all 50 positive agreements, plus simple random sampling without replacement of 300/2032 negative agreements. Negative sampling seed: 20260924; independent display shuffle seed: 20260925. Inclusion probabilities are 1, 1, and 300/2032; weights are 1, 1, and 2032/300. Analyst metadata and predictions are excluded from the annotation UI.

Do not estimate population accuracy by counting unweighted answers in this enriched sample. A subsequent analysis must retain uncertain labels as unresolved, report their weighted prevalence/coverage, use the known inclusion probabilities, quantify uncertainty and account for correlated frames/runs. In particular, zero observed errors in the sampled negative stratum is not proof that no unsampled errors exist.

This is retrospective human review of compressed, same-session video frames and current-model replay. It does not validate sensor-exposure timing, exact historical live inputs, new-subject/new-session performance, physical or whole-arm safety, or comparative AEGIS efficacy. Prior exposure to model outputs is declared, not erased by this blind UI: a reviewer who saw the report/examples must choose yes. Do not consult model outputs while annotating. A separate second reviewer is recommended, using an isolated blank browser/local-storage profile; preserve independent exports and disagreements before adjudication.

Export schema: aegis-human-review-v1. `label_source` must be human. Required top-level keys: schema_version, label_source, review_manifest_sha256, annotator, prior_model_exposure (yes/no/unsure), labels, saved_at. Each label requires id, label (hand/no_hand/uncertain), cover, visibility, note, reviewed_at. For hand: cover is bare/glove/mixed/uncertain and visibility is full/partial/uncertain. For no_hand or uncertain: cover and visibility must be null. Timestamps must be timezone-aware ISO-8601 strings. Partial exports can be validated; final completeness requires --require-complete.

Run validation from the project root using the existing Python environment:

    python analysis/semantic_human_review.py validate /path/to/human-export.json
    python analysis/semantic_human_review.py validate /path/to/human-export.json --require-complete

The validator checks manifest identity, source image hashes, IDs, duplicate labels, human provenance declaration, annotator/exposure fields, condition combinations, timestamps, and completeness when requested. It cannot certify that a human actually performed the review or that the judgment is correct. It produces no empirical accuracy metric and never changes originals.
