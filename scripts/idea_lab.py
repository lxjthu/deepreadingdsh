"""Deterministic economics/management notes from local evidence, without providers.

Passages are evidence leads, not verified causal claims or field-wide novelty.
"""
from __future__ import annotations

import re
from typing import Any


TIER_ORDER = {"P0": 0, "P1": 1, "P2": 2}
METADATA_KINDS = {"title", "doi", "metadata", "keywords", "reference", "citation"}
METADATA_FIELDS = {"title", "doi", "journal", "keywords_json"}
HINTS = {
    "mechanism": r"\b(?:mechanisms?|through|mediat\w*)\b|机制|路径|中介",
    "moderator": r"\b(?:moderat\w*|contingent)\b|边界|调节",
    "identification": r"\b(?:(?-i:DID|IV|RDD)|fixed effects|instrumental variables?|difference.in.differences|regression discontinuity)\b|双重差分|工具变量|固定效应|断点回归|识别策略",
    "data": r"\b(?:data\w*|sample\w*|panel|annual reports?)\b|样本|数据|年报",
    "theory": r"\b(?:theor\w*|resource.based view|dynamic capabilities)\b|理论|资源基础观|动态能力",
    "measurement": r"\b(?:measur\w*|prox\w*|operationaliz\w*)\b|测量|度量|指标|操作化",
    "context": r"\b(?:institution\w*|countr\w*|industr\w*|region\w*)\b|制度|地区|行业|情境",
    "risk": r"\b(?:endogene\w*|reverse causality|measurement error|selection bias)\b|内生性|反向因果|测量误差|选择偏差",
}
LIMITATION = "规则提取仅整理当前证据片段；缺口限于本次检索范围，不能据此断言整个领域缺少研究或选题具有新颖性。"


def _compact(value: str | None) -> str:
    return " ".join((value or "").split())


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _entry_evidence(entry: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in entry.get("evidence") or entry.get("items") or []:
        text = _compact(row.get("quote") or row.get("text") or row.get("content"))
        if not text:
            continue
        rows.append({
            **row,
            "entry_id": str(entry.get("entry_id") or entry.get("id") or ""),
            "title": _compact(entry.get("title")),
            "source_tier": row.get("source_tier") if row.get("source_tier") in TIER_ORDER else "P2",
            "source_kind": row.get("source_kind") or "unknown",
            "quote": text[:700],
        })
    return sorted(rows, key=lambda row: TIER_ORDER[row["source_tier"]])


def _passages(rows: list[dict[str, Any]], kind: str) -> list[str]:
    sentences = [part.strip() for row in rows for part in re.split(r"(?<=[。！？.!?;；])\s*|\n+", row["quote"]) if part.strip()]
    return _unique([part for part in sentences if re.search(HINTS[kind], part, re.I)])[:5]


def _relationship(rows: list[dict[str, Any]]) -> tuple[str, str]:
    for row in rows:
        # Only label roles when the snippet contains an explicit relationship.
        match = re.search(
            r"(?:^|[。.!?]\s*)([^。.!?]{2,100}?)\s+(?:improves?|affects?|influences?|enhances?|reduces?)\s+([^。.!?]{2,100}?)(?=\s+(?:through|via|by)\b|[。.!?]|$)",
            row["quote"], re.I,
        )
        if not match:
            match = re.search(r"(?:^|[。；])\s*([^。；]{2,50}?)(?:通过[^，。；]{2,60}?[，,]?)?(?:显著)?(?:提升|提高|促进|降低|影响)([^，。；]{2,50})", row["quote"])
        if match:
            return _compact(match[1]), _compact(match[2]).rstrip("。.")
    return "", ""


def extract_constructs_from_evidence(
    *, evidence_pack: dict[str, Any], topic: str, max_constructs: int = 8,
) -> dict[str, Any]:
    """Produce passage-backed notes; lower tiers never overwrite stronger evidence."""
    constructs = []
    limitations = [*(evidence_pack.get("limitations") or []), LIMITATION]
    entries = evidence_pack.get("entries") or []
    limit = max(1, min(max_constructs, 20))
    for entry in entries:
        rows = _entry_evidence(entry)
        substantive = [
            row for row in rows
            if row["source_kind"] not in METADATA_KINDS and row.get("field") not in METADATA_FIELDS
        ]
        if not substantive:
            limitations.append(f"{entry.get('title') or entry.get('entry_id')}: no usable substantive evidence snippets；仅题名或元数据不足以提取理论关系。")
            continue
        best_tier = substantive[0]["source_tier"]
        primary = [row for row in substantive if row["source_tier"] == best_tier]
        independent, dependent = _relationship(primary)
        name = independent or _compact(topic) or _compact(entry.get("title"))
        mediators = []
        for row in primary:
            match = re.search(r"\b(?:through|via|mediator\s*:)\s+([^.;。；]+)|中介(?:变量)?[：:]\s*([^。；]+)", row["quote"], re.I)
            if match:
                mediators.append((match[1] or match[2]).strip())
        constructs.append({
            "construct_id": f"construct_{len(constructs) + 1}",
            "name": name,
            "category": "construct",
            "definition": primary[0]["quote"][:500],
            "mechanisms": _passages(primary, "mechanism"),
            "theory_base": _passages(primary, "theory"),
            "measurement": _passages(primary, "measurement"),
            "context": _passages(primary, "context"),
            "variables": {
                "independent": [independent] if independent else [],
                "dependent": [dependent] if dependent else [],
                "mediators": _unique(mediators),
                "moderators": _passages(primary, "moderator"),
            },
            "empirical_design": {
                "data_sources": _passages(primary, "data"),
                "identification": _passages(primary, "identification"),
                "risks": _passages(primary, "risk"),
            },
            "evidence": rows,
            "uncertainty": "medium" if best_tier == "P0" else "high",
        })
        if best_tier != "P0":
            limitations.append(f"{name}：仅有 {best_tier} 实质内容，需核对 P0 原文；笔记不能作为已验证结论。")
        if entry.get("conflicts"):
            limitations.append(f"{name}：证据包存在冲突，需逐项核对：{entry['conflicts']}")
        if len(constructs) >= limit:
            if len(entries) > limit:
                limitations.append(f"本轮最多整理 {limit} 条构念笔记，未覆盖全部输入文献。")
            break
    if not constructs:
        limitations.append("当前证据不足，请选择文献或补充摘要、原文窗口。")
    return {"status": "ready" if constructs else "insufficient_evidence", "topic": topic, "constructs": constructs, "limitations": _unique(limitations)}


def diagnose_research_gaps(*, construct_result: dict[str, Any], topic: str) -> dict[str, Any]:
    """Report missing evidence within this corpus, never field-wide novelty."""
    gaps = []
    for construct in construct_result.get("constructs") or []:
        empirical = construct.get("empirical_design") or {}
        checks = [
            ("causal_identification", empirical.get("identification"), "因果识别", ["identification strategy evidence", "data source and variation source"]),
            ("mechanism", construct.get("mechanisms"), "机制链条", ["机制与中介、调节变量的原文证据"]),
            ("theory", construct.get("theory_base"), "理论基础", ["理论定义、适用前提与可检验推论"]),
            ("measurement", construct.get("measurement"), "构念测量", ["变量操作化、指标效度与替代测量"]),
            ("context", construct.get("context"), "制度情境与边界", ["地区、行业与制度条件的原文证据"]),
            ("empirical_design", empirical.get("data_sources"), "样本与数据可得性", ["数据来源、样本范围及获取条件"]),
        ]
        for gap_type, present, label, needed in checks:
            if present:
                continue
            gaps.append({
                "gap_id": f"gap_{len(gaps) + 1}",
                "construct_id": construct.get("construct_id"),
                "gap_type": gap_type,
                "summary": f"{construct.get('name')}：当前片段未明确呈现{label}，需回到原文确认。",
                "why_it_matters": f"补足{label}证据后，才能判断研究贡献与设计可行性。",
                "supporting_evidence": (construct.get("evidence") or [])[:3],
                "needed_evidence": needed,
                "confidence": "low" if construct.get("uncertainty") == "high" else "medium",
            })
    return {"status": construct_result.get("status", "ready"), "topic": topic, "constructs": construct_result.get("constructs") or [], "gaps": gaps, "limitations": construct_result.get("limitations") or []}


def generate_research_ideas(
    *, construct_result: dict[str, Any], gap_result: dict[str, Any], max_ideas: int = 5,
) -> dict[str, Any]:
    """Form provisional questions using only extracted relationships and passages."""
    ideas = []
    gaps = gap_result.get("gaps") or []
    for construct in (construct_result.get("constructs") or [])[:max(1, min(max_ideas, 10))]:
        name = construct.get("name") or "待明确构念"
        variables = construct.get("variables") or {}
        outcomes = variables.get("dependent") or []
        mediators = variables.get("mediators") or []
        empirical = construct.get("empirical_design") or {}
        related = [gap for gap in gaps if gap.get("construct_id") == construct.get("construct_id")]
        question = f"{name}如何影响{'、'.join(outcomes)}？" if outcomes else f"如何界定和测量{name}，并明确其相关结果变量？"
        hypotheses = [f"待检验 H1：{name}与{'、'.join(outcomes)}存在关联；方向与因果关系需验证。"] if outcomes else []
        if mediators and outcomes:
            hypotheses.append(f"待检验 H2：{'、'.join(mediators)}可能构成上述关系的中介路径。")
        ideas.append({
            "idea_id": f"idea_{len(ideas) + 1}",
            "construct_id": construct.get("construct_id"),
            "title": question,
            "research_question": question,
            "theory_base": construct.get("theory_base") or [],
            "mechanism_chain": [name, *mediators, *outcomes],
            "hypotheses": hypotheses,
            "data_strategy": {
                "sample": "；".join(empirical.get("data_sources") or []) or "待确认样本与数据来源",
                "variables": _unique([name, *mediators, *outcomes]),
                "identification": "；".join(empirical.get("identification") or []) or "待核对识别假设、外生变异和数据条件后选择方法",
            },
            "contribution": [f"候选贡献方向：补足{gap['gap_type']}证据，需进一步文献核验。" for gap in related],
            "risks": [*(empirical.get("risks") or []), *(gap["summary"] for gap in related), "候选问题与假说尚未验证，不能据此声称创新或因果效应。"],
            "evidence_refs": _unique([str(row["entry_id"]) for row in construct.get("evidence") or [] if row.get("entry_id")]),
            "confidence": "low",
        })
    return {"status": construct_result.get("status", "ready"), "topic": construct_result.get("topic") or "", "ideas": ideas, "gaps": gaps, "limitations": construct_result.get("limitations") or []}


def run_idea_lab_pipeline(
    *, evidence_pack: dict[str, Any], topic: str, max_constructs: int = 8, max_ideas: int = 5,
) -> dict[str, Any]:
    constructs = extract_constructs_from_evidence(evidence_pack=evidence_pack, topic=topic, max_constructs=max_constructs)
    gaps = diagnose_research_gaps(construct_result=constructs, topic=topic)
    ideas = generate_research_ideas(construct_result=constructs, gap_result=gaps, max_ideas=max_ideas)
    return {**constructs, "gaps": gaps["gaps"], "ideas": ideas["ideas"]}
