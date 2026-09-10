"""Configuration assembly.

One .env serves every component, and it is deliberately flat — no ${VAR}
references. python-dotenv would expand them, but `kubectl --from-env-file` and
`docker compose env_file:` copy values literally, so a composed value in the file
would reach the app as the characters "${POSTGRES_USER}". DATABASE_URL is
assembled here instead, which behaves the same under all three.
"""

import importlib
import pathlib
import re

import pytest

from backend import config as backend_config


def reload_backend(monkeypatch, **env):
    """Re-imports backend.config with exactly the given POSTGRES_*/DATABASE_URL."""
    for name in ("DATABASE_URL", "POSTGRES_PASSWORD", "POSTGRES_USER", "POSTGRES_HOST",
                 "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_SSLMODE"):
        monkeypatch.delenv(name, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    # The repo-root .env would otherwise reintroduce whatever a developer has
    # locally, making the outcome depend on the machine.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    return importlib.reload(backend_config)


class TestDatabaseUrl:
    def test_explicit_url_is_used_verbatim(self, monkeypatch):
        url = "postgresql://u:p@managed.example:6543/db?sslmode=require&pool=1"
        assert reload_backend(monkeypatch, DATABASE_URL=url).DATABASE_URL == url

    def test_url_is_composed_from_the_parts(self, monkeypatch):
        cfg = reload_backend(
            monkeypatch, POSTGRES_PASSWORD="s3cret", POSTGRES_USER="cw",
            POSTGRES_HOST="postgres.cw-dev.svc.cluster.local", POSTGRES_DB="competitor_watch",
        )
        assert cfg.DATABASE_URL == (
            "postgresql://cw:s3cret@postgres.cw-dev.svc.cluster.local:5432"
            "/competitor_watch?sslmode=disable"
        )

    def test_explicit_url_wins_over_the_parts(self, monkeypatch):
        cfg = reload_backend(monkeypatch, DATABASE_URL="postgresql://explicit/db",
                             POSTGRES_PASSWORD="ignored", POSTGRES_HOST="ignored")
        assert cfg.DATABASE_URL == "postgresql://explicit/db"

    def test_special_characters_in_the_password_are_encoded(self, monkeypatch):
        # An unencoded @ or / would be parsed as URL structure, silently
        # pointing the app at the wrong host or database.
        cfg = reload_backend(monkeypatch, POSTGRES_PASSWORD="p@ss/w:rd?x",
                             POSTGRES_HOST="db.local")
        assert "p%40ss%2Fw%3Ard%3Fx" in cfg.DATABASE_URL
        assert cfg.DATABASE_URL.count("@") == 1

    def test_missing_password_and_url_fails_with_a_usable_message(self, monkeypatch):
        with pytest.raises(RuntimeError, match=r"DATABASE_URL.*POSTGRES_PASSWORD"):
            reload_backend(monkeypatch)

    def test_defaults_match_the_documented_ones(self, monkeypatch):
        cfg = reload_backend(monkeypatch, POSTGRES_PASSWORD="x")
        assert "//cw:" in cfg.DATABASE_URL
        assert ":5432/" in cfg.DATABASE_URL
        assert cfg.DATABASE_URL.endswith("/competitor_watch?sslmode=disable")


class TestLogLevel:
    @pytest.mark.parametrize("given", ["debug", "DEBUG", "Debug"])
    def test_level_is_normalised_to_upper_case(self, given, monkeypatch):
        cfg = reload_backend(monkeypatch, POSTGRES_PASSWORD="x", LOG_LEVEL=given)
        assert cfg.LOG_LEVEL == "DEBUG"

    def test_the_result_is_a_level_logging_accepts(self, monkeypatch):
        # logging rejects a lowercase name outright (ValueError: Unknown level:
        # 'debug'), so an un-normalised value is a crash on boot rather than
        # merely a wrong log level.
        import logging
        cfg = reload_backend(monkeypatch, POSTGRES_PASSWORD="x", LOG_LEVEL="warning")
        logging.getLogger("probe").setLevel(cfg.LOG_LEVEL)

    def test_default_is_info(self, monkeypatch):
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        assert reload_backend(monkeypatch, POSTGRES_PASSWORD="x").LOG_LEVEL == "INFO"


class TestEnvExample:
    """The committed template is the only documentation of these variables, so
    it has to stay in step with what the code reads."""

    @staticmethod
    def example_keys() -> set[str]:
        text = (pathlib.Path(__file__).resolve().parent.parent / ".env.example").read_text()
        return {
            match.group(1)
            for line in text.splitlines()
            if (match := re.match(r"^([A-Z][A-Z0-9_]*)=", line.strip()))
        }

    @staticmethod
    def code_keys() -> set[str]:
        root = pathlib.Path(__file__).resolve().parent.parent
        found: set[str] = set()
        for package in ("backend", "research_crawler"):
            for path in (root / package).rglob("*.py"):
                text = path.read_text()
                # Both access styles: os.environ.get("X") and os.environ["X"].
                found |= set(re.findall(r'environ\.get\(\s*"([A-Z][A-Z0-9_]*)"', text))
                found |= set(re.findall(r'environ\[\s*"([A-Z][A-Z0-9_]*)"\s*\]', text))
        return found

    def test_no_variable_is_read_without_being_documented(self):
        undocumented = self.code_keys() - self.example_keys()
        assert not undocumented, f"read by code but missing from .env.example: {undocumented}"

    def test_no_documented_variable_is_unread(self):
        # Variables consumed outside Python, so absent from code_keys().
        consumed_elsewhere = {
            "GEMINI_API_KEY",          # read by the Gemini SDK itself
            "PORT",                    # read by the Dockerfile's CMD
            "NEXT_PUBLIC_API_BASE_URL",  # inlined into the frontend at build time
        }
        unread = self.example_keys() - self.code_keys() - consumed_elsewhere
        assert not unread, f"documented in .env.example but read by nothing: {unread}"

    @staticmethod
    def example_text() -> str:
        return (pathlib.Path(__file__).resolve().parent.parent / ".env.example").read_text()

    def test_no_variable_interpolation(self):
        body = "\n".join(ln for ln in self.example_text().splitlines()
                          if not ln.lstrip().startswith("#"))
        assert "${" not in body, "${} in .env.example: copied literally by kubectl/compose"

    def test_no_inline_comments(self):
        # python-dotenv strips a trailing comment only when a value precedes it:
        # `KEY=   # hint` parses as the value "# hint", not as empty. A blank
        # secret with a hint beside it would start the app with the hint as its
        # password rather than failing.
        offenders = [
            ln for ln in self.example_text().splitlines()
            if "=" in ln and not ln.lstrip().startswith("#") and "#" in ln.split("=", 1)[1]
        ]
        assert not offenders, f"inline comments after a value: {offenders}"

    def test_timeouts_are_ordered_innermost_strictest(self):
        keys = {}
        text = (pathlib.Path(__file__).resolve().parent.parent / ".env.example").read_text()
        for line in text.splitlines():
            if match := re.match(r"^([A-Z][A-Z0-9_]*)=(\S+)", line.strip()):
                keys[match.group(1)] = match.group(2)
        classify_s = int(keys["CLASSIFY_TIMEOUT_MS"]) / 1000
        assert classify_s < int(keys["BACKEND_TIMEOUT_SECONDS"])
