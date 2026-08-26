
import json, sys
sys.path.insert(0, '.')
from ms_library import parse, format_ms

results = {"parse": {}, "format": {}}
for case in ["100","1m","1h","2d","1y","1.5h","-100ms","100 milliseconds","2.5 hrs","1mo","2w","30s","500","10s","2.5m","1.25d","0.5h"]:
    try:
        val = parse(case)
        results["parse"][case] = val
    except Exception as e:
        results["parse"][case] = str(e)

for val in [100,60000,3600000,172800000,31557600000,-5400000,0,1500,86400000,2592000000]:
    try:
        results["format"][str(val)] = format_ms(val)
    except Exception as e:
        results["format"][str(val)] = str(e)

print(json.dumps(results))
