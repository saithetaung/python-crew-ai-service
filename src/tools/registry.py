TOOL_NAMES = {
    "get_expired_contracts",
    "get_expiring_certificates",
    "list_vessels",
}

BEDROCK_TOOL_CONFIG = [
    {
        "toolSpec": {
            "name": "get_expired_contracts",
            "description": (
                "Retrieve contracts from the existing dashboard API "
                "for a specified number of days. Use this tool when "
                "the user asks which contracts will expire within a "
                "time window."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "minimum": 1,
                            "description": (
                                "Number of days in the requested window."
                            ),
                        }
                    },
                    "required": ["days"],
                    "additionalProperties": False,
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_expiring_certificates",
            "description": (
                "Retrieve certificates from the existing dashboard API "
                "for a specified number of days."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "days": {
                            "type": "integer",
                            "minimum": 1,
                            "description": (
                                "Number of days in the requested window."
                            ),
                        }
                    },
                    "required": ["days"],
                    "additionalProperties": False,
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "list_vessels",
            "description": (
                "Retrieve registered vessels and their information "
                "from the crew management system."
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
]