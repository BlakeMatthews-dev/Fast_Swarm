"""
Test _extract_pattern_refs() helper function - CONTRACT-BASED (TDD/EDD)

This helper extracts pattern references from an agent's assigned_patterns field.
It handles 3 forms:
1. Embedded patterns (dict with entry_conditions) -> go to embedded_patterns list
2. Reference IDs (strings) -> go to reference_ids list
3. Partial dicts (pattern_id but no conditions) -> extract ID, go to reference_ids

EDD Evidence:
a) DETERMINISM - same agent -> same output tuple
b) DIVISION SAFETY - empty assigned_patterns doesn't crash
c) BOUNDARY CONDITIONS - None, empty dict, empty list all handled
"""

import pytest


# ============================================================================
# Test Data Helpers
# ============================================================================


class MockAgent:
    """Mock agent with assigned_patterns attribute."""

    def __init__(self, assigned_patterns):
        self.assigned_patterns = assigned_patterns


def make_embedded_pattern(pattern_id: str) -> dict:
    """Create a fully embedded pattern with conditions."""
    return {
        "pattern_id": pattern_id,
        "name": f"Pattern {pattern_id}",
        "entry_conditions": [{"indicator": "rsi", "operator": "<", "value": 30}],
        "exit_conditions": [{"indicator": "rsi", "operator": ">", "value": 70}],
    }


def make_partial_pattern(pattern_id: str) -> dict:
    """Create a partial pattern dict (has pattern_id but no conditions)."""
    return {
        "pattern_id": pattern_id,
        "name": f"Partial {pattern_id}",
        # No entry_conditions or exit_conditions
    }


# ============================================================================
# BOUNDARY CONDITIONS - Empty/None inputs
# ============================================================================


class TestBoundaryConditions:
    """CONTRACT: Function handles empty/None inputs gracefully."""

    def test_none_assigned_patterns(self):
        """CONTRACT: None assigned_patterns returns empty lists."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        agent = MockAgent(assigned_patterns=None)
        embedded, refs = _extract_pattern_refs(agent)

        assert embedded == []
        assert refs == []

    def test_empty_dict_assigned_patterns(self):
        """CONTRACT: Empty dict {} returns empty lists."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        agent = MockAgent(assigned_patterns={})
        embedded, refs = _extract_pattern_refs(agent)

        assert embedded == []
        assert refs == []

    def test_empty_list_assigned_patterns(self):
        """CONTRACT: Empty list [] returns empty lists."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        agent = MockAgent(assigned_patterns=[])
        embedded, refs = _extract_pattern_refs(agent)

        assert embedded == []
        assert refs == []

    def test_dict_with_empty_base(self):
        """CONTRACT: Dict with empty base list returns empty lists."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        agent = MockAgent(assigned_patterns={"base": []})
        embedded, refs = _extract_pattern_refs(agent)

        assert embedded == []
        assert refs == []


# ============================================================================
# FORM 1: Embedded Patterns (dict with entry_conditions)
# ============================================================================


class TestEmbeddedPatterns:
    """CONTRACT: Embedded patterns (have entry_conditions) go to embedded list."""

    def test_single_embedded_pattern_in_base(self):
        """CONTRACT: Embedded pattern in base dict goes to embedded list."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        pattern = make_embedded_pattern("pat-001")
        agent = MockAgent(assigned_patterns={"base": [pattern]})

        embedded, refs = _extract_pattern_refs(agent)

        assert len(embedded) == 1
        assert embedded[0]["pattern_id"] == "pat-001"
        assert embedded[0].get("entry_conditions") is not None
        assert refs == []

    def test_multiple_embedded_patterns(self):
        """CONTRACT: Multiple embedded patterns all go to embedded list."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        patterns = [
            make_embedded_pattern("pat-001"),
            make_embedded_pattern("pat-002"),
            make_embedded_pattern("pat-003"),
        ]
        agent = MockAgent(assigned_patterns={"base": patterns})

        embedded, refs = _extract_pattern_refs(agent)

        assert len(embedded) == 3
        assert {p["pattern_id"] for p in embedded} == {"pat-001", "pat-002", "pat-003"}
        assert refs == []

    def test_embedded_pattern_in_list_format(self):
        """CONTRACT: Embedded pattern in list format goes to embedded list."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        pattern = make_embedded_pattern("pat-001")
        agent = MockAgent(assigned_patterns=[pattern])

        embedded, refs = _extract_pattern_refs(agent)

        assert len(embedded) == 1
        assert embedded[0]["pattern_id"] == "pat-001"
        assert refs == []


# ============================================================================
# FORM 2: Reference IDs (strings)
# ============================================================================


class TestReferenceIDs:
    """CONTRACT: String pattern IDs go to reference_ids list."""

    def test_single_string_id_in_base(self):
        """CONTRACT: String pattern ID in base dict goes to refs list."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        agent = MockAgent(assigned_patterns={"base": ["pattern-abc"]})

        embedded, refs = _extract_pattern_refs(agent)

        assert embedded == []
        assert refs == ["pattern-abc"]

    def test_multiple_string_ids(self):
        """CONTRACT: Multiple string IDs all go to refs list."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        agent = MockAgent(assigned_patterns={"base": ["pat-1", "pat-2", "pat-3"]})

        embedded, refs = _extract_pattern_refs(agent)

        assert embedded == []
        assert set(refs) == {"pat-1", "pat-2", "pat-3"}

    def test_string_ids_in_list_format(self):
        """CONTRACT: String IDs in list format go to refs list."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        agent = MockAgent(assigned_patterns=["pattern-xyz"])

        embedded, refs = _extract_pattern_refs(agent)

        assert embedded == []
        assert refs == ["pattern-xyz"]


# ============================================================================
# FORM 3: Partial Dicts (pattern_id but no conditions)
# ============================================================================


class TestPartialDicts:
    """CONTRACT: Partial dicts (pattern_id, no conditions) extract ID to refs."""

    def test_partial_dict_with_pattern_id(self):
        """CONTRACT: Dict with pattern_id but no conditions -> ID goes to refs."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        partial = make_partial_pattern("pat-partial")
        agent = MockAgent(assigned_patterns={"base": [partial]})

        embedded, refs = _extract_pattern_refs(agent)

        assert embedded == []
        assert refs == ["pat-partial"]

    def test_partial_dict_with_id_key(self):
        """CONTRACT: Dict with 'id' key (not pattern_id) -> ID goes to refs."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        partial = {"id": "pat-alt-id", "name": "Alt Pattern"}
        agent = MockAgent(assigned_patterns={"base": [partial]})

        embedded, refs = _extract_pattern_refs(agent)

        assert embedded == []
        assert refs == ["pat-alt-id"]

    def test_partial_dict_with_empty_conditions(self):
        """CONTRACT: Dict with empty entry_conditions -> ID goes to refs."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        partial = {
            "pattern_id": "pat-empty-cond",
            "entry_conditions": [],  # Empty, not None
            "exit_conditions": [],
        }
        agent = MockAgent(assigned_patterns={"base": [partial]})

        embedded, refs = _extract_pattern_refs(agent)

        # Empty conditions = not valid embedded pattern
        assert embedded == []
        assert refs == ["pat-empty-cond"]


# ============================================================================
# MIXED INPUTS - All 3 forms together
# ============================================================================


class TestMixedInputs:
    """CONTRACT: Function correctly separates all 3 forms."""

    def test_mixed_embedded_and_refs_in_base(self):
        """CONTRACT: Mix of embedded and string IDs are separated correctly."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        patterns = [
            make_embedded_pattern("embed-1"),
            "ref-1",
            make_embedded_pattern("embed-2"),
            "ref-2",
        ]
        agent = MockAgent(assigned_patterns={"base": patterns})

        embedded, refs = _extract_pattern_refs(agent)

        assert len(embedded) == 2
        assert {p["pattern_id"] for p in embedded} == {"embed-1", "embed-2"}
        assert set(refs) == {"ref-1", "ref-2"}

    def test_all_three_forms_mixed(self):
        """CONTRACT: Embedded, string IDs, and partial dicts all separated."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        patterns = [
            make_embedded_pattern("embed-1"),
            "ref-string",
            make_partial_pattern("partial-1"),
        ]
        agent = MockAgent(assigned_patterns={"base": patterns})

        embedded, refs = _extract_pattern_refs(agent)

        assert len(embedded) == 1
        assert embedded[0]["pattern_id"] == "embed-1"
        assert set(refs) == {"ref-string", "partial-1"}


# ============================================================================
# DETERMINISM - Same input -> same output
# ============================================================================


class TestDeterminism:
    """EDD: Same input produces same output every time."""

    def test_deterministic_output(self):
        """EDD: Calling function multiple times produces identical results."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        patterns = [
            make_embedded_pattern("det-1"),
            "det-ref",
            make_partial_pattern("det-partial"),
        ]
        agent = MockAgent(assigned_patterns={"base": patterns})

        result1 = _extract_pattern_refs(agent)
        result2 = _extract_pattern_refs(agent)
        result3 = _extract_pattern_refs(agent)

        # Same embedded patterns
        assert result1[0] == result2[0] == result3[0]
        # Same reference IDs
        assert result1[1] == result2[1] == result3[1]

    def test_order_preserved(self):
        """EDD: Order of patterns is preserved in output."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        patterns = [
            make_embedded_pattern("first"),
            make_embedded_pattern("second"),
            make_embedded_pattern("third"),
        ]
        agent = MockAgent(assigned_patterns={"base": patterns})

        embedded, refs = _extract_pattern_refs(agent)

        # Order should be preserved
        assert [p["pattern_id"] for p in embedded] == ["first", "second", "third"]


# ============================================================================
# EDGE CASES
# ============================================================================


class TestEdgeCases:
    """CONTRACT: Edge cases are handled gracefully."""

    def test_dict_without_base_key(self):
        """CONTRACT: Dict without 'base' key returns empty lists."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        agent = MockAgent(assigned_patterns={"other_key": ["pat-1"]})

        embedded, refs = _extract_pattern_refs(agent)

        assert embedded == []
        assert refs == []

    def test_pattern_dict_with_no_id_fields(self):
        """CONTRACT: Dict with no pattern_id or id is skipped."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        partial = {"name": "No ID Pattern"}  # No pattern_id or id
        agent = MockAgent(assigned_patterns={"base": [partial]})

        embedded, refs = _extract_pattern_refs(agent)

        # Should be skipped entirely
        assert embedded == []
        assert refs == []

    def test_empty_string_id_skipped(self):
        """CONTRACT: Empty string pattern IDs are skipped."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        agent = MockAgent(assigned_patterns={"base": ["", "valid-id", ""]})

        embedded, refs = _extract_pattern_refs(agent)

        assert embedded == []
        assert refs == ["valid-id"]  # Empty strings filtered out

    def test_none_in_list_skipped(self):
        """CONTRACT: None values in list are skipped."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        patterns = [None, make_embedded_pattern("valid"), None, "valid-ref"]
        agent = MockAgent(assigned_patterns={"base": patterns})

        embedded, refs = _extract_pattern_refs(agent)

        assert len(embedded) == 1
        assert refs == ["valid-ref"]


# ============================================================================
# RETURN TYPE CONTRACT
# ============================================================================


class TestReturnType:
    """CONTRACT: Function returns tuple of (list[dict], list[str])."""

    def test_return_type_is_tuple(self):
        """CONTRACT: Return value is a tuple."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        agent = MockAgent(assigned_patterns={"base": []})
        result = _extract_pattern_refs(agent)

        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_first_element_is_list_of_dicts(self):
        """CONTRACT: First element is list of pattern dicts."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        agent = MockAgent(assigned_patterns={"base": [make_embedded_pattern("test")]})
        embedded, refs = _extract_pattern_refs(agent)

        assert isinstance(embedded, list)
        assert all(isinstance(p, dict) for p in embedded)

    def test_second_element_is_list_of_strings(self):
        """CONTRACT: Second element is list of pattern ID strings."""
        from Fast_Swarm.Agents.Services.backtest_service import _extract_pattern_refs

        agent = MockAgent(assigned_patterns={"base": ["ref-1", "ref-2"]})
        embedded, refs = _extract_pattern_refs(agent)

        assert isinstance(refs, list)
        assert all(isinstance(r, str) for r in refs)
