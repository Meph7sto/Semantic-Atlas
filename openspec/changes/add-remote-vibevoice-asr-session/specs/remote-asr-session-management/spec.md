## ADDED Requirements

### Requirement: Media Transcription Job Creation
The system SHALL accept authenticated uploads of supported media formats (`wav`, `mp3`, `m4a`, `mp4`) and create a transcription session that can be processed asynchronously by the remote VibeVoice ASR service.

#### Scenario: Create transcription session from uploaded file
- **WHEN** an authenticated user uploads a supported media file and submits a transcription request
- **THEN** the system creates a new transcription session with status `queued`, persists file metadata, and returns a unique `session_id`

#### Scenario: Reject unsupported file format
- **WHEN** a user uploads a file with an unsupported media extension or MIME type
- **THEN** the system rejects the request with a validation error and does not create a transcription session

### Requirement: Remote ASR Orchestration and Status Tracking
The system SHALL orchestrate remote inference with `microsoft/VibeVoice-ASR-HF` through configured remote endpoints and maintain a deterministic session status lifecycle.

#### Scenario: Session progresses through lifecycle
- **WHEN** the backend dispatches a queued session to remote inference and remote execution starts
- **THEN** the session status transitions from `queued` to `running` and stores execution timestamps

#### Scenario: Session marked failed on remote error
- **WHEN** remote inference returns an error response or exceeds configured timeout
- **THEN** the session status transitions to `failed` or `timeout` and stores structured error details

#### Scenario: Idempotent retry for failed sessions
- **WHEN** a client retries a session in `failed` or `timeout` state
- **THEN** the system creates a new processing attempt without corrupting prior session history

### Requirement: Transcription Result Persistence and Retrieval
The system SHALL persist transcription outputs returned from remote inference and expose query APIs for session list and session detail views.

#### Scenario: Persist successful transcription result
- **WHEN** remote inference returns a successful transcription result
- **THEN** the system stores the full text, optional timestamped segments, metadata, and updates session status to `succeeded`

#### Scenario: Retrieve session list
- **WHEN** an authenticated user requests transcription sessions
- **THEN** the system returns a paginated list containing session id, filename, created time, and current status

#### Scenario: Retrieve session detail
- **WHEN** an authenticated user requests a specific transcription session detail
- **THEN** the system returns stored transcription text, segment data when available, and error metadata when session is not successful

### Requirement: Local Export of Transcription Results
The system SHALL allow users to export persisted transcription results to local files in supported formats.

#### Scenario: Export successful session as TXT
- **WHEN** a user requests TXT export for a session with status `succeeded`
- **THEN** the system returns a downloadable `.txt` file containing the transcription text

#### Scenario: Export successful session as JSON
- **WHEN** a user requests JSON export for a session with status `succeeded`
- **THEN** the system returns a downloadable `.json` file containing text, segments, and metadata

#### Scenario: Prevent export for incomplete session
- **WHEN** a user requests export for a session not in `succeeded` state
- **THEN** the system rejects the export request with a domain-specific error indicating result is not ready

### Requirement: Secure Remote Invocation Configuration
The system SHALL load remote ASR endpoint and credentials from runtime configuration and validate connectivity before accepting processing requests.

#### Scenario: Startup with valid remote config
- **WHEN** the business backend starts with valid remote endpoint and auth configuration
- **THEN** the system marks remote ASR integration as available in health/status checks

#### Scenario: Startup with invalid remote config
- **WHEN** required remote ASR endpoint or credential configuration is missing or invalid
- **THEN** the system surfaces configuration errors and rejects new transcription job creation with actionable diagnostics
