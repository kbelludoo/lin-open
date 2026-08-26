
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sc", r"/home/k/Downloads/lin-master/examples/.multi_emit_out/safe_compare.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert m.safe_compare("ab","ab") is True
assert m.safe_compare("a","b") is False
assert m.safe_compare("prefix","pre") is False
assert m.safe_compare("","") is True
print("ok py safe-compare")
