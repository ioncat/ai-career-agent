"""core/pipeline_events.py — the events the CV, cover and analysis workers raise.

One place builds the event texts (English, per the UI policy; the client picks its own text from `code`)
and writes them with the state:

  - a failure the worker records itself (`record_generation_failure`, `record_analysis_failure`) stores
    the state and the event in ONE transaction, then sends the event to the channels;
  - a failure or success the tool already recorded in the state (analysis writes its own `analysis_failed`
    and `analyzed`; CV and cover write `cv_generated` / `cover_generated`) gets its event right after
    (`emit_done`, `emit_failure`): the state is the truth and is already committed, the event is the
    message about it, so a crash between the two loses only the message, never the card.

`origin` is decided by the backend only: "user" when an API endpoint was hit from the app, "auto" for
everything the backend started on its own (recovery sweep, watcher).

Nothing here raises: a notification problem must never abort the pipeline.
"""

from __future__ import annotations

import logging

from core import failure_codes
from core.generation_failure import analysis_failure_code, soft_failure
from core.notifier import PipelineEvent, build_event, fan_out, notify
from db import database

log = logging.getLogger(__name__)

# kind -> (done event, failed event, noun used in titles, verb for success)
_KINDS = {
    "analysis": (PipelineEvent.ANALYSIS_DONE, PipelineEvent.ANALYSIS_FAILED, "Analysis", "done"),
    "cv": (PipelineEvent.CV_DONE, PipelineEvent.CV_FAILED, "CV", "ready"),
    "cover": (PipelineEvent.COVER_DONE, PipelineEvent.COVER_FAILED, "Cover", "ready"),
}

ORIGIN_USER = "user"
ORIGIN_AUTO = "auto"

LABEL_MAX = 120      # the vacancy label comes from scraped company and title text


async def vacancy_label(vacancy_id: int) -> str:
    """"Company — Title", the title alone, the company alone, or "#id"."""
    row = await database.get_vacancy_by_id(vacancy_id)
    if not row:
        return f"#{vacancy_id}"
    title = (row["title"] or "").strip()
    company = (row["company"] or "").strip()
    label = f"{company} — {title}" if title and company else (title or company or f"#{vacancy_id}")
    return label if len(label) <= LABEL_MAX else label[: LABEL_MAX - 1].rstrip() + "…"


async def _analysis_summary(vacancy_id: int) -> str:
    """"Fit 8/10 · apply" from the stored analysis, or "" when there is none yet."""
    try:
        from contracts.pipeline import AnalysisJson

        row = await database.get_vacancy_by_id(vacancy_id)
        analysis = AnalysisJson.model_validate_json((row["analysis_json"] if row else None) or "{}")
        if analysis.p2:
            return f"Fit {analysis.p2.fit_score}/10 · {analysis.p2.recommendation_label}"
    except Exception as exc:  # noqa: BLE001 - a missing summary must not cost the event
        log.debug("pipeline_events: no analysis summary for v#%s: %s", vacancy_id, exc)
    return ""


async def done_event(kind: str, user_id: int | None, vacancy_id: int, origin: str) -> dict:
    done, _failed, noun, verb = _KINDS[kind]
    label = await vacancy_label(vacancy_id)
    body = await _analysis_summary(vacancy_id) if kind == "analysis" else ""
    return build_event(done, user_id, vacancy_id, f"{noun} {verb} — {label}", body, origin=origin)


async def failure_event(
    kind: str, user_id: int | None, vacancy_id: int, origin: str, reason: str, code: str
) -> dict:
    _done, failed, noun, _verb = _KINDS[kind]
    label = await vacancy_label(vacancy_id)
    # The body is the stable text of the code, never the raw reason: the reason can carry a local file path
    # or scraped text, and it stays on the vacancy (analysis_error / generation_failure.reason) for the card.
    return build_event(
        failed, user_id, vacancy_id, f"{noun} failed — {label}", failure_codes.user_text(code),
        origin=origin, code=failure_codes.normalize(code),
    )


async def emit_done(kind: str, user_id: int | None, vacancy_id: int, origin: str) -> None:
    """The tool has already written the success state; tell the channels."""
    try:
        event = await done_event(kind, user_id, vacancy_id, origin)
        await notify(event["user_id"], event["event"], event["vacancy_id"], title=event["title"],
                     body=event["body"], origin=origin)
    except Exception as exc:  # noqa: BLE001
        log.warning("pipeline_events: %s done event for v#%s not sent: %s", kind, vacancy_id, exc)


async def emit_failure(
    kind: str, user_id: int | None, vacancy_id: int, origin: str, reason: str, code: str
) -> None:
    """The failure state is already written (by the tool); tell the channels."""
    try:
        event = await failure_event(kind, user_id, vacancy_id, origin, reason, code)
        await notify(event["user_id"], event["event"], event["vacancy_id"], title=event["title"],
                     body=event["body"], origin=origin, code=event["code"])
    except Exception as exc:  # noqa: BLE001
        log.warning("pipeline_events: %s failure event for v#%s not sent: %s", kind, vacancy_id, exc)


async def record_generation_failure(
    kind: str, user_id: int | None, vacancy_id: int, origin: str, reason: str, code: str,
    rollback_status: str, lang: str | None = None,
) -> None:
    """A CV or cover run failed: roll the status back, store the failure and its event in one
    transaction, then send the event to the channels."""
    event = None
    try:
        event = await failure_event(kind, user_id, vacancy_id, origin, reason, code)
    except Exception as exc:  # noqa: BLE001 - the state write below must happen without it
        log.warning("pipeline_events: %s failure event for v#%s not built: %s", kind, vacancy_id, exc)
    try:
        stored = await database.fail_generation(
            vacancy_id, kind, reason, rollback_status, code=code, lang=lang, notification=event,
        )
    except Exception as exc:  # noqa: BLE001 - called from an except branch: it must not raise again
        log.error("pipeline_events: %s failure of v#%s could not be recorded: %s", kind, vacancy_id, exc)
        return
    if stored and event:
        await fan_out(event["user_id"], event["event"], event["title"], event["body"])


async def record_analysis_failure(
    user_id: int | None, vacancy_id: int, origin: str, reason: str, code: str
) -> None:
    """An analysis run failed in a way only the worker saw (timeout, an exception, a tool that returned
    a warning text and left the vacancy "analyzing"): set `analysis_failed` and store the event in
    one transaction, then send it to the channels."""
    event = None
    try:
        event = await failure_event("analysis", user_id, vacancy_id, origin, reason, code)
    except Exception as exc:  # noqa: BLE001
        log.warning("pipeline_events: analysis failure event for v#%s not built: %s", vacancy_id, exc)
    try:
        stored = await database.set_analysis_error(vacancy_id, reason, notification=event)
    except Exception as exc:  # noqa: BLE001 - called from an except branch: it must not raise again
        log.error("pipeline_events: analysis failure of v#%s could not be recorded: %s", vacancy_id, exc)
        return
    if stored and event:
        await fan_out(event["user_id"], event["event"], event["title"], event["body"])


async def finish_analysis(user_id: int | None, vacancy_id: int, result: object, origin: str) -> None:
    """The analysis tool returned: decide from the vacancy's state (the truth) what happened, then tell the channels.

    cv_analyze writes `analysis_failed` itself for most failures and `analyzed` on success, and it also
    reports some failures only as a returned warning text, leaving the vacancy "analyzing" (a missing JD
    file); that last case is recorded here, so the vacancy cannot stay stuck. Used by AnalysisWorker and
    by RSSWatcher's automatic analysis. Never raises.
    """
    soft = soft_failure(result)
    try:
        row = await database.get_vacancy_by_id(vacancy_id)
        status = row["status"] if row else None
        if status == "analysis_failed":
            reason = (row["analysis_error"] if row else None) or (str(soft) if soft else "")
            log.error("analysis failed v#%d: %s", vacancy_id, reason)
            await emit_failure("analysis", user_id, vacancy_id, origin, reason, analysis_failure_code(soft))
        elif soft is not None:
            log.error("analysis failed v#%d: %s", vacancy_id, soft)
            await record_analysis_failure(user_id, vacancy_id, origin, str(soft)[:500], analysis_failure_code(soft))
        else:
            log.info("analysis done v#%d", vacancy_id)
            await emit_done("analysis", user_id, vacancy_id, origin)
    except Exception as exc:  # noqa: BLE001
        log.warning("pipeline_events: finishing the analysis of v#%s failed: %s", vacancy_id, exc)
        if soft is not None:
            # the tool only returned a warning: do not leave the vacancy "analyzing" because a read failed
            await record_analysis_failure(user_id, vacancy_id, origin, str(soft)[:500], analysis_failure_code(soft))
