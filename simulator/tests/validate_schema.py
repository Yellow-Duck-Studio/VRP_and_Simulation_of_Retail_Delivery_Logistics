"""Validate test data against JSON schema."""
import json
from jsonschema import validate, ValidationError

def validate_data(data_path: str, schema_path: str) -> bool:
    """Validate JSON data against schema."""
    with open(data_path, 'r') as f:
        data = json.load(f)
    
    with open(schema_path, 'r') as f:
        schema = json.load(f)
    
    try:
        validate(instance=data, schema=schema)
        print(f"✓ {data_path} is valid")
        return True
    except ValidationError as e:
        print(f"✗ {data_path} validation failed:")
        print(f"  Path: {' -> '.join(str(p) for p in e.path)}")
        print(f"  Message: {e.message}")
        return False

if __name__ == "__main__":
    import sys
    
    data_path = "../test_data_innopolis.json"
    schema_path = "../input_schema.json"
    
    success = validate_data(data_path, schema_path)
    sys.exit(0 if success else 1)
