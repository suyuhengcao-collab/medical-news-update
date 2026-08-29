#!/usr/bin/env python3
"""Fetch recent gastric-cancer publications and interventional trials.

Uses only the Python standard library. Outputs raw snapshots, normalized CSV files,
and a Markdown candidate report. The report is deliberately evidence-first: it
does not invent clinical conclusions from titles or registry fields.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "tracking.json"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
REPORT_DIR = ROOT / "weekly-reports" / "generated"
SCREENING_DIR = ROOT / "screening"
USER_AGENT = "gastric-cancer-tracker/0.1 (public biomedical evidence tracker)"


def request(url: str, *, retries: int = 3) -> bytes:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, application/xml;q=0.9"}
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=45) as r:
                return r.read()
        except Exception as exc:  # network errors vary by runner
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Request failed after {retries} attempts: {url}") from last_error


def text(node: ET.Element | None, path: str, default: str = "") -> str:
    if node is None:
        return default
    found = node.find(path)
    if found is None:
        return default
    return " ".join("".join(found.itertext()).split())


def pubmed_query(config: dict[str, Any]) -> str:
    conditions = " OR ".join(f'"{x}"[Title/Abstract]' for x in config["indications"])
    therapy = (
        'therapy[Title/Abstract] OR treatment[Title/Abstract] OR drug[Title/Abstract] '
        'OR trial[Title/Abstract] OR antibody[Title/Abstract] OR ADC[Title/Abstract] '
        'OR immunotherapy[Title/Abstract]'
    )
    return f"({conditions}) AND ({therapy}) AND \"last {int(config['lookback_days'])} days\"[Date - Publication]"


def fetch_pubmed(config: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    params = {
        "db": "pubmed",
        "term": pubmed_query(config),
        "retmode": "json",
        "retmax": str(config["max_pubmed_records"]),
        "sort": "pub date",
        "tool": "gastric_cancer_tracker",
        "email": os.getenv("NCBI_EMAIL", "tracker@example.com"),
    }
    api_key = os.getenv("NCBI_API_KEY")
    if api_key:
        params["api_key"] = api_key
    search_url = base + "esearch.fcgi?" + urllib.parse.urlencode(params)
    search = json.loads(request(search_url))
    ids = search.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return [], search

    fetch_params = {
        "db": "pubmed",
        "id": ",".join(ids),
        "retmode": "xml",
        "tool": "gastric_cancer_tracker",
        "email": params["email"],
    }
    if api_key:
        fetch_params["api_key"] = api_key
    xml_bytes = request(base + "efetch.fcgi?" + urllib.parse.urlencode(fetch_params))
    root = ET.fromstring(xml_bytes)
    rows: list[dict[str, str]] = []
    for article in root.findall(".//PubmedArticle"):
        citation = article.find("MedlineCitation")
        journal = citation.find("Article/Journal") if citation is not None else None
        year = text(journal, "JournalIssue/PubDate/Year") or text(journal, "JournalIssue/PubDate/MedlineDate")
        pmid = text(citation, "PMID")
        doi = ""
        for identifier in article.findall("PubmedData/ArticleIdList/ArticleId"):
            if identifier.attrib.get("IdType") == "doi":
                doi = (identifier.text or "").strip()
                break
        rows.append(
            {
                "pmid": pmid,
                "title": text(citation, "Article/ArticleTitle"),
                "abstract": " ".join(
                    " ".join("".join(x.itertext()).split())
                    for x in article.findall("MedlineCitation/Article/Abstract/AbstractText")
                ),
                "journal": text(journal, "Title"),
                "publication_date": year,
                "doi": doi,
                "source_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return rows, {"search": search, "xml": xml_bytes.decode("utf-8", errors="replace")}


def trial_value(study: dict[str, Any], *path: str, default: Any = "") -> Any:
    value: Any = study
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key, default)
    return value


def fetch_trials(config: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    condition = " OR ".join(config["indications"])
    params = {"query.cond": condition, "pageSize": str(config["max_trial_records"]), "format": "json"}
    url = "https://clinicaltrials.gov/api/v2/studies?" + urllib.parse.urlencode(params)
    payload = json.loads(request(url))
    rows: list[dict[str, str]] = []
    for study in payload.get("studies", []):
        p = study.get("protocolSection", {})
        design = p.get("designModule", {})
        if design.get("studyType") != "INTERVENTIONAL":
            continue
        ident = p.get("identificationModule", {})
        status = p.get("statusModule", {})
        contacts = p.get("contactsLocationsModule", {})
        arms = p.get("armsInterventionsModule", {})
        outcomes = p.get("outcomesModule", {})
        sponsor = p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {})
        nct = ident.get("nctId", "")
        interventions = arms.get("interventions", [])
        countries = sorted({x.get("country", "") for x in contacts.get("locations", []) if x.get("country")})
        phases = design.get("phases", [])
        primary = outcomes.get("primaryOutcomes", [])
        rows.append(
            {
                "nct_id": nct,
                "brief_title": ident.get("briefTitle", ""),
                "overall_status": status.get("overallStatus", ""),
                "phase": "; ".join(phases),
                "enrollment": str(design.get("enrollmentInfo", {}).get("count", "")),
                "sponsor": sponsor.get("name", ""),
                "interventions": "; ".join(x.get("name", "") for x in interventions if x.get("name")),
                "primary_outcomes": "; ".join(x.get("measure", "") for x in primary if x.get("measure")),
                "countries": "; ".join(countries),
                "study_start": trial_value(status, "startDateStruct", "date"),
                "primary_completion": trial_value(status, "primaryCompletionDateStruct", "date"),
                "last_update_posted": trial_value(status, "studyLastUpdatePostDateStruct", "date"),
                "source_url": f"https://clinicaltrials.gov/study/{nct}" if nct else "",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return rows, payload


def load_previous(path: Path, key: str) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        return {row[key]: row for row in csv.DictReader(f) if row.get(key)}


def changes(current: list[dict[str, str]], previous: dict[str, dict[str, str]], key: str) -> list[dict[str, Any]]:
    watched = ["overall_status", "phase", "enrollment", "primary_completion", "interventions", "primary_outcomes"]
    output: list[dict[str, Any]] = []
    for row in current:
        identifier = row[key]
        if identifier not in previous:
            output.append({"id": identifier, "change_type": "new", "changes": {}})
            continue
        diff = {field: {"before": previous[identifier].get(field, ""), "after": row.get(field, "")}
                for field in watched if field in row and previous[identifier].get(field, "") != row.get(field, "")}
        if diff:
            output.append({"id": identifier, "change_type": "updated", "changes": diff})
    return output


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def render_report(publications: list[dict[str, str]], trials: list[dict[str, str]], trial_changes: list[dict[str, Any]]) -> str:
    today = date.today().isoformat()
    changed_ids = {x["id"]: x for x in trial_changes}
    lines = [
        f"# 胃癌创新药候选周报｜{today}", "",
        "> 由公开数据库自动生成，供人工筛选和临床解读；不构成医学、监管或投资结论。", "",
        "## 本次抓取概览", "",
        f"- PubMed近期相关记录：{len(publications)}条",
        f"- ClinicalTrials.gov干预性研究：{len(trials)}项",
        f"- 新增或字段变化的试验：{len(trial_changes)}项", "",
        "## 新增或变化的试验", "",
    ]
    if not trial_changes:
        lines.append("本次未识别到新增或关键字段变化。")
    for trial in trials:
        change = changed_ids.get(trial["nct_id"])
        if not change:
            continue
        lines.extend([
            f"### [{trial['nct_id']}]({trial['source_url']})｜{trial['brief_title']}", "",
            f"- 变化类型：{change['change_type']}",
            f"- 阶段/状态：{trial['phase'] or '未登记'} / {trial['overall_status'] or '未登记'}",
            f"- 干预：{trial['interventions'] or '未登记'}",
            f"- 主要终点：{trial['primary_outcomes'] or '未登记'}",
            f"- 申办方：{trial['sponsor'] or '未登记'}", "",
        ])
        if change["changes"]:
            lines.append("登记字段变化：")
            for field, values in change["changes"].items():
                lines.append(f"- `{field}`：{values['before'] or '空'} → {values['after'] or '空'}")
            lines.append("")
        lines.extend(["人工解读：", "- 临床意义：待核查", "- CRA/运营提示：待核查", "- 尚不能得出的结论：待核查", ""])

    lines.extend(["## 近期文献候选", ""])
    if not publications:
        lines.append("本次未检索到符合条件的近期文献。")
    for item in publications[:20]:
        lines.extend([
            f"### [{item['title']}]({item['source_url']})", "",
            f"- 期刊/日期：{item['journal'] or '未登记'} / {item['publication_date'] or '未登记'}",
            f"- PMID：{item['pmid']}",
            f"- DOI：{item['doi'] or '未登记'}", "",
            "人工解读：", "- 研究类型与患者人群：待核查", "- 关键结果：待核查",
            "- 与当前治疗格局的关系：待核查", "- 局限性：待核查", "",
        ])
    lines.extend(["## 数据来源", "", "- PubMed/NCBI E-utilities", "- ClinicalTrials.gov API v2", ""])
    return "\n".join(lines)


def write_asreview_input(
    path: Path,
    publications: list[dict[str, str]],
    trials: list[dict[str, str]],
    trial_changes: list[dict[str, Any]],
) -> None:
    """Write a UTF-8 CSV compatible with ASReview LAB 3.

    ASReview requires a title or abstract and recognizes doi, url, keywords,
    and included. Extra metadata columns remain available after export.
    """
    changed_ids = {item["id"] for item in trial_changes}
    rows: list[dict[str, str]] = []
    for item in publications:
        rows.append(
            {
                "record_id": f"PMID:{item['pmid']}",
                "title": item["title"],
                "abstract": item["abstract"],
                "keywords": "publication; PubMed; gastric cancer; drug development",
                "doi": item["doi"],
                "url": item["source_url"],
                "source_type": "publication",
                "included": "",
            }
        )
    for trial in trials:
        if trial["nct_id"] not in changed_ids:
            continue
        summary = (
            f"Phase: {trial['phase'] or 'not reported'}. "
            f"Status: {trial['overall_status'] or 'not reported'}. "
            f"Sponsor: {trial['sponsor'] or 'not reported'}. "
            f"Interventions: {trial['interventions'] or 'not reported'}. "
            f"Primary outcomes: {trial['primary_outcomes'] or 'not reported'}. "
            f"Enrollment: {trial['enrollment'] or 'not reported'}. "
            f"Primary completion: {trial['primary_completion'] or 'not reported'}."
        )
        rows.append(
            {
                "record_id": trial["nct_id"],
                "title": trial["brief_title"],
                "abstract": summary,
                "keywords": "clinical trial; ClinicalTrials.gov; gastric cancer; trial update",
                "doi": "",
                "url": trial["source_url"],
                "source_type": "clinical_trial_change",
                "included": "",
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["record_id", "title", "abstract", "keywords", "doi", "url", "source_type", "included"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    SCREENING_DIR.mkdir(parents=True, exist_ok=True)
    publications_path = DATA_DIR / "publications.csv"
    trials_path = DATA_DIR / "trials.csv"
    previous_trials = load_previous(trials_path, "nct_id")

    publications, pubmed_raw = fetch_pubmed(config)
    trials, trials_raw = fetch_trials(config)
    trial_changes = changes(trials, previous_trials, "nct_id")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (RAW_DIR / f"pubmed-{stamp}.json").write_text(json.dumps(pubmed_raw, ensure_ascii=False), encoding="utf-8")
    (RAW_DIR / f"clinicaltrials-{stamp}.json").write_text(json.dumps(trials_raw, ensure_ascii=False), encoding="utf-8")
    write_csv(publications_path, publications)
    write_csv(trials_path, trials)
    (DATA_DIR / "trial_changes.json").write_text(json.dumps(trial_changes, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = REPORT_DIR / f"{date.today().isoformat()}.md"
    report_path.write_text(render_report(publications, trials, trial_changes), encoding="utf-8")
    asreview_path = SCREENING_DIR / "asreview_input.csv"
    write_asreview_input(asreview_path, publications, trials, trial_changes)
    print(f"Generated {report_path.relative_to(ROOT)}")
    print(f"Generated {asreview_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"tracker update failed: {exc}", file=sys.stderr)
        raise
