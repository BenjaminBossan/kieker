import pytest

from kieker.project_map import create_project_map


class TestProjectMap:
    @pytest.fixture
    def project_map(self, conn):
        project_map = create_project_map(conn)
        return project_map

    def test_modules(self, project_map):
        module_names = [module.name for module in project_map]
        expected = [
            "hf",
            "_version",
            "__init__",
            "net",
            "cli",
            "history",
            "toy",
            "callbacks.__init__",
            "callbacks.base",
            "callbacks.training",
            "callbacks.regularization",
            "callbacks.lr_scheduler",
            "callbacks.logging",
            "callbacks.scoring",
            "llm.__init__",
            "llm.prompts",
            "llm.classifier",
            "setter",
            "probabilistic",
            "_doctor",
            "exceptions",
            "regressor",
            "helper",
            "classifier",
            "dataset",
            "scoring",
            "utils",
        ]
        assert sorted(module_names) == sorted(expected)

    def test_classes(self, project_map):
        module_classifier = next(
            module for module in project_map if module.name == "classifier"
        )
        clf = module_classifier.classes[0]
        assert clf.name == "NeuralNetClassifier"
        assert clf.line == 57

        bclf = module_classifier.classes[1]
        assert bclf.name == "NeuralNetBinaryClassifier"
        assert bclf.line == 266

    def test_methods(self, project_map):
        module_classifier = next(
            module for module in project_map if module.name == "regressor"
        )
        clf = module_classifier.classes[0]
        methods = clf.methods

        assert methods[0].name == "__init__"
        assert methods[0].line == 42
        assert methods[1].name == "check_data"
        assert methods[1].line == 57
        assert methods[2].name == "fit"
        assert methods[2].line == 73

    def test_functions(self, project_map):
        module_classifier = next(
            module for module in project_map if module.name == "classifier"
        )
        functions = module_classifier.functions
        assert len(functions) == 2

        assert functions[0].name == "get_neural_net_clf_doc"
        assert functions[0].line == 44
        assert functions[1].name == "get_neural_net_binary_clf_doc"
        assert functions[1].line == 255

    def test_indentation(self, project_map):
        # classes and functions typically start at col 0, methods at col 1, but
        # there can be nested functions with more indentation
        module_utils = next(module for module in project_map if module.name == "utils")

        cls = next(c for c in module_utils.classes if c.name == "FirstStepAccumulator")
        assert cls.col == 0

        method = cls.methods[0]
        assert method.col == 4

        function = module_utils.functions[0]
        assert function.col == 0

        # this is a local function defined in a method in an if condition (i.e.
        # 3x4 spaces indentation)
        local_function = next(
            f for f in module_utils.functions if f.name == "_load_from_bytes"
        )
        assert local_function.col == 12
