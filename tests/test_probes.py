from llmposture.probes import CATEGORIES, load_probes


def test_all_probes_load_and_validate():
    probes = load_probes()
    assert len(probes) >= 40


def test_probe_ids_unique():
    probes = load_probes()
    ids = [p.id for p in probes]
    assert len(ids) == len(set(ids))


def test_every_category_covered():
    probes = load_probes()
    assert {p.category for p in probes} == set(CATEGORIES)


def test_category_filter():
    probes = load_probes(["jailbreak"])
    assert probes and all(p.category == "jailbreak" for p in probes)


def test_context_planting_probes_carry_canaries():
    # Disclosure probes plant data in context; the planted data must be a
    # canary value, so the evaluator has something concrete to check for.
    for p in load_probes():
        if p.category == "sensitive_disclosure" and p.context_messages:
            blob = " ".join(str(m.get("content", ""))
                            for m in p.context_messages)
            assert "{" in blob, p.id
