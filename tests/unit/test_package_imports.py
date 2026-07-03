def test_optimus_package_exports_version():
    import optimus

    assert optimus.__version__ == "0.1.0"


def test_pydantic_is_available_for_gateway_settings():
    import pydantic

    assert pydantic.VERSION.split(".")[0] == "2"
