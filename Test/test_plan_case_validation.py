#!/usr/bin/env python3
"""Regression guard for "执行管理器运行失败" caused by dangling case ids.

``execution_plan_items.testcase_id`` has no foreign key. Deleting a test case
(or importing a project without its ``test_cases`` section) therefore leaves
plan items pointing at ids that no longer exist. Validation used to ignore
that, so /run started the batch and plan_runner logged
``test case ... missing`` on the first item and aborted everything — the UI
showed a bare failure with no cause.

``validate_plan`` now raises a blocking ``TESTCASE_NOT_FOUND`` error with the
currently available cases as replacement suggestions, and the plan editor
offers a per-row selector to fix the item.

Run: ``python3 Test/test_plan_case_validation.py``
"""
import asyncio
import os
import sys
from types import SimpleNamespace
from typing import List

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(HERE, "..", "backend")
sys.path.insert(0, BACKEND)

from app.services.plan_service import validate_plan  # noqa: E402

_failures: List[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


class FakeDB:
    def __init__(self, cases, devices=None):
        self.cases = cases
        self.devices = devices or []
        self._cases = {c.id: c for c in cases}

    async def execute(self, stmt):
        sql = str(stmt)
        if "FROM test_cases" in sql:
            return FakeResult(self.cases)
        if "FROM devices" in sql:
            return FakeResult(self.devices)
        return FakeResult([])

    async def get(self, model, key):
        return self._cases.get(key)


PLAN = {"name": "p", "plan_loop_count": 1, "max_parallel": 4, "on_error": "abort_all"}


def item(case_id: str, iid: str = "pitem_1"):
    return {
        "id": iid,
        "testcase_id": case_id,
        "group_no": 1,
        "seq": 1,
        "loop_count": 1,
        "delay_before_ms": 0,
        "delay_after_ms": 0,
        "loop_interval_ms": 0,
        "resolved_state": "unresolved",
        "resolved_device_ids": [],
        "node_count": 3,
    }


async def cases_checks() -> None:
    cases = [SimpleNamespace(id="tc_live_1", name="用例 A"),
             SimpleNamespace(id="tc_live_2", name="用例 B")]

    # 1. Dangling id -> blocking error with actionable suggestions.
    report = await validate_plan(FakeDB(cases), PLAN, [item("tc_deleted")])
    codes = [e["code"] for e in report["errors"]]
    check("dangling case is blocking", report["blocking"] is True, str(codes))
    check("dangling case reported as TESTCASE_NOT_FOUND",
          "TESTCASE_NOT_FOUND" in codes, str(codes))
    bad = next(e for e in report["errors"] if e["code"] == "TESTCASE_NOT_FOUND")
    check("error names the missing id and how to fix it",
          "tc_deleted" in bad["message"] and "重新选择" in bad["message"])
    check("error points at the offending item",
          bad["item_ids"] == ["pitem_1"], str(bad["item_ids"]))
    check("error offers live cases as replacements",
          [s["id"] for s in bad["suggestions"]] == ["tc_live_1", "tc_live_2"],
          str(bad["suggestions"]))

    # 2. Two dangling items produce two errors (one per row, so the UI can
    #    highlight each of them separately).
    report2 = await validate_plan(
        FakeDB(cases), PLAN,
        [item("tc_gone_1", "pitem_a"), item("tc_gone_2", "pitem_b")],
    )
    bad2 = [e for e in report2["errors"] if e["code"] == "TESTCASE_NOT_FOUND"]
    check("each dangling item reported separately", len(bad2) == 2, str(len(bad2)))

    # 3. A healthy plan must not regress into a false positive.
    good = await validate_plan(FakeDB(cases), PLAN, [item("tc_live_1")])
    check("existing case raises no TESTCASE_NOT_FOUND",
          not any(e["code"] == "TESTCASE_NOT_FOUND" for e in good["errors"]),
          str([e["code"] for e in good["errors"]]))
    check("healthy plan stays non-blocking", good["blocking"] is False)

    # 4. Blank ids (unsaved draft rows) are not treated as missing cases.
    blank = await validate_plan(FakeDB(cases), PLAN, [item("")])
    check("blank case id is not a TestCase lookup",
          not any(e["code"] == "TESTCASE_NOT_FOUND" for e in blank["errors"]))


def static_checks() -> None:
    api = open(os.path.join(BACKEND, "app", "api", "plans.py"), encoding="utf-8").read()
    check("run endpoint still blocks on validation",
          'if report["blocking"]' in api and "status_code=409" in api)

    editor = open(os.path.join(HERE, "..", "frontend", "src", "pages",
                               "ExecutionPlanner.tsx"), encoding="utf-8").read()
    check("editor offers an in-place replacement selector",
          "t('plan.caseMissing')" in editor and "t('plan.pickCase')" in editor)
    check("run flushes editor fixes before starting",
          "await save(true)" in editor and "const res = await planAPI.run(planId)" in editor
          and editor.index("await save(true)") < editor.index("await planAPI.run(planId)"))
    check("save is not called with the click event as `quiet`",
          "onClick={() => save()}" in editor)

    runner = open(os.path.join(BACKEND, "app", "services", "plan_runner.py"),
                  encoding="utf-8").read()
    check("runner still fails closed on a missing case",
          "test case %s missing" in runner)


def main() -> int:
    static_checks()
    asyncio.run(cases_checks())
    if _failures:
        print(f"\nFAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print("\nAll plan/case validation checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
