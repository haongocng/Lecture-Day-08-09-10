# Báo Cáo Cá Nhân — Lab Day 10: Data Pipeline & Observability

**Họ và tên:** Nguyễn Ngọc Hảo  
**Vai trò:** Ingestion / Cleaning / Embed / Monitoring — Cleaning & Embed  
**Ngày nộp:** 10/06/2026  
**Run chính:** `cohere-final-clean`  

---

## 1. Tôi phụ trách phần nào? (80–120 từ)

**File / module:**

- `transform/cleaning_rules.py`
- `quality/expectations.py`
- `embedding_backend.py`
- `etl_pipeline.py`
- `eval_retrieval.py`
- `grading_run.py`

Tôi phụ trách phần cleaning, expectation và chuyển pipeline sang dùng Cohere embedding thay vì embedding local. Ở tầng dữ liệu, tôi kiểm tra `data/raw/policy_export_dirty.csv`, so sánh `doc_id` trong raw với `ALLOWED_DOC_IDS`, rồi phát hiện `access_control_sop` là nguồn hợp lệ nhưng bị quarantine nhầm. Tôi cũng kết nối phần cleaning với embed/eval: sau khi cleaned CSV ổn, pipeline upsert vào Chroma collection `day10_kb`, rồi chạy eval và grading để xác nhận retrieval dùng đúng corpus.

**Bằng chứng:** run `cohere-final-clean` có `raw_records=247`, `cleaned_records=35`, `quarantine_records=212`, và log `embed_upsert count=35 collection=day10_kb provider=cohere model=embed-multilingual-v3.0`.

---

## 2. Một quyết định kỹ thuật (100–150 từ)

Tôi chọn tách embedding thành `embedding_backend.py` thay vì viết trực tiếp trong từng script. Quyết định này giúp `etl_pipeline.py`, `eval_retrieval.py` và `grading_run.py` dùng cùng một cấu hình embedding, tránh tình trạng ETL embed bằng một model nhưng eval query bằng model khác. Backend chính là Cohere với `COHERE_EMBEDDING_MODEL=embed-multilingual-v3.0`; document dùng `input_type="search_document"`, còn câu hỏi eval/grading dùng `input_type="search_query"`. Tôi vẫn giữ fallback local `SentenceTransformerBackend` nếu cần chạy offline. Về validate, tôi đặt `required_doc_ids_present` và `no_repeated_workday_phrase` là `halt`, vì thiếu source grading hoặc để lỗi sync vào corpus sẽ làm agent trả lời sai. Riêng `no_ambiguous_chunk_marker` để `warn`, vì nó là tín hiệu chất lượng cần theo dõi nhưng không nhất thiết luôn làm dừng pipeline trong mọi môi trường.

---

## 3. Một lỗi hoặc anomaly đã xử lý (100–150 từ)

Anomaly lớn nhất là pipeline ban đầu thiếu `access_control_sop` trong allowlist, trong khi `data/grading_questions.json` có câu `gq_d10_10` yêu cầu `expect_top1_doc_id="access_control_sop"`. Nếu giữ nguyên baseline, các chunk access control hợp lệ sẽ bị quarantine và grading không thể trả lời đúng câu Level 4 Admin Access. Tôi đã thêm `access_control_sop` vào `ALLOWED_DOC_IDS` và đồng bộ với `contracts/data_contract.yaml`. Ngoài ra, pipeline còn bị halt ở run đầu `cohere-smoke` do expectation `hr_leave_no_stale_10d_annual` fail với `violations=2`: cleaned data vẫn còn nội dung HR 2025 “10 ngày phép năm”. Tôi sửa bằng rule quarantine theo nội dung `"bản HR 2025"` hoặc `"10 ngày phép năm"`, không chỉ dựa vào `effective_date`, vì raw có trường hợp ngày mới nhưng text vẫn stale.

---

## 4. Bằng chứng trước / sau (80–120 từ)

Tôi dùng Sprint 3 để chứng minh before/after. Run lỗi là `inject-bad`, chạy với `--no-refund-fix --skip-validate`; expectation `refund_no_stale_14d_window` fail với `violations=2` nhưng vẫn embed để tạo bằng chứng xấu. Dòng eval then chốt:

```text
after_inject_bad.csv: q_refund_window, top1_doc_id=policy_refund_v4, contains_expected=no, hits_forbidden=yes, top1_doc_expected=yes
after_fix_eval.csv: q_refund_window, top1_doc_id=policy_refund_v4, contains_expected=yes, hits_forbidden=no, top1_doc_expected=yes
```

Sau đó tôi chạy lại pipeline sạch `cohere-final-clean` để restore Chroma snapshot. Grading chính thức `artifacts/eval/grading_run.jsonl` có đủ 10 câu pass: `contains_expected=true`, `hits_forbidden=false`, `top1_doc_matches=true`.

---

## 5. Cải tiến tiếp theo (40–80 từ)

Nếu có thêm 2 giờ, tôi sẽ chuyển các rule versioning như `hr_leave_min_effective_date` và danh sách `allowed_doc_ids` sang đọc trực tiếp từ `contracts/data_contract.yaml` thay vì hard-code trong `cleaning_rules.py`. Như vậy khi thêm source mới hoặc đổi cutoff policy, nhóm chỉ cần cập nhật contract, giảm nguy cơ code và tài liệu bị lệch nhau.
