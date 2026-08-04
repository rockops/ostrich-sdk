from src.util import *

# Define custom filters and global functions

# Filter & global for unit tests
def unitGlobal(s):
    return s+"/unit"


# Parses a JSON string and returns an array.
# If the element is already an array, no change is made.
# If the element is a single object, it is returned as a single-element array.
def jsonArray(jsonstr: str):
    import json
    try:
        json_data = json.loads(jsonstr)
    except Exception as e:
        logging.error(f"Error parsing JSON:\n{jsonstr}")
        raise
    if isinstance(json_data, list):
        return jsonstr
    else:
        return json.dumps([json_data], indent=2)

addFilter('gunit', unitGlobal)
addGlobal('gunit', unitGlobal)
addFilter('jsonArray', jsonArray)
