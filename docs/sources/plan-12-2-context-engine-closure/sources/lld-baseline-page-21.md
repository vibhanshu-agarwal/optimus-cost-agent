# 6.1 OpenAI-compatible upstream pattern

```python
class UrllibOpenAICompatibleClient:
    """Gateway-owned aggregator transport.

    The agent never receives the upstream URL or credential. The transport
    has no direct-provider selection branch.
    """

    def __init__(self, *, api_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    def create_message(
        self, *, model: str, input_text: str
    ) -> ProviderMessageResult:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": input_text}],
        }
        body = self._post_json("/chat/completions", payload)
        return parse_openai_compatible_message_and_usage(body)
```

`parse_openai_compatible_message_and_usage` must validate output, provider request identity,
billing units, token/cache detail, resolved model/version when present, and provider-reported USD
cost. The Gateway returns the requested agent-facing shape plus the same validated GatewayUsage
contract.

```text
Agent /v1/responses "input" --------\
                                      > completion service
Agent /v1/chat/completions "messages"/       |
                                             v
                         OpenAI-compatible aggregator transport
```

The upstream transport may use Chat Completions while the Gateway preserves both agent-facing
contracts. Those shapes must never be mixed.