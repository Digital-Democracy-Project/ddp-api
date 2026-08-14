"""Request model for the /legbot analyze-bill dispatch endpoint.

Mirrors app/schemas/common.py's CreateEventRequest -- only question_type is
required; every other field (bill_source, url, claim, old_bill_source,
diff_source, diff_format, ...) is one of CAMS/LegBot's existing per-question-
type payload fields (see ddp-sync's legbot_client.py) and is passed through
as-is via extra="allow". No response model: CAMS's JSON is forwarded
verbatim, same as broker_proxy.py/ddp_sync_proxy.py/openstates_proxy.py.
"""

from pydantic import BaseModel, ConfigDict


class LegBotAnalyzeRequest(BaseModel):
    """Request body for POST /legbot/tasks.

    question_type selects which LegBot question is being asked
    (e.g. "summary_500char", "pros_cons", "bill_changelog",
    "verify_bill_position", "find_bill_positions"). Every other field is
    question-type-specific and forwarded to CAMS untouched -- this proxy
    does not enumerate or validate them, so new LegBot question types work
    here without a ddp-api code change.
    """
    model_config = ConfigDict(extra="allow")

    question_type: str
