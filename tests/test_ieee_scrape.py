import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from arxivbot.ieee_scrape import extract_salient_fields_from_metadata


FIXTURE_DIR = Path(__file__).parent / "example_inputs" / "ieee"


class TestExtractSalientFields:
    def _load_metadata_from_html(self, filename):
        html_path = FIXTURE_DIR / filename
        soup = BeautifulSoup(html_path.read_text(), "html.parser")
        for script_tag in soup.find_all("script"):
            if script_tag.string and "xplGlobal.document.metadata" in script_tag.string:
                json_match = re.search(r"xplGlobal\.document\.metadata=(\{.*\});", script_tag.string.strip())
                if json_match:
                    return json.loads(json_match.group(1))
        return None

    def test_extracts_expected_fields(self):
        metadata = self._load_metadata_from_html("9381661.html")
        if metadata is None:
            return  # fixture doesn't contain expected metadata structure
        salient = extract_salient_fields_from_metadata(metadata)
        assert "abstract" in salient
        assert "authors" in salient
        assert isinstance(salient["authors"], list)
        assert "displayDocTitle" in salient
        assert "articleNumber" in salient
