# Report — Day 10 Lab: Data Pipeline & Observability

**Ngày chạy:** 2026-06-10  
**Môi trường:** `Lecture-Day-08-09-10/day10/lab/venv`  
**Python dùng để chạy:** `.\venv\Scripts\python.exe`  
**Run sạch cuối cùng:** `cohere-final-clean`  
**Run inject lỗi:** `inject-bad`

---

## 1. Mục tiêu đã xử lý

Mục tiêu chính là hoàn thiện pipeline `ingest -> clean -> validate -> embed -> eval/grading` cho lab Day 10, nhưng không dùng embedding local. Pipeline đã được chuyển sang dùng Cohere AI để embedding trong môi trường venv của lab.

Kết quả cuối:

- Pipeline chuẩn chạy thành công: `PIPELINE_OK`
- Grading chính thức 10 câu: pass toàn bộ
- Eval tự kiểm 21 câu: pass toàn bộ sau fix
- Có artifact before/after cho Sprint 3 inject corruption
- Chroma index cuối cùng đã được restore về snapshot sạch sau khi inject-bad

---

## 2. Cấu hình embedding và vector store

### Embedding provider

Pipeline hiện dùng Cohere:

```env
EMBEDDING_PROVIDER=cohere
COHERE_EMBEDDING_MODEL=embed-multilingual-v3.0
COHERE_API_KEY=<secret trong .env>
```

Model sử dụng:

- Provider: `cohere`
- Model: `embed-multilingual-v3.0`
- Document embedding input type: `search_document`
- Query embedding input type: `search_query`
- Embedding type: `float`

### Fallback local

Vẫn giữ fallback local nếu đổi:

```env
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

Tuy nhiên trong các lần chạy report này, pipeline dùng Cohere, không dùng SentenceTransformers local.

### ChromaDB

```env
CHROMA_DB_PATH=./chroma_db
CHROMA_COLLECTION=day10_kb
```

Pipeline dùng Chroma PersistentClient. Sau mỗi run:

- Upsert theo `chunk_id`
- Prune vector id không còn trong cleaned CSV
- Nhờ đó index hoạt động như snapshot publish, tránh vector cũ làm fail grading

---

## 3. Chunk size / chunking strategy

Lab này không có bước chunking runtime kiểu tách văn bản theo token/character size.

Nguồn raw `data/raw/policy_export_dirty.csv` đã có sẵn cột `chunk_text`. Vì vậy:

- Mỗi dòng hợp lệ sau clean tương ứng với 1 chunk
- `chunk_id` được tạo ổn định từ `doc_id`, `chunk_text`, và số thứ tự `seq`
- Chunk size không cấu hình bằng tham số như `chunk_size=...`
- Số chunk sau clean ở run final: `35`

Nói ngắn gọn: **chunk size = theo từng record `chunk_text` có sẵn trong raw CSV**, không tách lại bằng tokenizer.

---

## 4. Các file đã xử lý

### `embedding_backend.py`

File mới được thêm để gom logic embedding vào một chỗ.

Nội dung xử lý:

- Tạo interface `EmbeddingBackend`
- Thêm `CohereEmbeddingBackend`
- Thêm fallback `SentenceTransformerBackend`
- Thêm hàm `get_embedding_backend()`

Logic chọn provider:

- Nếu `EMBEDDING_PROVIDER=cohere`: dùng Cohere
- Nếu không set provider nhưng có `COHERE_API_KEY`: mặc định dùng Cohere
- Nếu `EMBEDDING_PROVIDER=local`: dùng SentenceTransformers

Điểm quan trọng:

- Documents dùng `input_type="search_document"`
- Questions/eval queries dùng `input_type="search_query"`

---

### `etl_pipeline.py`

Đã sửa phần embed.

Trước đó pipeline dùng:

```python
SentenceTransformerEmbeddingFunction(model_name=model_name)
```

Sau khi sửa:

- Import `get_embedding_backend`
- Tạo embedding bằng Cohere
- Gọi `col.upsert(..., embeddings=embeddings)` thay vì để Chroma tự embed bằng local model
- Log thêm provider/model:

```text
embed_upsert count=35 collection=day10_kb provider=cohere model=embed-multilingual-v3.0
```

Kết quả run final:

```text
run_id=cohere-final-clean
raw_records=247
cleaned_records=35
quarantine_records=212
PIPELINE_OK
```

---

### `eval_retrieval.py`

Đã sửa để eval retrieval dùng cùng embedding backend với ETL.

Trước đó:

- Query bằng `query_texts`
- Chroma tự embed query bằng local SentenceTransformer

Sau khi sửa:

- Query text được embed qua Cohere với `search_query`
- Gọi Chroma bằng `query_embeddings`

Lệnh đã chạy:

```powershell
.\venv\Scripts\python.exe -X utf8 eval_retrieval.py --out artifacts\eval\after_fix_eval.csv
```

Kết quả:

- 21 dòng eval
- Không có `contains_expected=no`
- Không có `hits_forbidden=yes`
- Không có `top1_doc_expected=no`

---

### `grading_run.py`

Đã sửa tương tự `eval_retrieval.py`.

Mục tiêu:

- Grading chính thức 10 câu dùng đúng Cohere query embedding
- Không phụ thuộc local embedding model

Lệnh đã chạy:

```powershell
.\venv\Scripts\python.exe -X utf8 grading_run.py --out artifacts\eval\grading_run.jsonl
```

Kết quả:

- `gq_d10_01` đến `gq_d10_10` đều pass
- `contains_expected=true` toàn bộ
- `hits_forbidden=false` toàn bộ
- `top1_doc_matches=true` toàn bộ

---

### `transform/cleaning_rules.py`

Đã sửa cleaning rules để pipeline pass dữ liệu thật.

Các thay đổi chính:

1. Thêm `access_control_sop` vào `ALLOWED_DOC_IDS`
2. Quarantine chunk có marker `"Nội dung không rõ ràng"`
3. Quarantine HR stale theo nội dung, ví dụ `"bản HR 2025"` hoặc `"10 ngày phép năm"`
4. Chuẩn hóa lỗi lặp cụm `"làm việc làm việc"` thành `"làm việc"`
5. Giữ rule fix refund stale: `"14 ngày làm việc"` -> `"7 ngày làm việc"`

Lý do quan trọng:

- Raw CSV có 8 dòng `access_control_sop`
- Grading câu `gq_d10_10` yêu cầu top-1 là `access_control_sop`
- Nếu không thêm allowlist, source hợp lệ này bị quarantine nhầm

---

### `quality/expectations.py`

Đã thêm expectations mới.

Expectations mới:

1. `required_doc_ids_present`
   - Severity: `halt`
   - Kiểm tra các doc bắt buộc cho grading đều có mặt sau clean
   - Gồm: `policy_refund_v4`, `sla_p1_2026`, `it_helpdesk_faq`, `hr_leave_policy`, `access_control_sop`

2. `no_ambiguous_chunk_marker`
   - Severity: `warn`
   - Kiểm tra không còn marker `"Nội dung không rõ ràng"` trong cleaned data

3. `no_repeated_workday_phrase`
   - Severity: `halt`
   - Kiểm tra không còn lỗi sync lặp cụm `"làm việc làm việc"`

Expectation có tác động rõ trong run inject:

```text
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=2
WARN: expectation failed but --skip-validate -> tiếp tục embed
```

---

### `contracts/data_contract.yaml`

Đã đồng bộ contract với pipeline.

Thay đổi:

- Thêm canonical source:

```yaml
- path: "data/docs/access_control_sop.txt"
  doc_id: "access_control_sop"
```

- Thêm vào `allowed_doc_ids`:

```yaml
- access_control_sop
```

---

### `requirements.txt`

Đã đổi dependency embedding.

Trước:

```txt
sentence-transformers>=2.6.0
```

Sau:

```txt
cohere>=7.0.0
```

Các dependency chính hiện dùng:

```txt
python-dotenv>=1.0.0
chromadb>=0.4.22
cohere>=7.0.0
pyyaml>=6.0.1
pytest>=8.0.0
```

---

### `.env.example`

Đã cập nhật để thể hiện cấu hình Cohere.

Thêm:

```env
EMBEDDING_PROVIDER=cohere
COHERE_EMBEDDING_MODEL=embed-multilingual-v3.0
COHERE_API_KEY=
```

Giữ fallback local:

```env
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

---

## 5. Các lệnh đã chạy

### Cài dependency vào venv

```powershell
.\venv\Scripts\pip.exe install python-dotenv chromadb cohere pyyaml pytest
```

### Pipeline bị halt ban đầu

```powershell
.\venv\Scripts\python.exe etl_pipeline.py run --run-id cohere-smoke
```

Kết quả:

```text
expectation[hr_leave_no_stale_10d_annual] FAIL (halt) :: violations=2
PIPELINE_HALT
```

### Pipeline sạch sau khi sửa

```powershell
.\venv\Scripts\python.exe -X utf8 etl_pipeline.py run --run-id cohere-final-clean
```

Kết quả:

```text
raw_records=247
cleaned_records=35
quarantine_records=212
embed_upsert count=35 collection=day10_kb provider=cohere model=embed-multilingual-v3.0
PIPELINE_OK
```

### Freshness

```powershell
.\venv\Scripts\python.exe -X utf8 etl_pipeline.py freshness --manifest artifacts\manifests\manifest_cohere-final-clean.json
```

Kết quả:

```text
FAIL {"latest_exported_at": "2026-04-11T00:00:00", "age_hours": 1448.37, "sla_hours": 24.0, "reason": "freshness_sla_exceeded"}
```

Giải thích: dữ liệu mẫu có timestamp cũ, nên freshness fail là hợp lý. Pipeline vẫn pass; phần này cần ghi trong runbook/report.

### Inject corruption

```powershell
.\venv\Scripts\python.exe -X utf8 etl_pipeline.py run --run-id inject-bad --no-refund-fix --skip-validate
```

Kết quả:

```text
expectation[refund_no_stale_14d_window] FAIL (halt) :: violations=2
WARN: expectation failed but --skip-validate -> tiếp tục embed
PIPELINE_OK
```

### Eval after inject

```powershell
.\venv\Scripts\python.exe -X utf8 eval_retrieval.py --out artifacts\eval\after_inject_bad.csv
```

Kết quả:

- `q_refund_window` có `contains_expected=no`
- `q_refund_window` có `hits_forbidden=yes`

### Eval after fix

```powershell
.\venv\Scripts\python.exe -X utf8 eval_retrieval.py --out artifacts\eval\after_fix_eval.csv
```

Kết quả:

- 21/21 câu pass
- Không còn forbidden

### Grading chính thức

```powershell
.\venv\Scripts\python.exe -X utf8 grading_run.py --out artifacts\eval\grading_run.jsonl
```

Kết quả:

- 10/10 câu pass

### Instructor quick check

```powershell
.\venv\Scripts\python.exe -X utf8 instructor_quick_check.py --grading artifacts\eval\grading_run.jsonl
.\venv\Scripts\python.exe -X utf8 instructor_quick_check.py --manifest artifacts\manifests\manifest_cohere-final-clean.json
```

Kết quả:

```text
GRADE_CHECK[gq_d10_01] OK
...
GRADE_CHECK[gq_d10_10] OK
OK manifest run_id=cohere-final-clean raw=247 clean=35 quar=212
```

---

## 6. Artifact đã tạo

### Manifest

- `artifacts/manifests/manifest_cohere-final-clean.json`
- `artifacts/manifests/manifest_inject-bad.json`

### Cleaned / quarantine

- `artifacts/cleaned/cleaned_cohere-final-clean.csv`
- `artifacts/quarantine/quarantine_cohere-final-clean.csv`
- `artifacts/cleaned/cleaned_inject-bad.csv`
- `artifacts/quarantine/quarantine_inject-bad.csv`

### Eval / grading

- `artifacts/eval/after_fix_eval.csv`
- `artifacts/eval/after_inject_bad.csv`
- `artifacts/eval/grading_run.jsonl`
- `artifacts/eval/eval_cohere-after-cleaning.csv`

---

## 7. Before / after summary

### Inject-bad

Run:

```text
run_id=inject-bad
no_refund_fix=true
skipped_validate=true
```

Eval result:

```text
after_inject_bad.csv
contains_expected=no: q_refund_window
hits_forbidden=yes: q_refund_window
```

Ý nghĩa: khi tắt rule refund fix, stale chunk `"14 ngày làm việc"` lọt vào index và làm retrieval fail.

### After fix

Run:

```text
run_id=cohere-final-clean
no_refund_fix=false
skipped_validate=false
```

Eval result:

```text
after_fix_eval.csv
contains_expected=no: none
hits_forbidden=yes: none
top1_doc_expected=no: none
```

Ý nghĩa: pipeline sạch đã loại/fix stale context, retrieval không còn lấy chunk forbidden.

---

## 8. Kết quả grading chính thức

Tất cả 10 câu pass:

| ID | Top-1 doc | contains_expected | hits_forbidden | top1_doc_matches |
|----|-----------|-------------------|----------------|------------------|
| gq_d10_01 | policy_refund_v4 | true | false | true |
| gq_d10_02 | policy_refund_v4 | true | false | true |
| gq_d10_03 | policy_refund_v4 | true | false | true |
| gq_d10_04 | sla_p1_2026 | true | false | true |
| gq_d10_05 | sla_p1_2026 | true | false | true |
| gq_d10_06 | sla_p1_2026 | true | false | true |
| gq_d10_07 | it_helpdesk_faq | true | false | true |
| gq_d10_08 | it_helpdesk_faq | true | false | true |
| gq_d10_09 | hr_leave_policy | true | false | true |
| gq_d10_10 | access_control_sop | true | false | true |

---

## 9. Lưu ý kỹ thuật

### Console UTF-8

Trên Windows, một số lệnh bị lỗi khi in ký tự tiếng Việt hoặc ký tự `->`/mũi tên nếu stdout dùng `cp1252`.

Vì vậy các lệnh final nên chạy với:

```powershell
.\venv\Scripts\python.exe -X utf8 ...
```

### `.env` warning

Trong `.env` thật có biến bắt đầu bằng số như `9_ROUTER_API_KEY`, làm `python-dotenv` báo:

```text
python-dotenv could not parse statement starting at line 17
```

Cảnh báo này không làm fail pipeline. Nếu muốn sạch log, đổi tên biến sang dạng hợp lệ, ví dụ:

```env
NINE_ROUTER_API_KEY=...
NINE_ROUTER_BASE_URL=...
NINE_ROUTER_MODEL=...
```

---

## 10. Kết luận

Pipeline Day 10 đã được hoàn thiện theo luồng README:

- Sprint 1: phát hiện pipeline halt và thiếu `access_control_sop`
- Sprint 2: sửa cleaning/expectations và embed bằng Cohere
- Sprint 3: tạo inject-bad và chứng minh retrieval xấu hơn
- Sprint 4: chạy freshness, grading, quick check và tạo artifact final

Run nên dùng để viết báo cáo/nộp:

```text
run_id=cohere-final-clean
manifest=artifacts/manifests/manifest_cohere-final-clean.json
grading=artifacts/eval/grading_run.jsonl
after_fix_eval=artifacts/eval/after_fix_eval.csv
before_eval=artifacts/eval/after_inject_bad.csv
```
