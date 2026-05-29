# MyTraL: my trailing log
#
# Copyright (C) 2015-2026 Martin Dvorak <martin.dvorak@mindforger.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import pytest

from mytral import routes


@pytest.mark.mytral
def test_markdown_filter_basic():
    """Test basic markdown conversion."""
    # GIVEN
    markdown_text = "This is **bold** and *italic*"

    # WHEN
    result = routes.markdown_filter(markdown_text)

    # THEN
    assert "<strong>bold</strong>" in str(result)
    assert "<em>italic</em>" in str(result)
    print(f"DONE: Basic markdown conversion works: {result}")


@pytest.mark.mytral
def test_markdown_filter_empty():
    """Test markdown filter with empty string."""
    # GIVEN
    markdown_text = ""

    # WHEN
    result = routes.markdown_filter(markdown_text)

    # THEN
    assert result == ""
    print("DONE: Empty string handling works")


@pytest.mark.mytral
def test_markdown_filter_none():
    """Test markdown filter with None."""
    # GIVEN
    markdown_text = None

    # WHEN
    result = routes.markdown_filter(markdown_text)

    # THEN
    assert result == ""
    print("DONE: None handling works")


@pytest.mark.mytral
def test_markdown_filter_list():
    """Test markdown list conversion."""
    # GIVEN
    markdown_text = "- Item 1\n- Item 2\n- Item 3"

    # WHEN
    result = routes.markdown_filter(markdown_text)

    # THEN
    assert "<ul>" in str(result)
    assert "<li>Item 1" in str(result)
    assert "<li>Item 2" in str(result)
    assert "<li>Item 3" in str(result)
    print(f"DONE: List markdown conversion works: {result}")


@pytest.mark.mytral
def test_markdown_filter_newlines():
    """Test markdown newline conversion with nl2br extension."""
    # GIVEN
    markdown_text = "Line 1\nLine 2\nLine 3"

    # WHEN
    result = routes.markdown_filter(markdown_text)

    # THEN
    # nl2br extension converts single newlines to <br>
    assert "<br" in str(result).lower()
    print(f"DONE: Newline to br conversion works: {result}")


@pytest.mark.mytral
def test_markdown_filter_xss_script_tag():
    """Test that script tags are stripped."""
    # GIVEN a script-tag XSS payload
    markdown_text = "<script>alert('XSS')</script>"

    # WHEN filtered
    result = str(routes.markdown_filter(markdown_text))

    # THEN script tag is stripped; text content may remain as inert plain text
    assert "<script" not in result.lower()
    assert "</script>" not in result.lower()
    print("DONE - script tag stripped")


@pytest.mark.mytral
def test_markdown_filter_xss_onerror():
    """Test that onerror event handlers are stripped."""
    # GIVEN an onerror handler payload
    markdown_text = "<img src=x onerror=alert(1)>"

    # WHEN filtered
    result = str(routes.markdown_filter(markdown_text))

    # THEN handler is stripped
    assert "onerror" not in result.lower()
    print("DONE - onerror handler stripped")


@pytest.mark.mytral
def test_markdown_filter_xss_javascript_protocol():
    """Test that javascript: link protocol is blocked."""
    # GIVEN a javascript: protocol link
    markdown_text = "[click me](javascript:alert('XSS'))"

    # WHEN filtered
    result = str(routes.markdown_filter(markdown_text))

    # THEN javascript: protocol is removed
    assert "javascript:" not in result.lower()
    print("DONE - javascript: protocol blocked")


@pytest.mark.mytral
def test_markdown_filter_xss_iframe():
    """Test that iframe tags are stripped."""
    # GIVEN an iframe embed payload
    markdown_text = "<iframe src='http://evil.com'></iframe>"

    # WHEN filtered
    result = str(routes.markdown_filter(markdown_text))

    # THEN iframe is stripped
    assert "<iframe" not in result.lower()
    print("DONE - iframe stripped")
