"""Contract-First Phase D: pure binder core (parse / plan / render / compute)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import contract_bind as cb


def _mod(iface, impl, method, kind):
    return (f"// @contract-module interface={iface} impl={impl} kind={kind}\n"
            f"public static class {impl}Module {{\n"
            f"    public static IServiceCollection {method}(this IServiceCollection services)\n"
            f"        => services.AddScoped<{iface}, {impl}>();\n}}\n")


_AGG = ("public static class FeatureModules {\n"
        "    public static IServiceCollection AddFeatureModules(this IServiceCollection services)\n"
        "    {\n"
        "        // @contract-aggregator:begin\n"
        "        services.AddNewsletterServiceModule();\n"
        "        // @contract-aggregator:end\n"
        "        return services;\n"
        "    }\n}\n")


def test_parse_modules_finds_marked_only():
    files = {"A.cs": _mod("INews", "NewsStub", "AddNewsModule", "stub"),
             "B.cs": "// nothing here\n"}
    mods = cb.parse_modules(files)
    assert len(mods) == 1 and mods[0].iface == "INews" and mods[0].kind == "stub"
    assert mods[0].method == "AddNewsModule"


def test_plan_prefers_real_and_drops_stub():
    files = {"stub/NewsModule.cs": _mod("INews", "NewsStub", "AddNewsModule", "stub"),
             "real/NewsModule.cs": _mod("INews", "NewsService", "AddNewsModule", "real")}
    plan = cb.plan_binding(cb.parse_modules(files))
    assert plan.conflicts == ()
    assert [m.impl for m in plan.chosen] == ["NewsService"]
    assert plan.drop_paths == ("stub/NewsModule.cs",)
    assert plan.method_calls == ("AddNewsModule",)


def test_plan_keeps_stub_when_no_real_yet():
    files = {"stub/NewsModule.cs": _mod("INews", "NewsStub", "AddNewsModule", "stub")}
    plan = cb.plan_binding(cb.parse_modules(files))
    assert [m.kind for m in plan.chosen] == ["stub"]
    assert plan.drop_paths == ()


def test_plan_flags_two_real_impls():
    files = {"a.cs": _mod("INews", "NewsA", "AddA", "real"),
             "b.cs": _mod("INews", "NewsB", "AddB", "real")}
    plan = cb.plan_binding(cb.parse_modules(files))
    assert any("2 real impls" in c for c in plan.conflicts)


def test_render_aggregator_replaces_region():
    out = cb.render_aggregator(_AGG, ["AddNewsModule", "AddOrderModule"])
    assert "services.AddNewsModule();" in out
    assert "services.AddOrderModule();" in out
    assert "services.AddNewsletterServiceModule();" not in out   # stub-era call gone
    assert cb.AGG_BEGIN in out and cb.AGG_END in out and "return services;" in out


def test_render_aggregator_missing_markers_raises():
    try:
        cb.render_aggregator("no markers here", ["X"])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_compute_binding_happy_path():
    files = {
        "Modules/NewsStubModule.cs": _mod("INews", "NewsStub", "AddNewsModule", "stub"),
        "Modules/OrderStubModule.cs": _mod("IOrder", "OrderStub", "AddOrderModule", "stub"),
        "slice1/NewsModule.cs": _mod("INews", "NewsService", "AddNewsModule", "real"),
        "slice2/OrderModule.cs": _mod("IOrder", "OrderService", "AddOrderModule", "real"),
        "FeatureModules.cs": _AGG,
    }
    res = cb.compute_binding(files)
    assert res["ok"] is True, res["conflicts"]
    assert set(res["drop_paths"]) == {"Modules/NewsStubModule.cs", "Modules/OrderStubModule.cs"}
    assert res["aggregator_path"] == "FeatureModules.cs"
    assert set(res["method_calls"]) == {"AddNewsModule", "AddOrderModule"}
    assert "services.AddNewsModule();" in res["new_aggregator_text"]
    assert ("INews", "NewsService", "real") in res["chosen"]


def test_compute_binding_no_aggregator_is_conflict():
    files = {"a.cs": _mod("INews", "NewsService", "AddNewsModule", "real")}
    res = cb.compute_binding(files)
    assert res["ok"] is False
    assert any("aggregator" in c for c in res["conflicts"])


def test_compute_binding_two_real_impls_blocks():
    files = {"a.cs": _mod("INews", "NewsA", "AddA", "real"),
             "b.cs": _mod("INews", "NewsB", "AddB", "real"),
             "FeatureModules.cs": _AGG}
    res = cb.compute_binding(files)
    assert res["ok"] is False
    assert any("2 real impls" in c for c in res["conflicts"])
