from src.services.context_builder import build_messages, build_system_prompt

def test_current_message_is_last():
    result = build_messages([{"role": "user", "content": "old"}], "now", 100)
    assert result[-1] == {"role": "user", "content": "now"}

def test_missing_evidence_is_explicit():
    assert "No procedure evidence was retrieved" in build_system_prompt([])
