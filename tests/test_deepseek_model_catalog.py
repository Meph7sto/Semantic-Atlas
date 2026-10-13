"""Keep every model selector aligned with the current DeepSeek API catalog."""

from html.parser import HTMLParser
from pathlib import Path


class _ModelSelectorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.model_selectors = []
        self._options = None

    def handle_starttag(self, tag, attrs):
        if tag == "select":
            self._options = []
        elif tag == "option" and self._options is not None:
            value = dict(attrs).get("value", "")
            if value.startswith("deepseek-"):
                self._options.append(value)

    def handle_endtag(self, tag):
        if tag == "select":
            if self._options:
                self.model_selectors.append(self._options)
            self._options = None


def test_all_frontend_model_selectors_use_only_current_models():
    frontend = Path(__file__).resolve().parents[1] / "frontend" / "src"
    expected_models = {"deepseek-v4-pro", "deepseek-flash"}
    selector_count = 0

    for path in sorted(frontend.rglob("*.vue")):
        parser = _ModelSelectorParser()
        parser.feed(path.read_text(encoding="utf-8"))
        for models in parser.model_selectors:
            assert set(models) == expected_models, str(path.relative_to(frontend))
            assert len(models) == len(expected_models)
            selector_count += 1

    assert selector_count > 0
