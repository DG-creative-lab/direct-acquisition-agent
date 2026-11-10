"""Recorded synthetic response snapshots and their coverage contract."""

from acquisition.contracts import Conflict, canonical, digest

from .outcomes import finite, identifier


REPORT_BINDINGS = ("organization", "cohort_id", "job_id", "metric", "window_start", "window_end")
REPORT_FIELDS = set(REPORT_BINDINGS) | {"schema", "mode", "report_id", "watermark", "final", "page_count", "pages"}


def normalize_report(report):
    if (type(report) is not dict or set(report) != REPORT_FIELDS
            or report["schema"] != "synthetic-provider-report/v1" or report["mode"] != "SYNTHETIC_ONLY"
            or type(report["final"]) is not bool or type(report["page_count"]) is not int
            or not 1 <= report["page_count"] <= 100 or type(report["pages"]) is not list
            or len(report["pages"]) > report["page_count"]):
        raise ValueError("Use a bounded synthetic provider report with an explicit page count")
    identifier(report["report_id"])
    for field in ("window_start", "window_end", "watermark"):
        finite(report[field])

    pages, events = {}, {}
    total = 0
    for page in report["pages"]:
        if (type(page) is not dict or set(page) != {"report_id", "number", "events"}
                or page["report_id"] != report["report_id"] or type(page["number"]) is not int
                or not 1 <= page["number"] <= report["page_count"] or type(page["events"]) is not list):
            raise ValueError("Each page must belong to the report and have a valid page number")
        if page["number"] in pages:
            raise Conflict("The report repeats a page number")
        total += len(page["events"])
        if total > 10000:
            raise ValueError("A report may contain at most 10000 events")
        for event in page["events"]:
            if (type(event) is not dict or set(event) != {"event_id", "outcome"}
                    or type(event["outcome"]) is not dict):
                raise ValueError("Each event requires its identity and explicit outcome")
            outcome = event["outcome"]
            business_id = outcome.get("business_id")
            identifier(business_id)
            expected_id = "synthetic_event_" + digest({"cohort_id": report["cohort_id"], "business_id": business_id})
            if event["event_id"] != expected_id:
                raise Conflict("Report event identity differs from its cohort and business")
            if outcome.get("response") is False and not report["final"]:
                raise Conflict("A non-response requires a final report through the cohort cutoff")
            if business_id in events and canonical(events[business_id]) != canonical(outcome):
                raise Conflict("The report contains conflicting copies of an event")
            events[business_id] = outcome
        pages[page["number"]] = page | {"events": sorted(page["events"], key=lambda event: event["event_id"])}

    if len(pages) != report["page_count"]:
        raise Conflict("The provider report is missing pages")
    return report | {"pages": [pages[number] for number in sorted(pages)]}, events, total - len(events)


def validate_report_binding(report, cohort, now):
    expected = cohort | {"cohort_id": cohort["id"]}
    if any(report[key] != expected[key] for key in REPORT_BINDINGS):
        raise Conflict("The report differs from the accepted cohort, metric or window")
    watermark = report["watermark"]
    if not cohort["window_start"] <= watermark <= min(now, cohort["window_end"]):
        raise Conflict("The report watermark is outside the available observation window")
    if report["final"] and watermark != cohort["window_end"]:
        raise Conflict("A final report must attest the entire closed cohort window")
