"""Contract-First Phase D — barrier BINDING (Option A: per-slice DI module + binder
composes).

At the wave barrier, concurrent slices have each implemented their real impl in their
OWN ``*Module.cs`` file (file-disjoint) and registered it via a marked DI extension;
the Phase-1 materializer registered placeholder STUB impls the same way. This module
composes the final wiring: prefer each interface's REAL module over its STUB module,
drop the superseded stub modules, and regenerate the composition aggregator to call
exactly the chosen modules. The core here is PURE (parse / plan / render) and unit
tested; the orchestrator applies the result to disk and runs a real ``dotnet build``
to prove the assembly, escalating no-abort on any conflict or build failure.

Convention (emitted by the stub materializer + each engineer slice):

    // @contract-module interface=<IName> impl=<ClassName> kind=<stub|real>
    public static class <X>Module
    {
        public static IServiceCollection Add<X>Module(this IServiceCollection services)
            => services.AddScoped<IName, ClassName>();
    }

and ONE aggregator file with a replaceable region the binder rewrites:

    public static IServiceCollection AddFeatureModules(this IServiceCollection services)
    {
        // @contract-aggregator:begin
        services.Add<X>Module();
        // @contract-aggregator:end
        return services;
    }
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_MODULE_RE = re.compile(
    r"//\s*@contract-module\s+interface=(?P<iface>\S+)\s+impl=(?P<impl>\S+)\s+kind=(?P<kind>stub|real)",
    re.IGNORECASE)
_METHOD_RE = re.compile(
    r"public\s+static\s+IServiceCollection\s+(?P<m>Add\w+)\s*\(\s*this\s+IServiceCollection",
    re.IGNORECASE)

AGG_BEGIN = "// @contract-aggregator:begin"
AGG_END = "// @contract-aggregator:end"


@dataclass(frozen=True)
class Module:
    path: str
    iface: str
    impl: str
    kind: str               # "stub" | "real"
    method: str | None      # the Add*Module extension method name, if parseable


def parse_modules(files: dict) -> list:
    """PURE. Given ``{path: text}``, return the contract DI modules found (those
    carrying the ``@contract-module`` marker). Files without the marker are ignored.
    Deterministic order: sorted by path."""
    mods = []
    for path in sorted(files):
        text = files[path] or ""
        m = _MODULE_RE.search(text)
        if not m:
            continue
        meth = _METHOD_RE.search(text)
        mods.append(Module(path=path, iface=m.group("iface"), impl=m.group("impl"),
                           kind=m.group("kind").lower(),
                           method=(meth.group("m") if meth else None)))
    return mods


@dataclass(frozen=True)
class BindPlan:
    chosen: tuple           # one Module per interface (real preferred over stub)
    drop_paths: tuple       # stub module files superseded by a real impl
    method_calls: tuple     # ordered extension methods the aggregator must call
    conflicts: tuple        # human-readable conflict reasons (empty ⇒ clean)


def plan_binding(modules) -> BindPlan:
    """PURE. Per interface, choose the REAL module (fall back to its stub if no real
    impl was built yet), list the stub files a real impl supersedes (to drop), and
    the ordered, de-duplicated extension methods the aggregator should call. Flags
    conflicts: an interface with >1 real impl, or a chosen module with no parseable
    ``Add*Module`` extension method."""
    by_iface: dict = {}
    for mod in modules:
        by_iface.setdefault(mod.iface, []).append(mod)
    chosen, drop, conflicts = [], [], []
    for iface in sorted(by_iface):
        group = by_iface[iface]
        reals = [m for m in group if m.kind == "real"]
        stubs = [m for m in group if m.kind == "stub"]
        if len(reals) > 1:
            conflicts.append(
                f"interface {iface} has {len(reals)} real impls: "
                + ", ".join(sorted(m.impl for m in reals)))
            continue
        pick = reals[0] if reals else (stubs[0] if stubs else None)
        if pick is None:
            continue
        chosen.append(pick)
        if reals:                       # a real impl supersedes every stub module
            drop.extend(s.path for s in stubs)
        if pick.method is None:
            conflicts.append(
                f"module {pick.path} ({iface}) has no Add*Module extension method")
    method_calls = []
    for m in chosen:
        if m.method and m.method not in method_calls:
            method_calls.append(m.method)
    return BindPlan(chosen=tuple(chosen), drop_paths=tuple(sorted(set(drop))),
                    method_calls=tuple(method_calls), conflicts=tuple(conflicts))


def render_aggregator(text: str, method_calls, indent: str = "        ") -> str:
    """PURE. Replace the region between ``@contract-aggregator:begin`` and
    ``...:end`` in the aggregator file with one ``services.<Method>();`` call per
    chosen module (in order). Markers and everything outside them are preserved.
    Raises ``ValueError`` if the markers are absent or out of order."""
    bi = text.find(AGG_BEGIN)
    ei = text.find(AGG_END)
    if bi == -1 or ei == -1 or ei < bi:
        raise ValueError("aggregator markers not found or out of order")
    begin_line_end = text.find("\n", bi)
    if begin_line_end == -1:
        raise ValueError("aggregator begin marker malformed (no newline after it)")
    body = "".join(f"{indent}services.{mc}();\n" for mc in method_calls)
    end_line_start = text.rfind("\n", 0, ei) + 1
    return text[:begin_line_end + 1] + body + text[end_line_start:]


def compute_binding(files: dict) -> dict:
    """PURE end-to-end planner the orchestrator applies. Given ``{path: text}`` for
    the feature's changed C# files, return a binding result:

      ok                  : bool  — clean (no conflicts, aggregator found+rendered)
      conflicts           : list[str]
      drop_paths          : list[str]  — stub module files to delete
      aggregator_path     : str | None
      new_aggregator_text : str | None — rewritten aggregator content
      method_calls        : list[str]
      chosen              : list[(iface, impl, kind)]

    The orchestrator deletes ``drop_paths``, writes ``new_aggregator_text`` to
    ``aggregator_path``, commits, and runs ``dotnet build``; any conflict or build
    failure drives the no-abort escalation (siblings stay merged)."""
    mods = parse_modules(files)
    plan = plan_binding(mods)
    agg_paths = sorted(p for p, t in files.items() if t and AGG_BEGIN in t)
    conflicts = list(plan.conflicts)
    agg_path = None
    new_agg = None
    if not mods:
        conflicts.append("no @contract-module files found among changed C# files")
    if len(agg_paths) == 0:
        conflicts.append("no @contract-aggregator file found")
    elif len(agg_paths) > 1:
        conflicts.append("multiple @contract-aggregator files: " + ", ".join(agg_paths))
    else:
        agg_path = agg_paths[0]
        try:
            new_agg = render_aggregator(files[agg_path], plan.method_calls)
        except ValueError as e:
            conflicts.append(f"aggregator render failed: {e}")
    return {
        "ok": not conflicts,
        "conflicts": conflicts,
        "drop_paths": list(plan.drop_paths),
        "aggregator_path": agg_path,
        "new_aggregator_text": new_agg,
        "method_calls": list(plan.method_calls),
        "chosen": [(m.iface, m.impl, m.kind) for m in plan.chosen],
    }
