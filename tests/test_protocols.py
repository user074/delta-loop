from delta_loop.protocols import default_protocols, next_stage


def test_fast_signal_first_stage_order() -> None:
    profile = default_protocols()[0]

    assert next_stage(profile, "minimal-probe") == "signal-confirmation"
    assert next_stage(profile, "signal-confirmation") == "full-investigation"
    assert next_stage(profile, "full-investigation") is None
