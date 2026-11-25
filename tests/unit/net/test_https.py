from optimus.net.https import https_hostname


def test_https_hostname_returns_normalized_host_for_https_urls():
    assert https_hostname("https://docs.example.com/a") == "docs.example.com"
    assert https_hostname("https://example.com:443/a") == "example.com"


def test_https_hostname_rejects_non_https_urls():
    assert https_hostname("http://docs.example.com/a") is None
    assert https_hostname("not-a-url") is None


# #603: each of these makes urllib's parser raise ValueError (an unclosed or invalid bracketed host).
MALFORMED_URLS = ["https://[", "https://[::1", "https://[not-an-address]/x", "https://example.com:65536/a"]


def test_https_hostname_has_no_host_for_a_url_the_parser_rejects():
    for url in MALFORMED_URLS:
        assert https_hostname(url) is None
