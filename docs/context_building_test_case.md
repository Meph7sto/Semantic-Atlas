# Context Building Test Case (Requirement Analysis)

Purpose: provide a ready-to-run context building test with a transcript parsed from audio.

## Transcript (parsed text)

Use the following transcript format for ingestion:

```
[00:00:03-00:00:12] Alex: We need the mobile app to upload audio and images.
[00:00:12-00:00:22] Priya: Upload must support resume or users on bad networks will fail.
[00:00:22-00:00:31] Alex: After upload, show a processing state like "parsing" then "stored".
[00:00:31-00:00:42] Sam: Privacy is critical; audio and images must be encrypted and access controlled.
[00:00:42-00:00:54] Priya: Offline mode? We want basic requirement extraction without network.
[00:00:54-00:01:05] Sam: Encryption and auth are server side; full offline may be limited.
[00:01:05-00:01:16] Alex: Then do local span splitting and cache, sync to server when online.
[00:01:16-00:01:27] Priya: Sync must be idempotent; reupload of the same audio cannot create duplicate spans.
[00:01:27-00:01:39] Alex: Each requirement must trace back to the original quote and speaker.
[00:01:39-00:01:50] Sam: Permissions: project members see full text, external reviewers only redacted summaries.
[00:01:50-00:02:02] Priya: Also run conflict detection, like "must be offline" vs "must use cloud inference".
[00:02:02-00:02:12] Alex: Open question: what is the minimal offline extraction scope.
```

## Steps (PowerShell)

1) Ingest the transcript into spans

```powershell
$transcript = @'
[00:00:03-00:00:12] Alex: We need the mobile app to upload audio and images.
[00:00:12-00:00:22] Priya: Upload must support resume or users on bad networks will fail.
[00:00:22-00:00:31] Alex: After upload, show a processing state like "parsing" then "stored".
[00:00:31-00:00:42] Sam: Privacy is critical; audio and images must be encrypted and access controlled.
[00:00:42-00:00:54] Priya: Offline mode? We want basic requirement extraction without network.
[00:00:54-00:01:05] Sam: Encryption and auth are server side; full offline may be limited.
[00:01:05-00:01:16] Alex: Then do local span splitting and cache, sync to server when online.
[00:01:16-00:01:27] Priya: Sync must be idempotent; reupload of the same audio cannot create duplicate spans.
[00:01:27-00:01:39] Alex: Each requirement must trace back to the original quote and speaker.
[00:01:39-00:01:50] Sam: Permissions: project members see full text, external reviewers only redacted summaries.
[00:01:50-00:02:02] Priya: Also run conflict detection, like "must be offline" vs "must use cloud inference".
[00:02:02-00:02:12] Alex: Open question: what is the minimal offline extraction scope.
'@

$payload = @{
  transcript_text = $transcript
  session_id = "ctx-test-001"
  options = @{
    estimate_timestamps_if_missing = $false
  }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:5001/api/analysis/ingest_transcript" `
  -ContentType "application/json" `
  -Body $payload
```

2) Build context (use mock LLM so it runs without model access)

```powershell
$payload = @{
  session_id = "ctx-test-001"
  options = @{
    mock_llm = $true
    window_size = 8
    step_size = 7
    tau = 0.6
    top_k = 3
  }
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:5001/api/analysis/build_context" `
  -ContentType "application/json" `
  -Body $payload
```

3) Inspect results

```powershell
Invoke-RestMethod -Uri "http://localhost:5001/api/analysis/bundles/<context_run_id>"
Invoke-RestMethod -Uri "http://localhost:5001/api/analysis/span_links/<context_run_id>"
```

## Expected checks

- Ingest returns a non-zero `span_total` and a stable `session_id`.
- Build context returns a `context_run_id`, and `bundle_total` should be greater than 0.
- Bundles should contain grouped spans around upload, offline mode, privacy, and conflict detection.
- Span links should include relations like continuation, elaboration, or conflict.
