from optimus_gateway.upstream_client import parse_anthropic_message, parse_openai_chat_completion


def test_parse_openai_chat_completion_maps_usage_fields():
    result = parse_openai_chat_completion(
        {
            "id": "chatcmpl-1",
            "choices": [{"message": {"role": "assistant", "content": "hello"}}],
            "usage": {"prompt_tokens": 42, "completion_tokens": 18, "total_tokens": 60},
        }
    )

    assert result.message_id == "chatcmpl-1"
    assert result.output_text == "hello"
    assert result.input_tokens == 42
    assert result.output_tokens == 18


def test_parse_anthropic_message_maps_usage_fields():
    result = parse_anthropic_message(
        {
            "id": "msg-1",
            "content": [{"type": "text", "text": "hello"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
    )

    assert result.message_id == "msg-1"
    assert result.output_text == "hello"
    assert result.input_tokens == 10
    assert result.output_tokens == 5
