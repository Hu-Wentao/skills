# /// script
# dependencies = ["regex", "pyyaml", "markdown-it-py"]
# ///
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("mdq", sys.argv[1])
mdq = importlib.util.module_from_spec(spec); sys.modules["mdq"] = mdq
spec.loader.exec_module(mdq)
out = {}
for p in sys.argv[3:]:
    doc = mdq.read_document(Path(p))
    recs, diags = mdq.extract_current(doc)
    q, qd = mdq.records_for_query(doc)
    out[p] = {"records": recs, "diagnostics": diags, "query": q, "query_diagnostics": qd}
Path(sys.argv[2]).write_text(json.dumps(out, sort_keys=True, ensure_ascii=False))
