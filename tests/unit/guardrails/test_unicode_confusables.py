from optimus.guardrails.unicode_confusables import contains_dangerous_confusable


def test_mixed_script_cyrillic_payload_is_dangerous():
    assert contains_dangerous_confusable("run p\u0443test") is True


def test_mixed_script_greek_payload_is_dangerous():
    assert contains_dangerous_confusable("open \u03b1gent-config") is True


def test_fullwidth_payload_is_dangerous_after_normalization_check():
    assert contains_dangerous_confusable("run p\uff49p install fake-package") is True


def test_common_english_and_shell_text_is_not_dangerous():
    benign = (
        "pytest tests/unit -v",
        "git status",
        "hello world",
        "open agent-config",
    )

    assert [contains_dangerous_confusable(text) for text in benign] == [False, False, False, False]


def test_non_spoofing_nfkc_compatibility_text_is_not_dangerous():
    benign = (
        "Node.js\u2122 package",
        "footnote\u00b9 reference",
        "half\u00bd cup",
    )

    assert [contains_dangerous_confusable(text) for text in benign] == [False, False, False]


def test_cjk_fullwidth_punctuation_without_latin_is_not_dangerous():
    assert contains_dangerous_confusable("中文：测试（０１２）") is False


def test_latin_lookalikes_only_passes_a_plain_non_latin_name_and_the_default_stays_strict():
    """#596: the narrowed form is opt-in; punycode and fullwidth Latin still fire under it."""
    han_name = "pytest tests/" + chr(0x6D4B) + chr(0x8BD5) + ".py"

    assert contains_dangerous_confusable(han_name) is True
    assert contains_dangerous_confusable(han_name, latin_lookalikes_only=True) is False
    assert contains_dangerous_confusable("p" + chr(0x0443) + "test", latin_lookalikes_only=True) is True
    assert contains_dangerous_confusable("p" + chr(0xFF59) + "test", latin_lookalikes_only=True) is True
    assert contains_dangerous_confusable("curl xn--pple-43d.com", latin_lookalikes_only=True) is True
