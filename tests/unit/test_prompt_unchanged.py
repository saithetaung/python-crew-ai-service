from src.prompts.generation_prompt import GENERATION_PROMPT


def test_prompt_keeps_required_template_placeholders():
    assert "$search_results$" in GENERATION_PROMPT
    assert "$output_format_instructions$" in GENERATION_PROMPT
    assert "You are MarineOn, an AI assistant for a Ship Crew Management System." in GENERATION_PROMPT
