import inspect

import optimus_gateway.pricing as pricing


def test_pricing_module_has_no_settled_cost_calculation():
    source = inspect.getsource(pricing)

    assert "MODEL_RATES" not in source
    assert "compute_cost_usd" not in source
    assert "lookup_model_rate" not in source
    assert "billing_units" not in source
