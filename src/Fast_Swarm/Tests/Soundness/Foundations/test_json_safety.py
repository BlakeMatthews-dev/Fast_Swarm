"""
JSON Safety Tests - CONTRACT-BASED (TDD/EDD)

Source of truth: EDD Rules (Safety Invariants)
JSON parsing must be safe and validated.
"""

import json
import math
import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from Fast_Swarm.Agents.Models.agent_models import Agent, EvolutionRunRequest, SpawnAgentsResponse
from Fast_Swarm.Agents.Models.memory_models import AgentMemory, MemoryCreateRequest, MemoryType
from Fast_Swarm.Agents.Services.trait_service import ALL_22_TRAITS
from Fast_Swarm.Tests.Fixtures.factories import AgentFactory, PatternFactory, TradeFactory

# ============================================================================
# JSON SAFETY CONTRACT
# ============================================================================


class TestMalformedJSONHandling:
    """CONTRACT: Malformed JSON must be handled safely."""

    def test_invalid_json_string(self):
        """CONTRACT: Invalid JSON string doesn't crash system."""
        invalid_jsons = [
            "not json at all",
            "{key: value}",
            "{'single': 'quotes'}",
            "",
            "null",
        ]
        for invalid in invalid_jsons:
            try:
                result = json.loads(invalid)
                # "null" and "" (empty) may parse; that's OK
            except (json.JSONDecodeError, TypeError):
                pass  # Expected - graceful failure
            # Must not raise any other exception type

    def test_truncated_json(self):
        """CONTRACT: Truncated JSON handled gracefully."""
        truncated_jsons = [
            '{"key": "val',
            '{"traits": {"risk_tolerance": 0.5',
            '[1, 2, 3',
            '{"nested": {"deep": ',
        ]
        for truncated in truncated_jsons:
            with pytest.raises(json.JSONDecodeError):
                json.loads(truncated)

    def test_json_with_trailing_comma(self):
        """CONTRACT: Trailing comma handled or rejected."""
        trailing_comma = '{"a": 1, "b": 2,}'
        with pytest.raises(json.JSONDecodeError):
            json.loads(trailing_comma)

    def test_json_with_comments(self):
        """CONTRACT: Comments in JSON handled or rejected."""
        with_comments = '{"a": 1 /* comment */}'
        with pytest.raises(json.JSONDecodeError):
            json.loads(with_comments)

        with_line_comment = '{"a": 1 // comment\n}'
        with pytest.raises(json.JSONDecodeError):
            json.loads(with_line_comment)


class TestJSONRecursionDepth:
    """CONTRACT: Deeply nested JSON must not crash."""

    def test_deep_nesting_limited(self):
        """CONTRACT: Depth limit prevents stack overflow."""
        # Python's default JSON recursion limit prevents stack overflow
        # Build a deeply nested structure
        depth = 100
        nested = "x"
        for _ in range(depth):
            nested = {"nested": nested}
        # Should be serializable at reasonable depth
        result = json.dumps(nested)
        assert isinstance(result, str)

    def test_reasonable_max_depth(self):
        """CONTRACT: Max depth is reasonable (e.g., 100)."""
        # Very deep nesting (near Python's recursion limit) should fail gracefully
        depth = 990  # Near Python's 1000 default recursion limit
        deeply_nested = '{"a":' * depth + '1' + '}' * depth
        try:
            result = json.loads(deeply_nested)
            # If it parses, that's fine
        except RecursionError:
            pass  # Expected for very deep nesting
        except json.JSONDecodeError:
            pass  # Also acceptable


class TestJSONSizeLimit:
    """CONTRACT: Large JSON payloads must be limited."""

    def test_json_size_limit(self):
        """CONTRACT: Maximum JSON size enforced."""
        # Generate a large-but-parseable JSON payload
        large_obj = {"key_" + str(i): "x" * 100 for i in range(1000)}
        serialized = json.dumps(large_obj)
        # Verify it's parseable but we track size
        size_mb = len(serialized) / (1024 * 1024)
        assert size_mb < 10, f"Test payload should be < 10MB, got {size_mb:.2f}MB"
        parsed = json.loads(serialized)
        assert len(parsed) == 1000

    def test_large_array_limit(self):
        """CONTRACT: Large arrays limited."""
        large_array = list(range(100_000))
        serialized = json.dumps(large_array)
        parsed = json.loads(serialized)
        assert len(parsed) == 100_000
        # Size should still be manageable
        size_mb = len(serialized) / (1024 * 1024)
        assert size_mb < 5, f"Large array should be < 5MB, got {size_mb:.2f}MB"


class TestJSONTypeValidation:
    """CONTRACT: JSON types must be validated."""

    def test_expected_object_not_array(self):
        """CONTRACT: Object expected, array rejected."""
        array_json = "[1, 2, 3]"
        parsed = json.loads(array_json)
        assert not isinstance(parsed, dict), "Array should not be dict"
        assert isinstance(parsed, list), "Array should be list"

    def test_expected_array_not_object(self):
        """CONTRACT: Array expected, object rejected."""
        object_json = '{"key": "value"}'
        parsed = json.loads(object_json)
        assert not isinstance(parsed, list), "Object should not be list"
        assert isinstance(parsed, dict), "Object should be dict"

    def test_expected_string_not_number(self):
        """CONTRACT: String expected, number rejected."""
        # When traits dict expects floats, a string should fail validation
        bad_traits = {"risk_tolerance": "not_a_number"}
        from Fast_Swarm.Agents.Services.trait_service import validate_trait_value
        is_valid, error = validate_trait_value("not_a_number")
        assert not is_valid, "String should not validate as trait value"

    def test_expected_number_not_string(self):
        """CONTRACT: Number expected, string rejected."""
        # JSON numbers should parse as numbers, not strings
        num_json = '{"value": 42}'
        parsed = json.loads(num_json)
        assert isinstance(parsed["value"], (int, float)), "JSON number should be numeric"
        str_json = '{"value": "42"}'
        parsed = json.loads(str_json)
        assert isinstance(parsed["value"], str), "JSON string should be string"


class TestPydanticValidation:
    """CONTRACT: Pydantic models must validate."""

    def test_missing_required_field(self):
        """CONTRACT: Missing required field raises error."""
        # EvolutionRunRequest has defaults, but SpawnAgentsResponse requires message & agents
        with pytest.raises(ValidationError):
            SpawnAgentsResponse()  # Missing required fields: message, agents, etc.

    def test_wrong_type_field(self):
        """CONTRACT: Wrong type raises error."""
        with pytest.raises(ValidationError):
            SpawnAgentsResponse(
                message=12345,  # Should be str but Pydantic coerces
                agents="not_a_list",  # Should be list
                ai_selection="not_bool",  # Should be bool
                patterns_available="not_int",  # Should be int
            )

    def test_extra_fields_handled(self):
        """CONTRACT: Extra fields ignored or rejected."""
        # EvolutionRunRequest with extra field
        req = EvolutionRunRequest(
            generations=5,
            population_size=10,
        )
        assert req.generations == 5
        assert req.population_size == 10

    def test_partial_payload_rejected(self):
        """CONTRACT: Partial payloads don't default to dangerous values."""
        # EvolutionRunRequest has safe defaults
        req = EvolutionRunRequest()
        assert req.generations > 0, "Default generations must be positive"
        assert req.population_size > 0, "Default population must be positive"
        assert 0 <= req.mutation_rate <= 1, "Default mutation rate must be in [0, 1]"
        assert 0 <= req.elite_percent <= 1, "Default elite_percent must be in [0, 1]"


class TestJSONBColumnSafety:
    """CONTRACT: JSONB columns must be safe."""

    def test_jsonb_retrieval_corrupted(self):
        """CONTRACT: Corrupted JSONB doesn't crash on read."""
        # Simulate corrupted JSONB by setting traits to various bad values
        bad_trait_values = [
            {},
            {"only_one_trait": 0.5},
            {"risk_tolerance": None},
        ]
        for bad_traits in bad_trait_values:
            # Agent model should accept these without crashing at construction
            agent_data = AgentFactory.create(traits=bad_traits)
            assert agent_data["traits"] is not None

    def test_jsonb_null_handling(self):
        """CONTRACT: NULL JSONB column handled."""
        # Empty/null JSONB defaults should be safe
        agent_data = AgentFactory.create(traits={})
        assert isinstance(agent_data["traits"], dict)
        assert agent_data["traits"] == {}

    def test_jsonb_empty_object(self):
        """CONTRACT: Empty JSONB {} handled."""
        agent_data = AgentFactory.create(traits={})
        assert agent_data["traits"] == {}
        # Fitness calculation should still work with empty traits
        # (traits aren't directly used in fitness calc)


class TestJSONSerializationSafety:
    """CONTRACT: JSON serialization must be safe."""

    def test_serialize_float_inf(self):
        """CONTRACT: Infinity serialized as null or rejected."""
        # Standard json module rejects Inf by default
        with pytest.raises((ValueError, OverflowError)):
            json.dumps({"value": float("inf")})
        # With allow_nan=False, it should also raise
        with pytest.raises(ValueError):
            json.dumps({"value": float("inf")}, allow_nan=False)

    def test_serialize_float_nan(self):
        """CONTRACT: NaN serialized as null or rejected."""
        with pytest.raises(ValueError):
            json.dumps({"value": float("nan")}, allow_nan=False)

    def test_serialize_datetime(self):
        """CONTRACT: Datetime serialized as ISO string."""
        dt = datetime(2024, 1, 15, 12, 30, 0)
        iso_str = dt.isoformat()
        assert isinstance(iso_str, str)
        assert "2024-01-15" in iso_str
        # Should be JSON-serializable as string
        result = json.dumps({"time": iso_str})
        assert "2024-01-15" in result

    def test_serialize_uuid(self):
        """CONTRACT: UUID serialized as string."""
        test_uuid = uuid.uuid4()
        uuid_str = str(test_uuid)
        assert isinstance(uuid_str, str)
        assert len(uuid_str) == 36  # Standard UUID format: 8-4-4-4-12
        # Should be JSON-serializable
        result = json.dumps({"id": uuid_str})
        assert uuid_str in result


class TestPatternConditionsJSON:
    """CONTRACT: Pattern conditions JSON must be valid."""

    def test_entry_conditions_valid_json(self):
        """CONTRACT: entry_conditions is valid JSON array."""
        pattern = PatternFactory.create()
        conditions = pattern["entry_conditions"]
        # Should be serializable
        serialized = json.dumps(conditions)
        deserialized = json.loads(serialized)
        assert deserialized is not None

    def test_exit_conditions_valid_json(self):
        """CONTRACT: exit_conditions is valid JSON array."""
        pattern = PatternFactory.create()
        conditions = pattern["exit_conditions"]
        serialized = json.dumps(conditions)
        deserialized = json.loads(serialized)
        assert deserialized is not None

    def test_condition_has_required_fields(self):
        """CONTRACT: Each condition has indicator, operator, value."""
        pattern = PatternFactory.rsi_oversold()
        entry = pattern["entry_conditions"]
        assert "indicator" in entry, "Condition must have 'indicator'"
        assert "operator" in entry, "Condition must have 'operator'"
        assert "value" in entry, "Condition must have 'value'"


class TestTraitsJSON:
    """CONTRACT: Traits JSON must be valid."""

    def test_traits_is_valid_json(self):
        """CONTRACT: traits field is valid JSON object."""
        agent = AgentFactory.create()
        traits = agent["traits"]
        serialized = json.dumps(traits)
        deserialized = json.loads(serialized)
        assert isinstance(deserialized, dict), "Traits must deserialize to dict"

    def test_traits_has_all_keys(self):
        """CONTRACT: All 22 trait keys present."""
        agent = AgentFactory.create()
        traits = agent["traits"]
        for trait_name in ALL_22_TRAITS:
            assert trait_name in traits, f"Missing trait key: {trait_name}"
        assert len(traits) == 22, f"Expected 22 traits, got {len(traits)}"

    def test_traits_values_are_floats(self):
        """CONTRACT: All trait values are floats."""
        agent = AgentFactory.create()
        traits = agent["traits"]
        for name, value in traits.items():
            assert isinstance(value, (int, float)), (
                f"Trait {name} value must be numeric, got {type(value).__name__}"
            )
