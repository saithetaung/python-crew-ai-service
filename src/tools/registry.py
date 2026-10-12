BEDROCK_TOOL_CONFIG = [
    {"toolSpec": {
        "name": "get_current_vessel",
        "description": "Get the current vessel for the authenticated user within their authorized scope.",
        "inputSchema": {"json": {"type": "object", "properties": {}, "additionalProperties": False}},
    }},
    {"toolSpec": {
        "name": "get_expiring_certifications",
        "description": "Find certifications expiring within a number of days in the caller's authorized scope.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {"daysAhead": {"type": "integer", "minimum": 1, "maximum": 365}},
            "required": ["daysAhead"], "additionalProperties": False,
        }},
    }},
    {"toolSpec": {
        "name": "get_vessel_crew_certificate_status",
        "description": "Get crew certificate status for a vessel in the caller's authorized scope.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {"vesselId": {"type": "string", "minLength": 1, "maxLength": 128}},
            "required": ["vesselId"], "additionalProperties": False,
        }},
    }},
]
TOOL_NAMES = {tool["toolSpec"]["name"] for tool in BEDROCK_TOOL_CONFIG}
