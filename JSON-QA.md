## Testing MarineOn Business Tools

### 1. Prerequisites

Before running the tests, make sure:

- The FastAPI service is running.
- Redis is connected.
- AWS credentials and Amazon Bedrock access are configured.
- The business-tool mock handlers are enabled.
- You have configured `INTERNAL_API_TOKEN` in your environment.

Start the service:

```powershell
.\venv\Scripts\Activate.ps1
uvicorn src.app:app --reload --log-level info
```

### 2. API Endpoint

**Method:** `POST`

**URL:**

```text
http://127.0.0.1:8000/internal/v1/chat
```

**Headers:**

```http
Content-Type: application/json
X-Internal-Service-Token: YOUR_INTERNAL_API_TOKEN
```

Replace `YOUR_INTERNAL_API_TOKEN` with the token configured in your environment.

---

### 3. Test Case 1 — Get Current Vessel

**Purpose:** Verify that MarineOn identifies a question about the user's current vessel and selects `get_current_vessel`.

**Request JSON:**

```json
{
  "requestId": "tool-test-001",
  "conversationId": "tool-test-001",
  "message": "What is my current vessel?",
  "actor": {
    "userId": "user-123",
    "tenantId": "tenant-01"
  }
}
```

**Expected tool:**

```text
get_current_vessel
```

**Example response:**

```json
{
  "requestId": "tool-test-001",
  "conversationId": "tool-test-001",
  "answer": "Your current vessel is MV Ocean Star (V-100), which is currently active.",
  "citations": [],
  "latencySeconds": 1.234
}
```

**Expected mock data:**

- Vessel ID: `V-100`
- Vessel name: `MV Ocean Star`
- Status: `ACTIVE`

The response text and latency may vary depending on the model and execution time.

---

### 4. Test Case 2 — Find Expiring Certifications

**Purpose:** Verify that MarineOn selects `get_expiring_certifications` when the user asks about upcoming certification expirations.

**Request JSON:**

```json
{
  "requestId": "tool-test-002",
  "conversationId": "tool-test-002",
  "message": "Which certifications are expiring in the next 30 days?",
  "actor": {
    "userId": "user-123",
    "tenantId": "tenant-01"
  }
}
```

**Expected tool:**

```text
get_expiring_certifications
```

**Expected tool arguments:**

```json
{
  "daysAhead": 30
}
```

**Example response:**

```json
{
  "requestId": "tool-test-002",
  "conversationId": "tool-test-002",
  "answer": "The mock certification data includes the following upcoming expirations:\n\n1. Medical Certificate (C-1001): 2026-10-25\n2. Basic Safety Training (C-1002): 2026-11-05",
  "citations": [],
  "latencySeconds": 1.456
}
```

**Important:** The current mock handler contains fixed sample certification records. Confirm that it filters the records using `daysAhead` before treating this test as a date-accurate result. The example above illustrates the mock data, not a guarantee that both records fall within the requested 30-day window.

---

### 5. Test Case 3 — Check Crew Certificate Status

**Purpose:** Verify that MarineOn selects `get_vessel_crew_certificate_status` for a certificate-status question concerning a specific vessel.

**Request JSON:**

```json
{
  "requestId": "tool-test-003",
  "conversationId": "tool-test-003",
  "message": "Show the certificate status of all crew on vessel V-100.",
  "actor": {
    "userId": "user-123",
    "tenantId": "tenant-01"
  }
}
```

**Expected tool:**

```text
get_vessel_crew_certificate_status
```

**Expected tool arguments:**

```json
{
  "vesselId": "V-100"
}
```

**Example response:**

```json
{
  "requestId": "tool-test-003",
  "conversationId": "tool-test-003",
  "answer": "Certificate status for vessel V-100:\n\n1. Medical Certificate (C-1001): Valid until 2027-03-20.\n2. Basic Safety Training (C-1002): Expired on 2026-09-15.",
  "citations": [],
  "latencySeconds": 1.678
}
```

**Expected mock data:**

- Vessel ID: `V-100`
- Medical Certificate: valid until `2027-03-20`
- Basic Safety Training: expired on `2026-09-15`

These are mock records, not live crew-management database results.

---

### 6. Verify the Terminal Logs

When you submit a request, check the terminal running Uvicorn. The current implementation should print logs similar to these:

```text
[CHAT] Received request ...
[CHAT] Selected tool: get_current_vessel
[BEDROCK TOOL] Starting request ...
[BEDROCK TOOL] stopReason: tool_use
[BEDROCK TOOL] Tool requested: get_current_vessel
[TOOL HANDLER] Executing get_current_vessel ...
[BEDROCK TOOL] Mock handler succeeded ...
```

The exact messages and order may vary. For each test, confirm that:

1. The correct tool is selected.
2. Bedrock requests the expected tool and arguments.
3. The mock handler executes successfully.
4. The API returns HTTP `200 OK` with the expected request and conversation IDs.

### 7. Test Summary

| Test | User question | Expected tool | Expected result |
|---|---|---|---|
| 1 | What is my current vessel? | `get_current_vessel` | `MV Ocean Star`, `V-100` |
| 2 | Which certifications are expiring in the next 30 days? | `get_expiring_certifications` | Certification records and expiry dates |
| 3 | Show the certificate status of all crew on vessel V-100. | `get_vessel_crew_certificate_status` | Valid and expired certificate records |

### 8. Troubleshooting

| Problem | What to check |
|---|---|
| HTTP `401 Unauthorized` | Verify `X-Internal-Service-Token`. |
| HTTP `503 Service Unavailable` | Check Bedrock configuration, AWS credentials, model access, and server logs. |
| Wrong tool selected | Review `_select_business_tool()` in `src/services/chat_service.py`. |
| No tool logs | Confirm the edited files are saved and Uvicorn is running the correct project and virtual environment. |
| Incorrect arguments | Check the tool schema and the model's tool-use response. |
| Unexpected certification dates | Review date filtering in `src/tools/registry.py`. |

### 9. Important Notes

- These tests use mock business data; they do not verify live vessel or crew records.
- Example answer wording and latency are illustrative. The model may produce different wording.
- An HTTP `200 OK` alone does not prove that the correct tool was called. Verify the terminal logs and tool arguments.
- Once the mock tests pass, replace the mock handlers with calls to the authorized Java Spring Boot APIs. Keep authentication, authorization, and database access in the Java backend rather than querying MySQL directly from the Python AI service.