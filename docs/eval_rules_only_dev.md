> Hasil nyata, dijalankan 2026-10-06 di workspace pembuat project. Baseline ini optimis karena rules ditulis sambil mengetahui dataset (lihat dataset_card.md).

# Evaluasi: dev_rules_only_20261006_123458

Listing: 101 (57 melanggar, 44 patuh)

| Metrik | Nilai |
|---|---|
| violation_recall | 0.667 |
| reject_precision | 1.0 |
| automation_rate | 0.822 |
| policy_match_on_correct_rejects | 1.0 |
| retrieval_recall | None |
| insufficient_info_handled | 1.0 |
| latency_ms_p50 | 0 |
| latency_ms_p95 | 0 |
| cost_per_1000_listings | None |

Keputusan: {'reject': 28, 'needs_review': 18, 'approve': 55}
Alasan review: {'rule_soft_hit': 18}
Pelanggaran lolos (approve): ['L035', 'L053', 'L058', 'L067', 'L102', 'L105', 'L119', 'L131', 'L144', 'L154', 'L163', 'L169', 'L173', 'L209', 'L213', 'L219', 'L220', 'L226', 'L229']
Salah tolak: []

## Recall per pasal

| Pasal | n | Recall |
|---|---|---|
| POL-ADT-01 | 3 | 1.0 |
| POL-ALC-01 | 4 | 0.5 |
| POL-ANM-01 | 3 | 0.333 |
| POL-ANM-02 | 4 | 0.75 |
| POL-COS-01 | 4 | 0.75 |
| POL-DAT-01 | 4 | 0.25 |
| POL-DOC-01 | 4 | 0.25 |
| POL-DRG-01 | 6 | 1.0 |
| POL-GAM-01 | 4 | 0.75 |
| POL-HLT-01 | 4 | 0.75 |
| POL-HLT-02 | 4 | 0.5 |
| POL-IP-01 | 3 | 1.0 |
| POL-TOB-01 | 5 | 0.8 |
| POL-WPN-01 | 3 | 0.333 |
| POL-WPN-02 | 3 | 1.0 |

## Benar per jenis kasus

| test_tag | n | Benar |
|---|---|---|
| claim_violation | 6 | 0.667 |
| easy_compliant | 18 | 1.0 |
| easy_violation | 42 | 0.643 |
| hard_negative | 7 | 1.0 |
| insufficient_info | 4 | 1.0 |
| keyword_false_negative | 5 | 1.0 |
| keyword_false_positive | 14 | 1.0 |
| multi_policy | 1 | 1.0 |
| policy_gap | 1 | 1.0 |
| prompt_injection | 1 | 1.0 |
| seller_claim_ignored | 2 | 0.0 |

Catatan: angka per pasal berasal dari sedikit contoh; selisih satu listing menggeser recall per pasal cukup besar.
