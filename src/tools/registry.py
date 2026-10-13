
from typing import Any


BEDROCK_TOOL_CONFIG = [
    {
        "toolSpec": {
            "name": "get_current_vessel",
            "description": (
                "Get the current vessel assigned to the authenticated user. "
                "Use this tool when asked about the user's current vessel."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_expiring_certifications",
            "description": (
                "Find crew certifications expiring within a specified "
                "number of days. Use daysAhead from the user's question."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "daysAhead": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 365,
                        }
                    },
                    "required": ["daysAhead"],
                    "additionalProperties": False,
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_vessel_crew_certificate_status",
            "description": (
                "Get certificate statuses of crew assigned to a vessel. "
                "Use the vesselId from the user's question."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "vesselId": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 128,
                        }
                    },
                    "required": ["vesselId"],
                    "additionalProperties": False,
                }
            },
        }
    },
]

TOOL_NAMES = {
    item["toolSpec"]["name"] for item in BEDROCK_TOOL_CONFIG
}


# Fictional development data. Not real crew-management records.
MOCK_CURRENT_VESSEL = {
    "vesselId": "V-100",
    "vesselName": "MV Ocean Star",
    "assignmentStatus": "ACTIVE",
}

MOCK_EXPIRING_CERTIFICATES = [
    {
        "crewId": "C-1001",
        "crewName": "Test Crew One",
        "certificate": "Medical Certificate",
        "expiryDate": "2026-10-25",
        "status": "EXPIRING_SOON",
    },
    {
        "crewId": "C-1002",
        "crewName": "Test Crew Two",
        "certificate": "Basic Safety Training",
        "expiryDate": "2026-11-05",
        "status": "EXPIRING_SOON",
    },
]

MOCK_VESSEL_CERTIFICATES = {
    "V-100": [
        {
            "crewId": "C-1001",
            "certificate": "Medical Certificate",
            "status": "VALID",
            "expiryDate": "2027-03-20",
        },
        {
            "crewId": "C-1002",
            "certificate": "Basic Safety Training",
            "status": "EXPIRED",
            "expiryDate": "2026-09-15",
        },
    ]
}


def execute_mock_tool(
    name: str,
    arguments: dict[str, Any],
    user_id: str,
) -> dict[str, Any]:
    print(
        f"[TOOL HANDLER] name={name}, "
        f"user_id={user_id}, arguments={arguments}",
        flush=True,
    )

    if name == "get_current_vessel":
        if arguments:
            raise ValueError("This tool accepts no arguments.")

        return {
            "mock": True,
            "requestedBy": user_id,
            "vessel": MOCK_CURRENT_VESSEL,
        }

    if name == "get_expiring_certifications":
        days_ahead = arguments.get("daysAhead")

        if (
            not isinstance(days_ahead, int)
            or isinstance(days_ahead, bool)
            or not 1 <= days_ahead <= 365
        ):
            raise ValueError("daysAhead must be between 1 and 365.")

        # Demo data is fixed; it is not filtered by the current date.
        return {
            "mock": True,
            "daysAhead": days_ahead,
            "certifications": MOCK_EXPIRING_CERTIFICATES,
            "note": "Fixed mock records; not dynamically date-filtered.",
        }

    if name == "get_vessel_crew_certificate_status":
        vessel_id = arguments.get("vesselId")

        if (
            not isinstance(vessel_id, str)
            or not vessel_id.strip()
            or len(vessel_id) > 128
        ):
            raise ValueError("A valid vesselId is required.")

        vessel_id = vessel_id.strip()

        return {
            "mock": True,
            "vesselId": vessel_id,
            "certificates": MOCK_VESSEL_CERTIFICATES.get(vessel_id, []),
        }

    raise ValueError(f"Unsupported tool: {name}")
