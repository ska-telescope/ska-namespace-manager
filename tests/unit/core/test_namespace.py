from ska_ser_namespace_manager.core.namespace import (
    Namespace,
    NamespaceMatcher,
    NamespaceMatchingOptions,
    match_namespace,
)


def test_namespace_defaults():
    ns = Namespace(name="xpto")
    assert ns.labels == {}
    assert ns.annotations == {}


def test_match_namespace():
    configs = [
        NamespaceMatcher(
            names=["ci-.*-.*", "staging-.*"],
        ),
        NamespaceMatcher(
            any=[
                NamespaceMatchingOptions(
                    labels={"label": "0"},
                ),
                NamespaceMatchingOptions(
                    annotations={"annotation": "0"},
                ),
            ],
        ),
        NamespaceMatcher(
            all=[
                NamespaceMatchingOptions(
                    labels={"label": "1"},
                ),
                NamespaceMatchingOptions(
                    annotations={"annotation": "1"},
                ),
            ],
        ),
        NamespaceMatcher(
            any=[
                NamespaceMatchingOptions(
                    labels={"otherLabel": "1"},
                )
            ],
            all=[
                NamespaceMatchingOptions(
                    labels={"label": "0"},
                    annotations={"annotation": "0"},
                )
            ],
        ),
        NamespaceMatcher(
            any=[
                NamespaceMatchingOptions(
                    labels={"label": "2", "otherLabel": "2"},
                ),
                NamespaceMatchingOptions(
                    labels={"otherLabel": "3"},
                ),
            ],
        ),
        NamespaceMatcher(
            all=[
                NamespaceMatchingOptions(
                    labels={"label": "2", "otherLabel": "2"},
                    annotations={"annotation": "1"},
                ),
                NamespaceMatchingOptions(
                    annotations={"otherAnnotation": "2"},
                ),
            ],
        ),
    ]

    scenarios = [
        # Test names
        {"namespace": Namespace(name="ci-nomatch"), "matching": None},
        {
            "namespace": Namespace(name="ci-this-00matches"),
            "matching": configs[0],
        },
        {
            "namespace": Namespace(name="staging-something"),
            "matching": configs[0],
        },
        # Test any
        {
            "namespace": Namespace(name="namespace", labels={"label": "0"}),
            "matching": configs[1],
        },
        {
            "namespace": Namespace(
                name="namespace", annotations={"annotation": "0"}
            ),
            "matching": configs[1],
        },
        {
            "namespace": Namespace(
                name="namespace",
                labels={"label": "0"},
                annotations={"annotation": "-1"},
            ),
            "matching": configs[1],
        },
        {
            "namespace": Namespace(
                name="namespace",
                labels={"label": "-1"},
                annotations={"annotation": "0"},
            ),
            "matching": configs[1],
        },
        # Test all
        {
            "namespace": Namespace(name="namespace", labels={"label": "1"}),
            "matching": None,
        },
        {
            "namespace": Namespace(
                name="namespace", annotations={"annotation": "1"}
            ),
            "matching": None,
        },
        {
            "namespace": Namespace(
                name="namespace",
                labels={"label": "1"},
                annotations={"annotation": "1"},
            ),
            "matching": configs[2],
        },
        # Test precedence
        {
            "namespace": Namespace(
                name="namespace",
                labels={"label": "0", "otherLabel": "1"},
                annotations={"annotation": "0"},
            ),
            "matching": configs[3],
        },
        {
            "namespace": Namespace(
                name="namespace",
                labels={"label": "0", "otherLabel": "-1"},
                annotations={"annotation": "0"},
            ),
            "matching": configs[3],
        },
        {
            "namespace": Namespace(
                name="namespace",
                labels={"label": "1", "otherLabel": "1"},
                annotations={"annotation": "1"},
            ),
            "matching": configs[2],
        },
        # Test compound matching
        {
            "namespace": Namespace(name="namespace", labels={"label": "2"}),
            "matching": None,
        },
        {
            "namespace": Namespace(
                name="namespace", labels={"label": "2", "otherLabel": "2"}
            ),
            "matching": configs[4],
        },
        {
            "namespace": Namespace(
                name="namespace", labels={"label": "2", "otherLabel": "3"}
            ),
            "matching": configs[4],
        },
        {
            "namespace": Namespace(
                name="namespace",
                labels={"label": "2", "otherLabel": "2"},
                annotations={"annotation": "1"},
            ),
            "matching": configs[4],
        },
        {
            "namespace": Namespace(
                name="namespace",
                labels={"label": "2", "otherLabel": "2"},
                annotations={"annotation": "1", "otherAnnotation": "2"},
            ),
            "matching": configs[5],
        },
    ]

    assert not match_namespace([], Namespace(name="xpto"))
    assert not match_namespace(configs, None)
    for scenario in scenarios:
        assert scenario.get("matching") == match_namespace(
            configs, scenario.get("namespace")
        )
