"""The shared package is the single source for the wire contract.

These were three copy-pasted pairs before: the schemas, the HTML text extractor,
and the Gemini retry helper. Drift between them broke things only at runtime — a
rejected delivery, or a content hash that disagreed with itself across runs.
"""

from backend import htmlutil
from backend import schemas as backend_schemas
from research_crawler import fetch
from research_crawler import schemas as crawler_schemas
from shared import gemini, htmltext
from shared import schemas as shared_schemas


class TestOneDefinition:
    def test_both_packages_expose_the_same_finding_class(self):
        assert backend_schemas.Finding is crawler_schemas.Finding
        assert backend_schemas.Finding is shared_schemas.Finding

    def test_both_packages_expose_the_same_payload_class(self):
        assert backend_schemas.IngestPayload is crawler_schemas.IngestPayload
        assert backend_schemas.IngestPayload is shared_schemas.IngestPayload

    def test_the_enums_are_identical_objects(self):
        for name in ("Category", "Line", "Tone"):
            assert getattr(backend_schemas, name) is getattr(crawler_schemas, name), name

    def test_both_packages_use_the_same_text_extractor(self):
        assert htmlutil.extract_clean_text is htmltext.extract_clean_text
        assert fetch.extract_clean_text is htmltext.extract_clean_text


class TestStillSeparateWhereItShouldBe:
    """Sharing the contract must not merge things only one side has."""

    def test_classification_is_backend_only(self):
        assert hasattr(backend_schemas, "Classification")
        assert not hasattr(crawler_schemas, "Classification")

    def test_findings_batch_is_crawler_only(self):
        assert hasattr(crawler_schemas, "FindingsBatch")
        assert not hasattr(backend_schemas, "FindingsBatch")

    def test_inject_base_href_is_backend_only(self):
        assert hasattr(htmlutil, "inject_base_href")
        assert not hasattr(htmltext, "inject_base_href")


class TestSharedIsSelfContained:
    """shared/ must not import from either deployable, or the dependency runs
    backwards and neither package can be built without the other."""

    def test_no_imports_from_backend_or_crawler(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parent.parent / "shared"
        for path in root.glob("*.py"):
            text = path.read_text()
            assert "from backend" not in text, path.name
            assert "from research_crawler" not in text, path.name
            assert "import backend" not in text, path.name

    def test_retry_limits_are_parameters_not_config_reads(self):
        # shared/ stays independent of either package's configuration, so the
        # two can keep different budgets.
        import inspect
        params = inspect.signature(gemini.generate).parameters
        assert "max_attempts" in params
        assert "backoff_seconds" in params
