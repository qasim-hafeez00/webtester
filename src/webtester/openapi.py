"""Declared API contracts (v5 plan O7, rule R57e; D61): when the app serves an OpenAPI or Swagger document, or
answers GraphQL introspection, the JSON responses the network timeline captured are checked against what is
declared for their operation, and the operations the run called are counted against the declared ones
(endpoint coverage, evaluation group 4).

R57e (DB11, T2): a response field whose value breaks its declared type or enum, or a required field missing.
OpenAPI: only 2xx JSON responses of operations whose path template and method match are checked; `$ref`,
`allOf` and `nullable` are followed, at most MAX_DEPTH levels deep, and at most MAX_ISSUES per response. A
schema the module cannot read (`oneOf`, `anyOf`, external refs) is skipped, never guessed.
GraphQL: the query the page sent is parsed (fields, aliases, arguments skipped, named fragments followed;
inline fragments and union members are skipped) and each selected field of `data` is checked against its
declared type: scalars, enums, lists, and null in a non-null field. Responses with `errors` are left to R57.
"""

from __future__ import annotations

import json
import re

SPEC_PATHS = ("/openapi.json", "/swagger.json", "/v3/api-docs", "/api-docs", "/api/openapi.json",
              "/api/swagger.json", "/api/docs/openapi.json", "/api-docs.json")
MAX_DEPTH = 4
MAX_ISSUES = 3
GRAPHQL_PATHS = ("/graphql", "/api/graphql", "/graphql/", "/query")
TIERS = {"R57e": "T2"}
_TYPES = {"string": (str,), "integer": (int,), "number": (int, float), "boolean": (bool,), "array": (list,),
          "object": (dict,)}


class Spec:
    def __init__(self, doc: dict):
        self.doc = doc
        base = ""
        if doc.get("basePath"):  # Swagger 2
            base = doc["basePath"].rstrip("/")
        elif doc.get("servers"):
            m = re.match(r"^(?:https?://[^/]+)?(/.*)?$", str(doc["servers"][0].get("url", "")))
            base = (m.group(1) or "").rstrip("/") if m else ""
        self.ops = []  # (method, compiled path, template, response schema or None)
        for tpl, item in (doc.get("paths") or {}).items():
            rx = re.compile("^" + re.escape(base + tpl).replace(r"\{", "{").replace(r"\}", "}") + "/?$")
            rx = re.compile(re.sub(r"\{[^/}]+\}", r"[^/]+", rx.pattern))
            for method, op in (item or {}).items():
                if method.lower() not in ("get", "post", "put", "patch", "delete") or not isinstance(op, dict):
                    continue
                self.ops.append((method.upper(), rx, f"{method.upper()} {tpl}", self._response_schema(op)))

    def _response_schema(self, op: dict) -> dict | None:
        for code in ("200", "201", 200, 201):
            r = (op.get("responses") or {}).get(code)
            if not r:
                continue
            r = self.resolve(r)
            if "schema" in r:  # Swagger 2
                return r["schema"]
            content = r.get("content") or {}
            for ctype, c in content.items():
                if "json" in ctype and isinstance(c, dict) and c.get("schema"):
                    return c["schema"]
        return None

    def resolve(self, node: dict, depth: int = 0) -> dict:
        while isinstance(node, dict) and "$ref" in node and depth < 10:
            ref = node["$ref"]
            if not ref.startswith("#/"):
                return {}
            cur = self.doc
            for part in ref[2:].split("/"):
                cur = cur.get(part.replace("~1", "/").replace("~0", "~"), {}) if isinstance(cur, dict) else {}
            node, depth = cur, depth + 1
        return node if isinstance(node, dict) else {}

    def match(self, method: str, path: str):
        for m, rx, tpl, schema in self.ops:
            if m == method and rx.match(path):
                return tpl, schema
        return None, None

    def issues(self, value, schema: dict | None, where: str = "", depth: int = 0) -> list[str]:
        if schema is None or depth > MAX_DEPTH:
            return []
        s = self.resolve(schema)
        if not s or "oneOf" in s or "anyOf" in s:
            return []
        if "allOf" in s:
            merged = {"type": "object", "properties": {}, "required": []}
            for part in s["allOf"]:
                p = self.resolve(part)
                merged["properties"].update(p.get("properties") or {})
                merged["required"] += p.get("required") or []
            s = merged
        if value is None:
            return [] if s.get("nullable") or s.get("x-nullable") or not s.get("type") else \
                [f"{where or 'the body'} is null, declared {s.get('type')}"]
        out = []
        t = s.get("type")
        if t in _TYPES and not (isinstance(value, _TYPES[t]) and not (t in ("integer", "number") and isinstance(value, bool))):
            return [f"{where or 'the body'} is {type(value).__name__} {json.dumps(value)[:40]}, declared {t}"]
        if "enum" in s and value not in s["enum"]:
            out.append(f"{where or 'the value'} is {json.dumps(value)[:40]}, not one of {s['enum'][:6]}")
        if isinstance(value, dict):
            props = s.get("properties") or {}
            for r in s.get("required") or []:
                if r not in value:
                    out.append(f"{where + '.' if where else ''}{r} is required but missing")
            for k, v in value.items():
                if k in props:
                    out += self.issues(v, props[k], f"{where + '.' if where else ''}{k}", depth + 1)
                if len(out) >= MAX_ISSUES:
                    break
        elif isinstance(value, list) and s.get("items"):
            for i, v in enumerate(value[:20]):
                out += self.issues(v, s["items"], f"{where}[{i}]", depth + 1)
                if len(out) >= MAX_ISSUES:
                    break
        return out[:MAX_ISSUES]


def rule_contract(net: list[dict], spec: Spec | None, called: set | None = None) -> list:
    """R57e over one step's network timeline; `called` collects the operation templates seen (coverage)."""
    from .consistency import Violation

    if spec is None:
        return []
    out = []
    for r in net:
        if isinstance(spec, GraphQLSchema):
            if r.get("path", "").rstrip("/") not in {p.rstrip("/") for p in GRAPHQL_PATHS} | {spec_path_of(spec)}:
                continue
            ops, issues = spec.check(r)
            if called is not None:
                called.update(ops)
            if issues:
                tpl = ops[0] if ops else "graphql"
                out.append(Violation("R57e", f"{tpl}|{issues[0].split(' ')[0]}", f"{tpl}: {issues[0]} (declared in the "
                                     "app's GraphQL schema)", f"{r.get('method')} {r.get('path')} -> {r.get('status')}"))
            continue
        tpl, schema = spec.match(r.get("method", ""), r.get("path", ""))
        if tpl is None:
            continue
        if called is not None:
            called.add(tpl)
        if not (200 <= r.get("status", 0) < 300) or "body" not in r:
            continue
        for issue in spec.issues(r["body"], schema):
            out.append(Violation("R57e", f"{tpl}|{issue.split(' ')[0]}", f"{tpl}: {issue} (declared in the app's API "
                                 "document)", f"{r.get('method')} {r.get('path')} -> {r.get('status')}"))
            break
    return out


async def load_spec(session, base_url: str) -> tuple[Spec | None, str]:
    """The app's API document, if it serves one at a usual path (fetched once per run)."""
    for p in SPEC_PATHS:
        try:
            r = await session.context.request.get(base_url.rstrip("/") + p, timeout=6000)
            if not r.ok:
                continue
            doc = json.loads(await r.text())
        except Exception:  # noqa: BLE001 - most apps serve none
            continue
        if isinstance(doc, dict) and (doc.get("openapi") or doc.get("swagger")) and doc.get("paths"):
            return Spec(doc), p
    for p in GRAPHQL_PATHS:  # D61: GraphQL introspection (apps that disable it answer an error: none is read)
        try:
            r = await session.context.request.post(base_url.rstrip("/") + p, data=json.dumps({"query": INTROSPECTION}),
                                                   headers={"Content-Type": "application/json"}, timeout=6000)
            if not r.ok:
                continue
            doc = json.loads(await r.text())
        except Exception:  # noqa: BLE001
            continue
        sch = ((doc or {}).get("data") or {}).get("__schema") if isinstance(doc, dict) else None
        if isinstance(sch, dict) and sch.get("types"):
            g = GraphQLSchema(sch)
            g.path = p
            return g, p
    return None, ""


def spec_path_of(spec) -> str:
    return getattr(spec, "path", "").rstrip("/")


# ---------------------------------------------------------------------------- GraphQL (D61)
INTROSPECTION = ("query{__schema{queryType{name} mutationType{name} types{kind name enumValues{name} "
                 "fields{name type{...T}}}}} fragment T on __Type{kind name ofType{kind name ofType{kind name "
                 "ofType{kind name ofType{kind name}}}}}")
_GQL_SCALARS = {"Int": (int,), "Float": (int, float), "String": (str,), "Boolean": (bool,), "ID": (str, int)}
_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|#[^\n]*|\.\.\.|[A-Za-z_][A-Za-z0-9_]*|[{}():@$!=\[\],]|-?\d+(?:\.\d+)?')


def _tokens(q: str) -> list[str]:
    return [x for x in _TOKEN.findall(q or "") if not x.startswith("#")]  # comments dropped, strings kept whole


def _skip_parens(t: list[str], i: int) -> int:
    depth = 0
    while i < len(t):
        depth += t[i] == "("
        depth -= t[i] == ")"
        i += 1
        if depth == 0:
            return i
    return i


def _selection(t: list[str], i: int) -> tuple[list, int]:
    """Parse a `{ ... }` selection set at t[i] == '{'. Returns ([(key, field, sub | None, optional)], next i);
    named fragment spreads come back as ('...', name, None, False), inline fragments are skipped."""
    out, i = [], i + 1
    while i < len(t) and t[i] != "}":
        if t[i] == "...":
            if i + 1 < len(t) and t[i + 1] not in ("on", "{", "@"):
                out.append(("...", t[i + 1], None, False))
                i += 2
                continue
            i += 1
            while i < len(t) and t[i] != "{":  # '... on Type' or '... @include(...)': skipped, never guessed
                i = _skip_parens(t, i) if t[i] == "(" else i + 1
            if i < len(t):
                _, i = _selection(t, i)
            continue
        key = name = t[i]
        i += 1
        if i < len(t) and t[i] == ":":
            name, i = t[i + 1], i + 2
        if i < len(t) and t[i] == "(":
            i = _skip_parens(t, i)
        optional = False
        while i < len(t) and t[i] == "@":  # a directive may leave the field out
            optional, i = True, i + 2
            if i < len(t) and t[i] == "(":
                i = _skip_parens(t, i)
        sub_ = None
        if i < len(t) and t[i] == "{":
            sub_, i = _selection(t, i)
        out.append((key, name, sub_, optional))
    return out, i + 1


def parse_operation(q: str) -> tuple[str, list, dict] | None:
    """('query' | 'mutation' | 'subscription', root selection, named fragments) of the first operation, or None."""
    t = _tokens(q)
    frags, op, i = {}, None, 0
    while i < len(t):
        if t[i] == "fragment" and i + 4 < len(t):
            name, j = t[i + 1], i + 2
            while j < len(t) and t[j] != "{":
                j += 1
            frags[name], i = _selection(t, j)
            continue
        if op is None and t[i] in ("query", "mutation", "subscription", "{"):
            kind = "query" if t[i] == "{" else t[i]
            j = i
            while j < len(t) and t[j] != "{":
                j = _skip_parens(t, j) if t[j] == "(" else j + 1
            if j >= len(t):
                return None
            sel, i = _selection(t, j)
            op = (kind, sel)
            continue
        i += 1
    return (op[0], op[1], frags) if op else None


class GraphQLSchema:
    def __init__(self, schema: dict):
        self.types = {x["name"]: x for x in schema.get("types") or [] if x.get("name")}
        self.roots = {"query": (schema.get("queryType") or {}).get("name"),
                      "mutation": (schema.get("mutationType") or {}).get("name")}
        root_fields = [f"{k} {f['name']}" for k, n in self.roots.items() if n for f in self.types.get(n, {}).get("fields") or []]
        self.ops = root_fields  # endpoint coverage: one operation per root field

    def _field_type(self, type_name: str, field: str) -> dict | None:
        return next((f["type"] for f in self.types.get(type_name, {}).get("fields") or [] if f["name"] == field), None)

    def _value(self, v, tref: dict, sel, frags, where: str, depth: int) -> list[str]:
        if depth > MAX_DEPTH + 4 or not tref:
            return []
        if tref.get("kind") == "NON_NULL":
            return [f"{where} is null, declared non-null"] if v is None else \
                self._value(v, tref.get("ofType") or {}, sel, frags, where, depth)
        if v is None:
            return []
        kind, name = tref.get("kind"), tref.get("name")
        if kind == "LIST":
            if not isinstance(v, list):
                return [f"{where} is {type(v).__name__}, declared a list"]
            out = []
            for k, x in enumerate(v[:20]):
                out += self._value(x, tref.get("ofType") or {}, sel, frags, f"{where}[{k}]", depth + 1)
                if len(out) >= MAX_ISSUES:
                    break
            return out
        if kind == "SCALAR" and name in _GQL_SCALARS:
            ok = isinstance(v, _GQL_SCALARS[name]) and not (name != "Boolean" and isinstance(v, bool))
            return [] if ok else [f"{where} is {type(v).__name__} {json.dumps(v)[:40]}, declared {name}"]
        if kind == "ENUM":
            allowed = [e["name"] for e in self.types.get(name, {}).get("enumValues") or []]
            return [] if not allowed or v in allowed else [f"{where} is {json.dumps(v)[:40]}, not one of {allowed[:6]}"]
        if kind in ("OBJECT", "INTERFACE") and sel is not None:
            if not isinstance(v, dict):
                return [f"{where} is {type(v).__name__}, declared {name}"]
            return self._object(v, name, sel, frags, where, depth + 1)
        return []  # custom scalars, unions: not checked

    def _object(self, data: dict, type_name: str, sel: list, frags: dict, where: str, depth: int) -> list[str]:
        out = []
        for key, field, sub_, optional in sel:
            if key == "...":
                out += self._object(data, type_name, frags.get(field) or [], frags, where, depth) if field in frags else []
                continue
            if field.startswith("__"):
                continue
            tref = self._field_type(type_name, field)
            path = f"{where}.{key}" if where else key
            if tref is None:
                continue  # not in the schema read (an extension, or a type the introspection did not list)
            if key not in data:
                if not optional:
                    out.append(f"{path} was selected but is missing")
                continue
            out += self._value(data[key], tref, sub_, frags, path, depth)
            if len(out) >= MAX_ISSUES:
                break
        return out[:MAX_ISSUES]

    def check(self, rec: dict) -> tuple[list[str], list[str]]:
        """(root operations called, issues) for one network record of a GraphQL request."""
        q = None
        if rec.get("sent"):
            try:
                body = json.loads(rec["sent"])
                q = body.get("query") if isinstance(body, dict) else None
            except ValueError:
                q = None
        elif "query=" in (rec.get("url") or ""):
            from urllib.parse import parse_qs, urlsplit

            q = (parse_qs(urlsplit(rec["url"]).query).get("query") or [None])[0]
        op = parse_operation(q) if q else None
        if op is None or not self.roots.get(op[0]):
            return [], []
        kind, sel, frags = op
        called = [f"{kind} {name}" for key, name, _, _ in sel if key != "..."]
        body = rec.get("body")
        if not (200 <= rec.get("status", 0) < 300) or not isinstance(body, dict) or body.get("errors") or \
                not isinstance(body.get("data"), dict):
            return called, []
        return called, self._object(body["data"], self.roots[kind], sel, frags, "", 0)
