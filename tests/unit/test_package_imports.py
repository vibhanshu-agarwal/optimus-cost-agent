def test_optimus_package_exports_version():
    import optimus

    assert optimus.__version__ == "0.1.0"
