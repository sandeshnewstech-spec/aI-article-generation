import json
import re

bad_json = '[{"text": "A"} {"text": "B"}]'
fixed = re.sub(r'}\s*{', '}, {', bad_json)
print(fixed)
print(json.loads(fixed))
