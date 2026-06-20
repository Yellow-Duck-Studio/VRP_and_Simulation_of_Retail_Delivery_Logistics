import pytest
import json
from jsonschema import validate, ValidationError
from copy import deepcopy


@pytest.fixture
def schema():
    with open("input_schema.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def valid_data(sample_json_data):
    return sample_json_data


def test_valid_json_schema(schema, valid_data):
    try:
        validate(instance=valid_data, schema=schema)
    except ValidationError as e:
        pytest.fail(f"Valid data failed schema validation: {e}")


def test_invalid_missing_required_field(schema, valid_data):
    invalid_data = deepcopy(valid_data)
    del invalid_data["orders"][0]["mass_kg"]

    with pytest.raises(ValidationError) as exc_info:
        validate(instance=invalid_data, schema=schema)

    assert "mass_kg" in exc_info.value.message


def test_invalid_type_field(schema, valid_data):
    invalid_data = deepcopy(valid_data)
    invalid_data["courier_types"][0]["capacity_kg"] = "one hundred"

    with pytest.raises(ValidationError) as exc_info:
        validate(instance=invalid_data, schema=schema)

    assert "is not of type 'number'" in exc_info.value.message


def test_invalid_enum_value(schema, valid_data):
    invalid_data = deepcopy(valid_data)
    invalid_data["couriers"][0]["status"] = "flying"

    with pytest.raises(ValidationError) as exc_info:
        validate(instance=invalid_data, schema=schema)

    assert "flying" in exc_info.value.message