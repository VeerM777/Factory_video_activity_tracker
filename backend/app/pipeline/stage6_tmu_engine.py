"""Stage 6 -- Deterministic TMU Engine.

Pure code, no model call. Given the parameter index values Stage 5 chose
(already validated against the fixed MOST tables), this module computes TMU,
total time, and VA/SVA/NVA/NVA-N/Noise bucketing exactly the way the source
workbook's formulas do -- verified against ASSY WITH PRESS OPERATION.xlsx's
cached values (see backend/tests/test_stage6_tmu_engine.py).

Formula (recovered from the ground-truth workbook, not invented here):
    Data Card in {G, C, T}: TMU = SUM(param_values) * 10 * FREQ
    Data Card PT:           TMU = FREQ * seconds / 0.036   (param_values[0] = seconds)
    Total Time (sec) = TMU * 0.036

One deliberate deviation from the legacy workbook, flagged here rather than
silently reproduced: the source sheet buckets VA/SVA/NVA-N/NVA by numeric
ref RANGES (e.g. "V<23 => NVA"), which only works because the taxonomy's ref
numbers happen to be contiguous per bucket, and it mis-buckets ref 0 (Noise)
as NVA. Since the taxonomy is explicitly versioned/editable (refs can move,
as ref 48/50 already did during this build), this engine instead buckets by
the taxonomy's own `classification` field. Same output for every ref that
existed in the original sheet; correct (and Noise now correctly nets to
zero across all four buckets) for any future edit.
"""
from __future__ import annotations

from app.config.most_tables import DataCard, load_most_tables
from app.config.taxonomy import load_taxonomy
from app.models.schemas import Classification, MostRow, Segment


def build_most_code(data_card: DataCard, param_values: list[int]) -> str:
    tables = load_most_tables()
    if data_card == "PT":
        return f"{param_values[0]}SEC"
    model = tables.sequence_models[data_card]
    return "".join(f"{letter}{value}" for letter, value in zip(model.parameters, param_values))


def compute_tmu(data_card: DataCard, param_values: list[int], freq: int) -> float:
    if data_card == "PT":
        seconds = param_values[0]
        return freq * seconds / 0.036
    return sum(param_values) * 10 * freq


def build_uppercase_elemental_description(
    segment_desc: str, human_state: str = "MOVE", data_card: str = "G"
) -> str:
    """Generates standard uppercase industrial MOST elemental descriptions matching
    traditional MOST time study formats (e.g. 'WITHIN REACH, GRASP THE FIXTURE',
    'PUSH TO ADJUST < 12 INCHES', 'WITHIN REACH, LAY ASIDE THE WORKPIECE')."""
    desc_upper = segment_desc.upper()

    object_name = "THE WORKPIECE"
    if "FIXTURE" in desc_upper or "TRAY" in desc_upper:
        object_name = "THE FIXTURE"
    elif "TOOL" in desc_upper or "DISPENSER" in desc_upper or "GLUE" in desc_upper or "SEALANT" in desc_upper:
        object_name = "GLUING TOOL"
    elif "CART" in desc_upper or "TROLLEY" in desc_upper:
        object_name = "THE CART"
    elif "HOIST" in desc_upper or "STRAP" in desc_upper or "HOOK" in desc_upper or "CRANE" in desc_upper:
        object_name = "THE HOIST STRAP"
    elif "FOAM" in desc_upper or "PACKAGING" in desc_upper or "COVER" in desc_upper:
        object_name = "THE PACKAGING"
    elif "CRATE" in desc_upper or "BOX" in desc_upper:
        object_name = "THE CRATE"
    elif "SCREW" in desc_upper or "BOLT" in desc_upper or "COMPONENT" in desc_upper or "PIECE" in desc_upper:
        object_name = "THE WORKPIECE"

    if "RE-GRASP" in desc_upper or ("HOLD" in desc_upper and human_state == "HOLD"):
        return f"WITHIN REACH, RE-GRASP {object_name}, HOLD"
    if "GRASP" in desc_upper or human_state == "GRASP" or "PICK" in desc_upper or "GRAB" in desc_upper:
        return f"WITHIN REACH, GRASP {object_name}"
    if "RELEASE" in desc_upper or human_state == "RELEASE" or "LAY ASIDE" in desc_upper or "RETURN" in desc_upper:
        return f"WITHIN REACH, LAY ASIDE {object_name}"
    if "PUSH" in desc_upper and ("ADJUST" in desc_upper or "MOVE" in desc_upper or "CART" in desc_upper):
        return "PUSH TO ADJUST < 12 INCHES"
    if "PULL" in desc_upper or "HOIST STRAP" in desc_upper:
        return f"PULL TRAY < 12 INCHES" if "TRAY" in desc_upper else "PUSH TO ADJUST < 12 INCHES"
    if "BUTTON" in desc_upper or "APPLY" in desc_upper or "PRESS" in desc_upper or "ACTUATE" in desc_upper:
        return "PUSH BUTTON TO APPLY THE GLUE < 12 INCHES" if ("GLUE" in desc_upper or "TOOL" in desc_upper) else "PUSH BUTTON TO APPLY < 12 INCHES"
    if "POSITION" in desc_upper or "PLACE" in desc_upper or "ALIGN" in desc_upper or "SEAT" in desc_upper or "INSERT" in desc_upper or "FIT" in desc_upper:
        return f"WITHIN REACH, PLACE {object_name} ON THE WORKPIECE" if object_name == "GLUING TOOL" else f"WITHIN REACH, PLACE {object_name} ON THE FIXTURE"

    return f"WITHIN REACH, GRASP {object_name}"


def build_most_row(
    segment: Segment,
    classification: Classification,
    s_no: int,
    activity_description: str,
    station_no: str = "",
    activity_no: str = "",
) -> MostRow:
    # Hard guardrail: reject any classification using a value outside the
    # fixed, enumerated MOST index tables or taxonomy before any math runs.
    classification.validate_against_tables()

    tables = load_most_tables()
    taxonomy = load_taxonomy()

    tmu = compute_tmu(classification.data_card, classification.param_values, classification.freq)
    total_time_sec = tmu * tables.tmu_conversion_factor_sec_per_tmu
    most_code = build_most_code(classification.data_card, classification.param_values)

    entry = taxonomy.by_ref(classification.muda_ref)
    va_sec = total_time_sec if entry.classification == "VA" else 0.0
    nvan_sec = total_time_sec if entry.classification == "NVA-N" else 0.0
    sva_sec = total_time_sec if entry.classification == "SVA" else 0.0
    nva_sec = total_time_sec if entry.classification == "NVA" else 0.0

    duration_sec = round(segment.t_end_sec - segment.t_start_sec, 2)
    timeline_str = f"{segment.t_start_sec:.2f}s - {segment.t_end_sec:.2f}s"
    mov_details = (
        f"Human: {segment.description} ({segment.human_movement_state}) | Machine: {segment.machine_state}"
    )
    uppercase_elemental = build_uppercase_elemental_description(
        segment.description, segment.human_movement_state, classification.data_card
    )

    return MostRow(
        s_no=s_no,
        station_no=station_no,
        activity_no=activity_no,
        activity_description=activity_description,
        data_card=classification.data_card,
        param_values=classification.param_values,
        most_code=most_code,
        freq=classification.freq,
        tmu=tmu,
        elemental_description=segment.description,
        operator=classification.operator,
        muda_ref=classification.muda_ref,
        total_time_sec=total_time_sec,
        online_offline_mode=classification.online_offline_mode,
        va_sec=va_sec,
        nvan_sec=nvan_sec,
        sva_sec=sva_sec,
        nva_sec=nva_sec,
        category=entry.description,
        source_video_uri=segment.source_video_uri,
        t_start_sec=segment.t_start_sec,
        t_end_sec=segment.t_end_sec,
        segment_model_version=segment.model_version,
        segment_prompt_version=segment.prompt_version,
        classification_model_version=classification.model_version,
        classification_prompt_version=classification.prompt_version,
        confidence=classification.confidence,
        activity_movement_details=mov_details,
        activity_duration_sec=duration_sec,
        activity_timeline=timeline_str,
        uppercase_elemental_description=uppercase_elemental,
    )
