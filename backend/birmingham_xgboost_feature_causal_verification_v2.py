from __future__ import annotations

"""SmartPark AI - Birmingham XGBoost feature causal verification V2 (optimized).

This version keeps the V2 audit policy but fixes the performance problem by:
- reading each ML .py file once;
- parsing each AST once;
- building function/line/temporal indexes once;
- building feature evidence from the in-memory index;
- never reparsing source for each feature.

It does not load test.parquet, train XGBoost, rebuild the feature pipeline,
or modify persisted datasets.
"""

import ast
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

TARGET = "target_occupancy_rate_30m"
EXPECTED_FEATURE_COUNT = 296
FORECAST_MINUTES = 30
LINEAGE_FEATURE_FILE = "birmingham_xgboost_feature_lineage_features.csv"
LINEAGE_SOURCE_FILE = "birmingham_xgboost_feature_lineage_source_findings.csv"
OUT_DIR = "xgboost_feature_causal_verification_v2"
OUT_JSON = "birmingham_xgboost_feature_causal_verification_v2.json"
OUT_FEATURES = "birmingham_xgboost_feature_causal_verification_v2_features.csv"
OUT_SOURCE = "birmingham_xgboost_feature_causal_verification_v2_source_findings.csv"
OUT_SUMMARY = "birmingham_xgboost_feature_causal_verification_v2_summary.csv"
OUT_AST = "birmingham_xgboost_feature_causal_verification_v2_ast_findings.csv"

FUTURE_WORDS = ("target_", "future_", "next_", "tomorrow_")
HISTORICAL_WORDS = (
    "lag_", "_lag", "lag", "rolling", "previous", "prior_",
    "historical", "lookback", "expanding", "ewm", "trend",
    "momentum", "volatility",
)
CURRENT_WORDS = (
    "current_state", "current_status", "availability_rate",
    "available_ratio", "vacancy_ratio", "occupied_ratio",
    "capacity_utilization", "occupancy_level", "demand_level",
    "demand_pressure", "demand_class",
)
TEMPORAL_WORDS = (
    "calendar", "quarter", "day_of_week", "dayofweek", "is_weekend",
    "holiday", "time_slot", "_sin", "_cos", "cyclic", "season",
)
TARGET_TERMS = (
    "target", "future_occupancy", "future_observed", "target_valid",
    "availability_column", "future_sequence_break", "future_operational_gap",
    "future_data_gap",
)


def norm(x: Any) -> str:
    return str(x).strip().lower().replace("-", "_").replace(" ", "_")


def tokens(x: str) -> set[str]:
    return {t for t in re.split(r"[^a-zA-Z0-9]+", norm(x)) if t}


def contains(x: str, words: tuple[str, ...]) -> bool:
    x = norm(x)
    return any(w in x for w in words)


def kv(label: str, value: Any, width: int = 43) -> None:
    print(f"{label:<{width}} : {value}")


def section(title: str) -> None:
    print(f"\n--- {title} ---")


def header(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


@dataclass
class Finding:
    source_file: str
    line_number: int
    finding_type: str
    context: str
    function_name: str = ""
    target_context: bool = False
    feature_context: bool = False
    future_or_forward: bool = False
    negative_shift: bool = False
    centered_rolling: bool = False
    classification: str = ""


@dataclass
class ASTFinding:
    source_file: str
    line_number: int
    function_name: str
    operation: str
    expression: str
    shift_value: Optional[int] = None
    negative_shift: bool = False
    centered_rolling: bool = False
    target_context: bool = False
    feature_context: bool = False


@dataclass
class Line:
    file: str
    number: int
    text: str
    function: str
    tokens: tuple[str, ...]


@dataclass
class Contract:
    feature: str
    family: str
    verdict: str
    source_evidence: bool
    source_files: list[str] = field(default_factory=list)
    source_functions: list[str] = field(default_factory=list)
    source_expressions: list[str] = field(default_factory=list)
    source_columns: list[str] = field(default_factory=list)
    temporal_operations: list[str] = field(default_factory=list)
    latest_information_boundary: str = ""
    availability_basis: str = ""
    causal_evidence: str = ""
    future_operation_detected: bool = False
    negative_shift_detected: bool = False
    centered_rolling_detected: bool = False
    forward_operation_detected: bool = False
    target_context_only: bool = False
    feature_context_future: bool = False
    realtime_contract_required: bool = False
    causal_review_required: bool = False
    potential_leakage: bool = False
    confidence: str = ""
    notes: list[str] = field(default_factory=list)


class Index:
    def __init__(self) -> None:
        self.lines: list[Line] = []
        self.files: list[str] = []
        self.token_lines: dict[str, set[int]] = defaultdict(set)
        self.exact_lines: dict[str, set[int]] = defaultdict(set)
        self.findings: list[Finding] = []
        self.finding_at: dict[tuple[str, int], list[int]] = defaultdict(list)
        self.ast_findings: list[ASTFinding] = []


def repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in (here.parent, here):
        if (candidate / "datasets" / "processed" / "birmingham").exists():
            return candidate
    return here.parent


def paths(root: Path) -> dict[str, Path]:
    processed = root / "datasets" / "processed" / "birmingham"
    target = processed / "target_occupancy_rate_30m"
    lineage = processed / "xgboost_feature_lineage"
    ml = root / "backend" / "app" / "ml"
    if not ml.exists():
        ml = root / "app" / "ml"
    return {
        "processed": processed,
        "train": target / "train.parquet",
        "validation": target / "validation.parquet",
        "test": target / "test.parquet",
        "manifest": processed / "training_dataset_manifest.json",
        "lineage_features": lineage / LINEAGE_FEATURE_FILE,
        "lineage_source": lineage / LINEAGE_SOURCE_FILE,
        "ml": ml,
        "out": processed / OUT_DIR,
    }


def validate_files(p: dict[str, Path]) -> None:
    section("DATASET FILE VALIDATION")
    for label, key in (
        ("Training dataset", "train"), ("Validation dataset", "validation"),
        ("Test dataset", "test"), ("Feature manifest", "manifest"),
        ("Existing lineage feature CSV", "lineage_features"),
        ("Existing lineage source CSV", "lineage_source"),
    ):
        kv(label, p[key])
    for label, key in (
        ("Training file exists", "train"), ("Validation file exists", "validation"),
        ("Test file exists", "test"), ("Manifest exists", "manifest"),
        ("Lineage feature artifact exists", "lineage_features"),
        ("Lineage source artifact exists", "lineage_source"),
    ):
        kv(label, "PASS" if p[key].exists() else "FAIL")
    print("\nTest dataset exists but will NOT be loaded.")
    missing = [k for k in ("train", "validation", "test", "manifest", "lineage_features", "lineage_source") if not p[k].exists()]
    if missing:
        raise RuntimeError("Required file(s) missing: " + ", ".join(missing))


def load_manifest(path: Path) -> dict[str, Any]:
    section("LOADING FEATURE MANIFEST")
    m = json.loads(path.read_text(encoding="utf-8"))
    features = [str(x) for x in m.get("feature_columns", [])]
    kv("Registered features", len(features))
    if not features:
        raise RuntimeError("Manifest contains no feature_columns.")
    return m


def load_data(p: dict[str, Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    section("LOADING PERSISTED DATASETS")
    print("Loading training dataset...")
    train = pd.read_parquet(p["train"])
    print("Loading validation dataset...")
    val = pd.read_parquet(p["validation"])
    kv("Training rows", f"{len(train):,}")
    kv("Validation rows", f"{len(val):,}")
    return train, val


def validate_registry(train: pd.DataFrame, val: pd.DataFrame, features: list[str]) -> None:
    section("FEATURE REGISTRY VALIDATION")
    reg = set(features)
    tr = reg & set(train.columns)
    va = reg & set(val.columns)
    kv("Registered features", len(reg))
    kv("Training model features", len(tr))
    kv("Validation model features", len(va))
    kv("Training feature registry", "PASS" if tr == reg else "FAIL")
    kv("Validation feature registry", "PASS" if va == reg else "FAIL")
    kv("Train/validation feature registry", "PASS" if tr == va == reg else "FAIL")
    metadata = sorted((set(train.columns) | set(val.columns)) - reg)
    print("\nPersisted non-feature / metadata columns excluded from causal verification:")
    for x in metadata:
        print(f"  - {x}")
    if tr != reg or va != reg:
        raise RuntimeError(f"Feature registry mismatch. Missing train={sorted(reg-tr)} val={sorted(reg-va)}")


def validate_target(train: pd.DataFrame, val: pd.DataFrame) -> None:
    section("TARGET CONTRACT VALIDATION")
    for label, df in (("Training", train), ("Validation", val)):
        if TARGET not in df.columns:
            raise RuntimeError(f"{label} dataset does not contain {TARGET}")
        y = pd.to_numeric(df[TARGET], errors="coerce")
        kv(f"{label} target rows", f"{len(y):,}")
        kv(f"{label} target nulls", int(y.isna().sum()))
        kv(f"{label} target mean", f"{y.mean():.6f}")
        kv(f"{label} target range", f"{y.min():.6f} -> {y.max():.6f}")
        if y.empty or y.isna().any() or y.min() < 0 or y.max() > 1:
            raise RuntimeError(f"{label} target contract failed")
    kv("Target contract", "PASS")


def function_map(tree: ast.AST, n: int) -> list[str]:
    spans: list[tuple[int, int, str]] = []
    stack: list[str] = []

    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            name = ".".join(stack + [node.name]) if stack else node.name
            spans.append((node.lineno, getattr(node, "end_lineno", node.lineno), name))
            stack.append(node.name); self.generic_visit(node); stack.pop()
        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            name = ".".join(stack + [node.name]) if stack else node.name
            spans.append((node.lineno, getattr(node, "end_lineno", node.lineno), name))
            stack.append(node.name); self.generic_visit(node); stack.pop()

    V().visit(tree)
    spans.sort(key=lambda x: (x[1] - x[0], x[0]))
    result = [""] * (n + 1)
    for start, end, name in spans:
        for i in range(max(1, start), min(n, end) + 1):
            if not result[i]:
                result[i] = name
    return result


def ast_shift_value(node: ast.Call) -> Optional[int]:
    if not node.args:
        return None
    a = node.args[0]
    if isinstance(a, ast.UnaryOp) and isinstance(a.op, ast.USub) and isinstance(a.operand, ast.Constant) and isinstance(a.operand.value, (int, float)):
        return -int(a.operand.value)
    if isinstance(a, ast.Constant) and isinstance(a.value, (int, float)):
        return int(a.value)
    return None


def context(text: str, fn: str) -> tuple[bool, bool]:
    s = (text + " " + fn).lower()
    target = any(x in s for x in TARGET_TERMS) or "target_" in s
    feature = any(x in s for x in ("feature", "features", "feature_columns", "feature_registry")) or "result[" in text.lower() or "dataframe[" in text.lower() or "df[" in text.lower()
    return target, feature


def build_source_index(root: Path) -> Index:
    section("BUILDING OPTIMIZED SOURCE INDEX")
    idx = Index()
    files = sorted(root.rglob("*.py"))
    idx.files = [str(x.relative_to(root)) for x in files]
    kv("ML source files scanned", len(files))

    for path in files:
        rel = str(path.relative_to(root))
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = source.splitlines()
        try:
            tree = ast.parse(source)
            fmap = function_map(tree, len(lines))
        except SyntaxError:
            tree = None
            fmap = [""] * (len(lines) + 1)

        # Index lines once.
        for no, raw in enumerate(lines, 1):
            txt = raw.strip()
            toks = tuple(sorted(tokens(txt)))
            lid = len(idx.lines)
            idx.lines.append(Line(rel, no, txt, fmap[no], toks))
            for t in toks:
                idx.token_lines[t].add(lid)
            # Exact feature-like identifiers in quoted strings and identifiers.
            ids = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", norm(txt)))
            for ident in ids:
                idx.exact_lines[ident].add(lid)

        if tree is None:
            continue

        # AST temporal scan once.
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            expr = ast.get_source_segment(source, node) or ""
            fn = fmap[node.lineno] if node.lineno < len(fmap) else ""
            tc, fc = context(expr, fn)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "shift":
                sv = ast_shift_value(node)
                idx.ast_findings.append(ASTFinding(rel, node.lineno, fn, "SHIFT", expr, sv, sv is not None and sv < 0, False, tc, fc))
            if isinstance(node.func, ast.Attribute) and node.func.attr == "rolling":
                centered = any(k.arg == "center" and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords)
                idx.ast_findings.append(ASTFinding(rel, node.lineno, fn, "ROLLING", expr, None, False, centered, tc, fc))

        # Regex scan over already-loaded lines.
        for no, raw in enumerate(lines, 1):
            txt = raw.strip(); low = txt.lower(); fn = fmap[no] if no < len(fmap) else ""
            tc, fc = context(txt, fn)
            if ".shift" in low:
                m = re.search(r"\.shift\s*\(\s*([-+]?\d+)", txt, re.I)
                sv = int(m.group(1)) if m else None
                neg = sv is not None and sv < 0
                f = Finding(rel, no, "NEGATIVE_SHIFT" if neg else "SHIFT", txt, fn, tc, fc, neg, neg, False)
                idx.finding_at[(rel, no)].append(len(idx.findings)); idx.findings.append(f)
            if ".rolling" in low:
                centered = bool(re.search(r"center\s*=\s*True", low))
                f = Finding(rel, no, "CENTERED_ROLLING" if centered else "ROLLING", txt, fn, tc, fc, False, False, centered)
                idx.finding_at[(rel, no)].append(len(idx.findings)); idx.findings.append(f)
            if ".diff" in low:
                f = Finding(rel, no, "DIFF", txt, fn, tc, fc)
                idx.finding_at[(rel, no)].append(len(idx.findings)); idx.findings.append(f)
            if re.search(r"\b(lead\s*\(|forward|future_|next_|tomorrow_|forecast)", low):
                if ".shift" not in low:
                    f = Finding(rel, no, "FUTURE_OR_FORWARD", txt, fn, tc, fc, True)
                    idx.finding_at[(rel, no)].append(len(idx.findings)); idx.findings.append(f)

    return idx


def classify_findings(findings: list[Finding]) -> None:
    for f in findings:
        if f.negative_shift:
            f.classification = "TARGET_FUTURE_LOGIC" if f.target_context else ("FEATURE_FUTURE_OPERATION" if f.feature_context else "FUTURE_OPERATION_REVIEW")
        elif f.centered_rolling:
            f.classification = "FEATURE_CENTERED_ROLLING" if f.feature_context else "CENTERED_ROLLING_REVIEW"
        elif f.future_or_forward:
            f.classification = "TARGET_FUTURE_LOGIC" if f.target_context else ("FEATURE_FUTURE_OPERATION" if f.feature_context else "FUTURE_OPERATION_REVIEW")
        else:
            f.classification = "TEMPORAL_OPERATION"


def family(feature: str) -> str:
    n = norm(feature)
    if "target" in n or n.startswith(("future_", "next_", "tomorrow_")):
        return "future_or_target"
    if any(w in n for w in HISTORICAL_WORDS):
        return "historical"
    if any(w in n for w in CURRENT_WORDS) or re.search(r"(^|_)is_(empty|full|near_full|low_availability|critical_availability|capacity_exceeded)($|_)", n):
        return "current_state"
    if any(w in n for w in TEMPORAL_WORDS) or re.search(r"(^|_)(year|month|week|day|hour|minute|quarter|is_weekend|holiday)($|_)", n):
        return "temporal_calendar"
    return "other"


def csv_lists(x: Any) -> list[str]:
    if x is None or str(x).strip().lower() in ("", "nan", "none", "null"):
        return []
    s = str(x).strip()
    try:
        y = json.loads(s)
        if isinstance(y, list):
            return sorted({str(v) for v in y if str(v).strip()})
    except Exception:
        pass
    for sep in ("|", ";"):
        if sep in s:
            return sorted({v.strip() for v in s.split(sep) if v.strip()})
    return [s]


def lineage_index(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    if df.empty:
        return {}
    col = next((c for c in ("feature", "feature_name", "name") if c in df.columns), None)
    if not col:
        return {}
    return {str(r[col]).strip(): r.to_dict() for _, r in df.iterrows() if str(r[col]).strip()}


def evidence(feature: str, idx: Index, lin: dict[str, dict[str, Any]]) -> dict[str, Any]:
    n = norm(feature)
    ids = set(idx.exact_lines.get(n, set()))
    if not ids:
        ft = {t for t in tokens(feature) if len(t) >= 4}
        hits: Counter[int] = Counter()
        for t in ft:
            for lid in idx.token_lines.get(t, set()):
                hits[lid] += 1
        need = 1 if len(ft) <= 1 else min(2, len(ft))
        ids = {lid for lid, count in hits.items() if count >= need}

    files, funcs, exprs, cols, ops = set(), set(), [], set(), set()
    findings: list[Finding] = []
    ft = {t for t in tokens(feature) if len(t) >= 4}
    for lid in ids:
        line = idx.lines[lid]
        # final guard against weak token matches
        if n not in norm(line.text) and len(ft & set(line.tokens)) < (1 if len(ft) <= 1 else min(2, len(ft))):
            continue
        files.add(line.file)
        if line.function: funcs.add(line.function)
        if line.text: exprs.append(line.text)
        for c in re.findall(r"['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]", line.text):
            if c != feature: cols.add(c)
        for fid in idx.finding_at.get((line.file, line.number), []):
            f = idx.findings[fid]; findings.append(f); ops.add(f.finding_type)

    r = lin.get(feature)
    if r:
        for key in ("source_files", "source_file", "files"):
            if key in r: files.update(csv_lists(r[key]))
        for key in ("source_functions", "source_function", "functions"):
            if key in r: funcs.update(csv_lists(r[key]))
        for key in ("source_expressions", "source_expression", "expressions"):
            if key in r: exprs.extend(csv_lists(r[key]))
        for key in ("source_columns", "source_column", "columns"):
            if key in r: cols.update(csv_lists(r[key]))
        for key in ("temporal_operations", "temporal_operation", "operations"):
            if key in r: ops.update(csv_lists(r[key]))

    return {
        "source_files": sorted(files),
        "source_functions": sorted(funcs),
        "source_expressions": sorted(set(exprs))[:25],
        "source_columns": sorted(cols)[:50],
        "temporal_operations": sorted(ops),
        "findings": findings,
    }


def contract(feature: str, idx: Index, lin: dict[str, dict[str, Any]]) -> Contract:
    fam = family(feature); e = evidence(feature, idx, lin); fs = e["findings"]
    neg = any(f.negative_shift for f in fs)
    centered = any(f.centered_rolling for f in fs)
    forward = any(f.future_or_forward and f.finding_type != "NEGATIVE_SHIFT" for f in fs)
    feature_future = any(f.future_or_forward and f.feature_context and not f.target_context for f in fs)
    target_only = bool(fs) and all(f.target_context and not f.feature_context for f in fs)
    leak = (neg or centered or forward or feature_future) and not target_only
    common = dict(feature=feature, family=fam, source_evidence=bool(e["source_files"]), source_files=e["source_files"], source_functions=e["source_functions"], source_expressions=e["source_expressions"], source_columns=e["source_columns"], temporal_operations=e["temporal_operations"], future_operation_detected=bool(neg or centered or forward), negative_shift_detected=neg, centered_rolling_detected=centered, forward_operation_detected=forward, target_context_only=target_only, feature_context_future=feature_future, potential_leakage=leak)

    if leak:
        return Contract(verdict="POTENTIAL_LEAKAGE", latest_information_boundary="UNKNOWN / FUTURE OPERATION DETECTED", availability_basis="Feature-level future operation detected.", causal_evidence="Indexed source evidence indicates information after T may contribute to this feature.", causal_review_required=True, confidence="HIGH", notes=["Requires immediate engineering investigation."], **common)
    if target_only:
        return Contract(verdict="TARGET_CONSTRUCTION_ONLY", latest_information_boundary="TARGET CONSTRUCTION / NOT FEATURE INPUT", availability_basis="Future operation appears confined to target-generation context.", causal_evidence="Future-oriented operation is confined to target construction rather than registered feature construction.", confidence="HIGH", notes=["Target-generation future logic is not automatically treated as feature leakage."], **common)
    if fam == "historical":
        return Contract(verdict="PRODUCTION_SAFE_HISTORICAL", latest_information_boundary="AT_OR_BEFORE_T", availability_basis="Historical/lag/rolling feature; no feature-level future operation detected.", causal_evidence="Feature naming and source evidence indicate historical semantics.", causal_review_required=True, confidence="HIGH" if e["source_files"] else "LOW", notes=["Formal source timestamp verification is still recommended before production approval."], **common)
    if fam == "current_state":
        return Contract(verdict="PRODUCTION_SAFE_REALTIME_CONTRACT", latest_information_boundary="T", availability_basis="Current-state feature may be available at prediction timestamp T.", causal_evidence="Current-state classification with no feature-level future operation detected.", realtime_contract_required=True, causal_review_required=True, confidence="HIGH" if e["source_files"] else "MEDIUM", notes=["Production requires an explicit realtime source and freshness SLA.", "Training availability alone does not establish production availability."], **common)
    if fam == "temporal_calendar":
        return Contract(verdict="PRODUCTION_SAFE", latest_information_boundary="T", availability_basis="Calendar/time feature derived from T or known calendar state.", causal_evidence="Temporal/calendar features are deterministic at T when derived solely from T.", confidence="HIGH" if e["source_files"] else "MEDIUM", **common)
    return Contract(verdict="REQUIRES_CAUSAL_REVIEW", latest_information_boundary="UNKNOWN", availability_basis="Insufficient static evidence for automatic causal approval.", causal_evidence="Feature family could not be established as deterministic calendar, current-state, or historical causal.", causal_review_required=True, confidence="MEDIUM" if e["source_files"] else "LOW", notes=["Manual source and timestamp verification required."], **common)


def summary(contracts: list[Contract]) -> dict[str, Any]:
    fc = Counter(c.family for c in contracts); vc = Counter(c.verdict for c in contracts)
    return {
        "features_audited": len(contracts), "family_counts": dict(fc), "verdict_counts": dict(vc),
        "potential_leakage_features": sum(c.potential_leakage for c in contracts),
        "negative_shift_features": sum(c.negative_shift_detected for c in contracts),
        "centered_rolling_features": sum(c.centered_rolling_detected for c in contracts),
        "forward_operation_features": sum(c.forward_operation_detected for c in contracts),
        "realtime_contract_features": sum(c.realtime_contract_required for c in contracts),
        "causal_review_features": sum(c.causal_review_required for c in contracts),
        "source_evidence_features": sum(c.source_evidence for c in contracts),
        "features_without_source_evidence": sum(not c.source_evidence for c in contracts),
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader()
        for row in rows:
            out = {}
            for k in fields:
                v = row.get(k, "")
                out[k] = json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict, tuple, set)) else v
            w.writerow(out)


def persist(p: dict[str, Path], manifest: dict[str, Any], contracts: list[Contract], idx: Index, summ: dict[str, Any], verdict: str, reasons: list[str]) -> None:
    section("PERSISTING CAUSAL VERIFICATION RESULTS")
    out = p["out"]; out.mkdir(parents=True, exist_ok=True)
    features = [asdict(c) for c in contracts]; source = [asdict(x) for x in idx.findings]; ast_rows = [asdict(x) for x in idx.ast_findings]
    feature_fields = list(features[0].keys()) if features else list(asdict(Contract("", "", "", False)).keys())
    write_csv(out / OUT_FEATURES, features, feature_fields)
    source_fields = list(asdict(Finding("", 0, "", "")).keys())
    write_csv(out / OUT_SOURCE, source, source_fields)
    ast_fields = list(asdict(ASTFinding("", 0, "", "", "")).keys())
    write_csv(out / OUT_AST, ast_rows, ast_fields)
    rows = []
    for k, v in summ.items():
        if isinstance(v, dict):
            for a, b in v.items(): rows.append({"category": k, "metric": a, "value": b})
        else: rows.append({"category": "overall", "metric": k, "value": v})
    rows += [{"category": "overall", "metric": "overall_verdict", "value": verdict}, {"category": "overall", "metric": "generated_at", "value": datetime.now(timezone.utc).isoformat()}]
    write_csv(out / OUT_SUMMARY, rows, ["category", "metric", "value"])
    report = {"audit": {"name": "Birmingham XGBoost Feature Causal Verification V2 Optimized", "target": TARGET, "generated_at": datetime.now(timezone.utc).isoformat(), "production_contract": {"prediction_timestamp": "T", "forecast_horizon_minutes": FORECAST_MINUTES, "feature_information": "available_at_or_before_T"}, "policy": {"test_loaded": False, "xgboost_trained": False, "feature_pipeline_rebuilt": False, "persisted_datasets_modified": False}, "performance": {"source_files_read_once": True, "source_files_parsed_once": True, "repeated_feature_source_scans": False}}, "manifest_summary": {"registered_feature_count": len(manifest.get("feature_columns", []))}, "summary": summ, "overall_verdict": verdict, "verdict_reasons": reasons, "feature_contracts": features, "source_findings": source, "ast_findings": ast_rows}
    jp = out / OUT_JSON; jp.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    kv("Output directory", out); kv("JSON report", jp); kv("CSV feature contract", out / OUT_FEATURES); kv("CSV source findings", out / OUT_SOURCE); kv("CSV summary", out / OUT_SUMMARY); kv("CSV AST findings", out / OUT_AST)


def main() -> int:
    header("SMARTPARK AI - BIRMINGHAM XGBOOST FEATURE CAUSAL VERIFICATION AUDIT V2 OPTIMIZED")
    print(f"\nTarget:\n  {TARGET}\n\nProduction prediction contract:\n  Prediction timestamp = T\n  Forecast horizon     = T + 30 minutes\n  Feature information  = available at or before T")
    print("\nAudit policy:\n  Verify each registered feature individually\n  Use existing feature-lineage artifacts\n  Inspect actual ML source code\n  Parse each source file once\n  Build an in-memory source/function/temporal index\n  Distinguish target-generation future logic from feature-generation future logic\n  Apply historical-before-current classification precedence\n  Do NOT load test.parquet\n  Do NOT train XGBoost\n  Do NOT rebuild the feature pipeline\n  Do NOT modify persisted datasets")
    root = repo_root(); p = paths(root)
    try:
        validate_files(p); manifest = load_manifest(p["manifest"]); features = [str(x) for x in manifest["feature_columns"]]
        train, val = load_data(p); validate_registry(train, val, features); validate_target(train, val)
        section("LOADING EXISTING FEATURE-LINEAGE ARTIFACTS")
        lf = pd.read_csv(p["lineage_features"]); ls = pd.read_csv(p["lineage_source"])
        kv("Lineage feature rows", len(lf)); kv("Lineage source findings", len(ls)); lin = lineage_index(lf)
        idx = build_source_index(p["ml"]); classify_findings(idx.findings)
        sc = Counter(x.finding_type for x in idx.findings)
        kv("Indexed source lines", len(idx.lines)); kv("Source temporal findings", len(idx.findings))
        for k, v in sorted(sc.items()): kv(f"  {k}", v, 40)
        print("\nAST temporal cross-check:"); kv("AST temporal findings", len(idx.ast_findings)); kv("AST shift findings", sum(x.operation == "SHIFT" for x in idx.ast_findings)); kv("AST rolling findings", sum(x.operation == "ROLLING" for x in idx.ast_findings)); kv("AST negative shifts", sum(x.negative_shift for x in idx.ast_findings)); kv("AST centered rolling", sum(x.centered_rolling for x in idx.ast_findings))
        section("BUILDING FEATURE-LEVEL CAUSAL CONTRACT")
        contracts = []
        for i, f in enumerate(features, 1):
            contracts.append(contract(f, idx, lin))
            if i % 50 == 0 or i == len(features): print(f"  Contract progress: {i}/{len(features)}")
        summ = summary(contracts)
        section("FEATURE CAUSAL VERIFICATION SUMMARY"); kv("Features audited", len(contracts)); kv("Features with source evidence", summ["source_evidence_features"]); kv("Features without source evidence", summ["features_without_source_evidence"])
        print("\nFeature families:"); [kv(f"  {k}", v, 40) for k, v in sorted(summ["family_counts"].items())]
        print("\nCausal verdicts:"); [kv(f"  {k}", v, 40) for k, v in sorted(summ["verdict_counts"].items())]
        for k in ("negative_shift_features", "centered_rolling_features", "forward_operation_features", "potential_leakage_features", "realtime_contract_features", "causal_review_features"): kv(k.replace("_", " ").title(), summ[k])
        checks = [("Training dataset non-empty", len(train) > 0), ("Validation dataset non-empty", len(val) > 0), ("Expected feature count", len(features) == EXPECTED_FEATURE_COUNT), ("Causal contract row count equals feature count", len(contracts) == len(features)), ("No duplicate registered features", len(features) == len(set(features))), ("No duplicate audited features", len(contracts) == len({c.feature for c in contracts})), ("All audited features present", {c.feature for c in contracts} == set(features)), ("Target not included as registered feature", TARGET not in set(features))]
        section("FINAL ASSERTIONS")
        for label, ok in checks: kv(label, "PASS" if ok else "FAIL");
        if not all(x[1] for x in checks): raise RuntimeError("One or more final assertions failed")
        review = [c for c in contracts if c.verdict in ("REQUIRES_CAUSAL_REVIEW", "POTENTIAL_LEAKAGE")]
        section("FEATURES REQUIRING REVIEW")
        if review:
            for v in sorted(set(c.verdict for c in review)):
                group = sorted(c.feature for c in review if c.verdict == v); print(f"\n{v}: {len(group)}"); [print(f"  - {x}") for x in group]
        else: print("No feature requires manual causal review.")
        leakage = [c for c in contracts if c.potential_leakage]
        realtime = [c for c in contracts if c.realtime_contract_required]
        causal_review = [c for c in contracts if c.causal_review_required]
        if leakage: verdict, reasons = "FAIL_POTENTIAL_FEATURE_LEAKAGE", [f"{len(leakage)} feature(s) contain feature-level future-oriented operations."]
        else:
            reasons = []
            if realtime: reasons.append(f"{len(realtime)} current-state feature(s) require a production realtime source/freshness contract.")
            if causal_review: reasons.append(f"{len(causal_review)} feature(s) remain conditional because static analysis does not formally prove their causal cutoff.")
            verdict = "PASS_WITH_CAUSAL_REVIEW" if reasons else "PASS_PRODUCTION_CAUSALITY_VERIFIED"
        section("FINAL FEATURE CAUSAL VERIFICATION RESULT"); kv("Features audited", len(contracts)); kv("Historical features", summ["family_counts"].get("historical", 0)); kv("Current-state features", summ["family_counts"].get("current_state", 0)); kv("Temporal/calendar features", summ["family_counts"].get("temporal_calendar", 0)); kv("Other features", summ["family_counts"].get("other", 0)); kv("Potential leakage features", summ["potential_leakage_features"]); kv("Features requiring causal review", summ["causal_review_features"]); print(f"\nPRODUCTION FEATURE CAUSAL VERDICT : {verdict}\n\nVerdict reasons:"); [print(f"  - {x}") for x in reasons]
        persist(p, manifest, contracts, idx, summ, verdict, reasons)
        header("BIRMINGHAM FEATURE CAUSAL VERIFICATION AUDIT V2 OPTIMIZED COMPLETED"); print("No feature was automatically confirmed as future leakage." if not leakage else "Potential feature-level future leakage was detected."); print("\nTest dataset used:       NO\nXGBoost training:        NO\nFeature pipeline rebuilt: NO\nPersisted datasets modified: NO\n\nOptimized feature causal verification is ready for engineering review.")
        return 0
    except Exception as exc:
        header("BIRMINGHAM FEATURE CAUSAL VERIFICATION AUDIT V2 OPTIMIZED FAILED"); print(f"ERROR: {type(exc).__name__}: {exc}\n\nNO persisted datasets were modified.\nTest dataset was NOT loaded.\nNo XGBoost model was trained."); return 1


if __name__ == "__main__":
    sys.exit(main())
