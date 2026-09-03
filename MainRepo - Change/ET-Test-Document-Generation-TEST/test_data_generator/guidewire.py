import base64
import hashlib
import io
import json
import math
import re
import urllib.parse
import urllib.request
import urllib.error
from collections import Counter
from typing import Any, Dict, Optional, Union
 
try:
    from pyeztrace import print
except ImportError:
    pass
 
class GuidewireClient:
    """Lightweight HTTP client for Guidewire ClaimCenter REST API."""
 
    DEFAULT_AUTO_DOCUMENT_QUERIES = (
        "estimate|appraisal|repair estimate",
        "photo|photos|image|inspection",
        "police report|accident report",
        "tow|towing|storage",
        "rental",
        "injury|medical|bodily injury",
        "total loss|salvage|title",
        "payment|settlement|release",
    )
 
    def __init__(self, base_url: str, username: str, password: str, timeout_seconds: int = 60):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout_seconds = timeout_seconds
 
    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"
 
    def _get_auth(self) -> str:
        credentials = f"{self.username}:{self.password}"
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
        return f"Basic {encoded}"
 
    def resolve_claim_id_by_number(self, claim_number: str) -> str:
        if str(claim_number).startswith("cc:"):
            return claim_number
        print(f"Resolving claim number '{claim_number}' to Guidewire public ID...")
        safe_number = urllib.parse.quote(str(claim_number), safe="%")
        raw = self.get_json(f"rest/claim/v1/claims?filter=claimNumber:eq:{safe_number}")
        if isinstance(raw, dict) and "data" in raw and isinstance(raw["data"], list) and len(raw["data"]) > 0:
            claim_id = raw["data"][0].get("attributes", {}).get("id") or raw["data"][0].get("id")
            if claim_id:
                print(f"Claim number '{claim_number}' resolved to ID '{claim_id}'")
                return claim_id
        print(f"Warning: Could not resolve claim number '{claim_number}' to a public ID. Falling back.")
        return claim_number
 
    def get_json(self, path: str, *, headers: Optional[Dict[str, str]] = None) -> Union[Dict[str, Any], str]:
        if headers is None:
            headers = {}
        url = self._url(path)
        req = urllib.request.Request(url, method="GET")
        headers["Authorization"] = self._get_auth()
        req.add_header("Accept", "application/json")
        for key, value in headers.items():
            req.add_header(key, value)
 
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                content_type = (resp.headers.get("Content-Type") or "").lower()
                raw = resp.read()
                if not raw:
                    return {"url": url, "status": resp.status, "data": None}
 
                if "application/json" in content_type:
                    return json.loads(raw.decode("utf-8"))
                return raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            return {
                "error": "http_error",
                "url": url,
                "status": exc.code,
                "reason": str(getattr(exc, "reason", "")) or None,
                "body": body or None,
            }
        except urllib.error.URLError as exc:
            return {"error": "url_error", "url": url, "reason": str(exc.reason)}
        except Exception as exc:
            return {"error": "unexpected_error", "url": url, "detail": str(exc)}
 
    @staticmethod
    def _nested_name(value: Any) -> Any:
        if isinstance(value, dict):
            return value.get("displayName") or value.get("name") or value.get("code")
        return value
 
    @staticmethod
    def _nested_id(value: Any) -> Any:
        if isinstance(value, dict):
            return value.get("id")
        return None
 
    @staticmethod
    def _nested_uri(value: Any) -> Any:
        if isinstance(value, dict):
            return value.get("uri")
        return None
 
    @staticmethod
    def _nested_code(value: Any) -> Any:
        if isinstance(value, dict):
            return value.get("code")
        return value
 
    @staticmethod
    def _policy_address(value: Any) -> Any:
        if isinstance(value, list):
            return ", ".join(
                addr.get("displayName")
                for addr in value
                if isinstance(addr, dict) and addr.get("displayName")
            ) or None
        if isinstance(value, dict):
            return value.get("displayName")
        return value
 
    @staticmethod
    def _sort_list_of_dicts(items: list[dict], keys: list[str]) -> list[dict]:
        return sorted(
            items,
            key=lambda item: tuple(str(item.get(key) or "") for key in keys),
        )
 
    def get_claim_details_summary(self, claim_id: str) -> Union[Dict[str, Any], str]:
        safe_claim = urllib.parse.quote(str(claim_id), safe="%")
        raw = self.get_json(f"rest/claim/v1/claims/{safe_claim}")
        data = raw.get("data", {}) if isinstance(raw, dict) else {}
        attrs = data.get("attributes", {}) if isinstance(data, dict) else {}
 
        if not isinstance(raw, dict):
            return raw
        if raw.get("error"):
            return raw
 
        assigned_user = attrs.get("assignedUser")
        assigned_group = attrs.get("assignedGroup")
        lob_code = attrs.get("lobCode")
 
        return {
            "claim_number": attrs.get("claimNumber") or attrs.get("claim_number"),
            "policy_number": attrs.get("policyNumber") or attrs.get("policy_number"),
            "status": self._nested_name(attrs.get("state")) or attrs.get("claim_status"),
            "loss_type": self._nested_name(attrs.get("lossType")),
            "loss_cause": self._nested_name(attrs.get("lossCause")),
            "loss_date": attrs.get("lossDate"),
            "insured": self._nested_name(attrs.get("insured")),
            "reporter": self._nested_name(attrs.get("reporter")),
            "assigned_adjuster": self._nested_name(assigned_user) or attrs.get("adjuster"),
            "adjuster_id": self._nested_id(assigned_user),
            "assigned_group": self._nested_name(assigned_group),
            "assigned_group_id": self._nested_id(assigned_group),
            "assigned_group_uri": self._nested_uri(assigned_group),
            "jurisdiction": self._nested_name(attrs.get("jurisdiction")),
            "line_of_business": self._nested_name(lob_code),
            "line_of_business_code": self._nested_code(lob_code),
            "how_reported": self._nested_name(attrs.get("howReported")),
            "reported_date": attrs.get("reportedDate"),
            "main_contact": self._nested_name(attrs.get("mainContact")),
            "loss_location": self._nested_name(attrs.get("lossLocation")),
            "policy_address": self._policy_address(attrs.get("policyAddresses")),
        }
 
    def get_claim_policy_summary(self, claim_id: str) -> Union[Dict[str, Any], str]:
        safe_claim = urllib.parse.quote(str(claim_id), safe="%")
        raw = self.get_json(f"rest/claim/v1/claims/{safe_claim}/policy")
        data = raw.get("data", {}) if isinstance(raw, dict) else {}
        attrs = data.get("attributes", {}) if isinstance(data, dict) else {}
 
        if not isinstance(raw, dict):
            return raw
        if raw.get("error"):
            return raw
 
        def nested_value(value: Any) -> Any:
            if isinstance(value, dict):
                return value.get("name") or value.get("code")
            return value
 
        return {
            "policy_number": attrs.get("policyNumber") or attrs.get("policy_number"),
            "policy_type": nested_value(attrs.get("policyType")),
            "policy_effective_date": attrs.get("effectiveDate"),
            "policy_expiration_date": attrs.get("expirationDate"),
            "currency": nested_value(attrs.get("currency")),
            "insured": (
                attrs.get("insured", {}).get("displayName")
                if isinstance(attrs.get("insured"), dict)
                else attrs.get("insured")
            ),
        }
 
    def get_claim_activities_summary(self, claim_id: str) -> Union[Dict[str, Any], str]:
        safe_claim = urllib.parse.quote(str(claim_id), safe="%")
        raw = self.get_json(f"rest/claim/v1/claims/{safe_claim}/activities")
        if not isinstance(raw, dict) or "data" not in raw or not isinstance(raw["data"], list):
            return raw
 
        cleaned_activities = []
        for activity in raw["data"]:
            attrs = activity.get("attributes", {})
            cleaned_activities.append(
                {
                    "id": attrs.get("id") or activity.get("id"),
                    "subject": attrs.get("subject"),
                    "activity_pattern": attrs.get("activityPattern"),
                    "activity_type": (attrs.get("activityType") or {}).get("name"),
                    "assigned_user": (attrs.get("assignedUser") or {}).get("displayName"),
                    "assigned_group": (attrs.get("assignedGroup") or {}).get("displayName"),
                    "status": (attrs.get("status") or {}).get("name"),
                    "priority": (attrs.get("priority") or {}).get("name"),
                    "due_date": attrs.get("dueDate"),
                    "create_time": attrs.get("createTime"),
                    "mandatory": attrs.get("mandatory"),
                    "escalated": attrs.get("escalated"),
                    "externally_owned": attrs.get("externallyOwned"),
                    "related_to": (attrs.get("relatedTo") or {}).get("displayName"),
                    "assigned_by_user": (attrs.get("assignedByUser") or {}).get("displayName"),
                    "assignment_status": (attrs.get("assignmentStatus") or {}).get("name"),
                    "importance": (attrs.get("importance") or {}).get("name"),
                    "description": attrs.get("description"),
                }
            )
 
        cleaned_activities = self._sort_list_of_dicts(
            cleaned_activities,
            ["id", "create_time", "subject"],
        )
        return {
            "count": len(cleaned_activities),
            "activities": cleaned_activities,
        }
 
    def get_claim_notes_summary(self, claim_id: str) -> Union[Dict[str, Any], str]:
        safe_claim = urllib.parse.quote(str(claim_id), safe="%")
        raw = self.get_json(f"rest/claim/v1/claims/{safe_claim}/notes")
        if not isinstance(raw, dict) or "data" not in raw or not isinstance(raw["data"], list):
            return raw
 
        cleaned_notes = []
        for note in raw.get("data", []):
            attrs = note.get("attributes", {})
            cleaned_notes.append(
                {
                    "id": attrs.get("id") or note.get("id"),
                    "author": (attrs.get("author") or {}).get("displayName"),
                    "created_date": attrs.get("createdDate"),
                    "updated_date": attrs.get("updateTime"),
                    "body_summary": attrs.get("bodySummary"),
                    "confidential": attrs.get("confidential"),
                    "topic": (attrs.get("topic") or {}).get("name"),
                    "related_to": (attrs.get("relatedTo") or {}).get("displayName"),
                }
            )
 
        cleaned_notes = self._sort_list_of_dicts(
            cleaned_notes,
            ["id", "updated_date", "created_date"],
        )
        return {
            "count": len(cleaned_notes),
            "notes": cleaned_notes,
        }
 
    def get_claim_history_events_summary(self, claim_id: str) -> Union[Dict[str, Any], str]:
        safe_claim = urllib.parse.quote(str(claim_id), safe="%")
        raw = self.get_json(f"rest/claim/v1/claims/{safe_claim}/history-events")
        if not isinstance(raw, dict) or "data" not in raw:
            return raw
 
        events = []
        for event in raw.get("data", []):
            attrs = event.get("attributes", {})
            events.append(
                {
                    "timestamp": attrs.get("eventTimestamp"),
                    "type": (attrs.get("historyType") or {}).get("name"),
                    "description": attrs.get("description"),
                    "user": (attrs.get("user") or {}).get("displayName"),
                }
            )
 
        events = self._sort_list_of_dicts(events, ["timestamp", "type", "description"])
        return {
            "count": len(events),
            "events": events,
        }
 
    def get_claim_exposures_summary(self, claim_id: str) -> Union[Dict[str, Any], str]:
        safe_claim = urllib.parse.quote(str(claim_id), safe="%")
        raw = self.get_json(f"rest/claim/v1/claims/{safe_claim}/exposures")
        if not isinstance(raw, dict) or "data" not in raw or not isinstance(raw["data"], list):
            return raw
 
        exposures = []
        for exposure in raw.get("data", []):
            attrs = exposure.get("attributes", {})
            exposures.append(
                {
                    "claim_order": attrs.get("claimOrder"),
                    "status": (attrs.get("state") or {}).get("name"),
                    "exposure_type": (attrs.get("type") or {}).get("name"),
                    "loss_party": (attrs.get("lossParty") or {}).get("name"),
                    "claimant": (attrs.get("claimant") or {}).get("displayName"),
                    "claimant_type": (attrs.get("claimantType") or {}).get("name"),
                    "primary_coverage": (attrs.get("primaryCoverage") or {}).get("name"),
                    "coverage_subtype": (attrs.get("coverageSubtype") or {}).get("name"),
                    "jurisdiction": (attrs.get("jurisdiction") or {}).get("name"),
                    "segment": (attrs.get("segment") or {}).get("name"),
                    "assigned_user": (attrs.get("assignedUser") or {}).get("displayName"),
                    "assigned_group": (attrs.get("assignedGroup") or {}).get("displayName"),
                    "assigned_by_user": (attrs.get("assignedByUser") or {}).get("displayName"),
                    "assignment_status": (attrs.get("assignmentStatus") or {}).get("name"),
                    "contact_permitted": attrs.get("contactPermitted"),
                    "create_time": attrs.get("createTime"),
                    "created_via": (attrs.get("createdVia") or {}).get("name"),
                    "strategy": (attrs.get("strategy") or {}).get("name"),
                    "tier": (attrs.get("tier") or {}).get("name"),
                    "vehicle_incident": (attrs.get("vehicleIncident") or {}).get("displayName"),
                }
            )
 
        exposures = self._sort_list_of_dicts(exposures, ["claim_order", "create_time", "claimant"])
        return {"count": len(exposures), "exposures": exposures}
 
    def get_claim_contacts_summary(self, claim_id: str) -> Union[Dict[str, Any], str]:
        safe_claim = urllib.parse.quote(str(claim_id), safe="%")
        raw = self.get_json(f"rest/claim/v1/claims/{safe_claim}/contacts")
        if not isinstance(raw, dict) or "data" not in raw or not isinstance(raw["data"], list):
            return raw
 
        contacts = []
        for contact in raw.get("data", []):
            attrs = contact.get("attributes", {})
            roles = []
            for role in attrs.get("roles") or []:
                role_info = role.get("role") or {}
                related = role.get("relatedTo") or {}
                roles.append(
                    {
                        "role": role_info.get("name"),
                        "active": role.get("active"),
                        "related_to": related.get("displayName"),
                        "related_type": related.get("type"),
                    }
                )
            contacts.append(
                {
                    "display_name": attrs.get("displayName"),
                    "first_name": attrs.get("firstName"),
                    "last_name": attrs.get("lastName"),
                    "contact_subtype": attrs.get("contactSubtype"),
                    "contact_prohibited": attrs.get("contactProhibited"),
                    "roles": roles,
                }
            )
 
        contacts = self._sort_list_of_dicts(contacts, ["display_name", "contact_subtype"])
        return {"count": len(contacts), "contacts": contacts}
 
    def get_claim_vehicle_incidents_summary(self, claim_id: str) -> Union[Dict[str, Any], str]:
        safe_claim = urllib.parse.quote(str(claim_id), safe="%")
        raw = self.get_json(f"rest/claim/v1/claims/{safe_claim}/vehicle-incidents")
        if not isinstance(raw, dict) or "data" not in raw or not isinstance(raw["data"], list):
            return raw
 
        incidents = []
        for incident in raw.get("data", []):
            attrs = incident.get("attributes", {})
            vehicle = attrs.get("vehicle") or {}
            driver = attrs.get("driver") or {}
            incidents.append(
                {
                    "driver": driver.get("displayName"),
                    "vehicle_display_name": vehicle.get("displayName"),
                    "vehicle_make": vehicle.get("make"),
                    "vehicle_model": vehicle.get("model"),
                    "vehicle_year": vehicle.get("year"),
                    "policy_vehicle": vehicle.get("policyVehicle"),
                }
            )
 
        incidents = self._sort_list_of_dicts(incidents, ["driver", "vehicle_display_name"])
        return {"count": len(incidents), "vehicle_incidents": incidents}
 
    @staticmethod
    def _transaction_amounts(line_items: Any) -> list[dict]:
        amounts = []
        for item in line_items or []:
            claim_amount = item.get("claimAmount") or {}
            amounts.append(
                {
                    "amount": claim_amount.get("amount"),
                    "currency": claim_amount.get("currency"),
                }
            )
        return amounts
 
    def get_claim_reserves_summary(self, claim_id: str) -> Union[Dict[str, Any], str]:
        safe_claim = urllib.parse.quote(str(claim_id), safe="%")
        raw = self.get_json(f"rest/claim/v1/claims/{safe_claim}/reserves")
        if not isinstance(raw, dict) or "data" not in raw or not isinstance(raw["data"], list):
            return raw
 
        reserves = []
        for reserve in raw.get("data", []):
            attrs = reserve.get("attributes", {})
            reserve_line = attrs.get("reserveLine") or {}
            reserves.append(
                {
                    "status": (attrs.get("status") or {}).get("name"),
                    "subtype": (attrs.get("subtype") or {}).get("name"),
                    "coverage": (attrs.get("coverage") or {}).get("name"),
                    "cost_category": (reserve_line.get("costCategory") or {}).get("name"),
                    "cost_type": (reserve_line.get("costType") or {}).get("name"),
                    "exposure": (reserve_line.get("exposure") or {}).get("displayName"),
                    "amounts": self._transaction_amounts(attrs.get("lineItems")),
                    "create_time": attrs.get("createTime"),
                    "created_via": (attrs.get("createdVia") or {}).get("name"),
                }
            )
 
        reserves = self._sort_list_of_dicts(reserves, ["create_time", "coverage", "cost_type"])
        return {"count": len(reserves), "reserves": reserves}
 
    def get_claim_payments_summary(self, claim_id: str) -> Union[Dict[str, Any], str]:
        safe_claim = urllib.parse.quote(str(claim_id), safe="%")
        raw = self.get_json(f"rest/claim/v1/claims/{safe_claim}/payments")
        if not isinstance(raw, dict) or "data" not in raw or not isinstance(raw["data"], list):
            return raw
 
        payments = []
        for payment in raw.get("data", []):
            attrs = payment.get("attributes", {})
            reserve_line = attrs.get("reserveLine") or {}
            payments.append(
                {
                    "status": (attrs.get("status") or {}).get("name"),
                    "subtype": (attrs.get("subtype") or {}).get("name"),
                    "payment_type": (attrs.get("paymentType") or {}).get("name"),
                    "coverage": (attrs.get("coverage") or {}).get("name"),
                    "cost_category": (reserve_line.get("costCategory") or {}).get("name"),
                    "cost_type": (reserve_line.get("costType") or {}).get("name"),
                    "exposure": (reserve_line.get("exposure") or {}).get("displayName"),
                    "amounts": self._transaction_amounts(attrs.get("lineItems")),
                    "eroding": attrs.get("eroding"),
                    "create_time": attrs.get("createTime"),
                    "created_via": (attrs.get("createdVia") or {}).get("name"),
                }
            )
 
        payments = self._sort_list_of_dicts(payments, ["create_time", "coverage", "cost_type"])
        return {"count": len(payments), "payments": payments}
 
    def get_claim_checks_summary(self, claim_id: str) -> Union[Dict[str, Any], str]:
        safe_claim = urllib.parse.quote(str(claim_id), safe="%")
        raw = self.get_json(f"rest/claim/v1/claims/{safe_claim}/checks")
        if not isinstance(raw, dict) or "data" not in raw or not isinstance(raw["data"], list):
            return raw
 
        checks = []
        for check in raw.get("data", []):
            attrs = check.get("attributes", {})
            gross = attrs.get("grossAmount") or {}
            address = attrs.get("mailingAddress") or {}
            payees = []
            for payee in attrs.get("payees") or []:
                contact = payee.get("contact") or {}
                payees.append(
                    {
                        "name": contact.get("displayName"),
                        "payee_type": (payee.get("payeeType") or {}).get("name"),
                    }
                )
            checks.append(
                {
                    "status": (attrs.get("status") or {}).get("name"),
                    "gross_amount": gross.get("amount"),
                    "currency": gross.get("currency"),
                    "pay_to": attrs.get("payTo"),
                    "mail_to": attrs.get("mailTo"),
                    "mailing_address": address.get("displayName"),
                    "payees": payees,
                    "scheduled_send_date": attrs.get("scheduledSendDate"),
                }
            )
 
        checks = self._sort_list_of_dicts(checks, ["scheduled_send_date", "pay_to", "status"])
        return {"count": len(checks), "checks": checks}
 
    @staticmethod
    def _pdf_base64_to_text(pdf_base64: str) -> Optional[str]:
        try:
            from pypdf import PdfReader
        except ImportError:
            return None
 
        try:
            pdf_stream = io.BytesIO(base64.b64decode(pdf_base64))
            reader = PdfReader(pdf_stream)
            text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
            return text or None
        except Exception:
            return None
 
    def _get_document_text_content(self, claim_id: str, document_id: str) -> dict:
        safe_claim = urllib.parse.quote(str(claim_id), safe="%")
        safe_document = urllib.parse.quote(str(document_id), safe="%")
        raw = self.get_json(f"rest/claim/v1/claims/{safe_claim}/documents/{safe_document}/content")
 
        if not isinstance(raw, dict):
            return {"document_text": None, "fetch_status": "unexpected_content_response"}
        if raw.get("error"):
            return {"document_text": None, "fetch_status": "content_api_failed", "content_error": raw}
 
        contents = ((raw.get("data") or {}).get("attributes") or {}).get("contents")
        if not contents:
            return {"document_text": None, "fetch_status": "contents_missing"}
 
        text = self._pdf_base64_to_text(contents)
        return {
            "document_text": text,
            "fetch_status": "success" if text else "text_extraction_failed",
        }
 
    @staticmethod
    def _pattern_to_query(pattern: str) -> str:
        return re.sub(r"\s*\|\s*", " ", str(pattern or "")).strip()
 
    @staticmethod
    def _tokenize_for_similarity(text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", str(text or "").lower())
 
    @staticmethod
    def _chunk_document_text(text: str, *, max_chunk_chars: int = 1200) -> list[str]:
        if not text:
            return []
 
        chunks: list[str] = []
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        for paragraph in paragraphs:
            if len(paragraph) <= max_chunk_chars:
                chunks.append(paragraph)
                continue
 
            lines = paragraph.splitlines()
            window = 3
            step = max(window - 1, 1)
            for index in range(0, len(lines), step):
                chunk = "\n".join(lines[index : index + window]).strip()
                if chunk:
                    chunks.append(chunk)
        return chunks
 
    @staticmethod
    def _tfidf_vector(terms: Counter[str], *, doc_frequency: Counter[str], corpus_size: int) -> dict[str, float]:
        vector: dict[str, float] = {}
        for term, term_frequency in terms.items():
            inverse_doc_frequency = math.log((1 + corpus_size) / (1 + doc_frequency[term])) + 1
            vector[term] = term_frequency * inverse_doc_frequency
        return vector
 
    @staticmethod
    def _cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
        if not left or not right:
            return 0.0
        shared_terms = set(left) & set(right)
        if not shared_terms:
            return 0.0
        dot_product = sum(left[term] * right[term] for term in shared_terms)
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot_product / (left_norm * right_norm)
 
    @classmethod
    def _similarity_search_document_text(
        cls,
        query: str,
        text: str,
        *,
        max_matches: int = 8,
        min_score: float = 0.08,
    ) -> list[str]:
        chunks = cls._chunk_document_text(text)
        if not query or not chunks:
            return []
 
        chunk_terms = [Counter(cls._tokenize_for_similarity(chunk)) for chunk in chunks]
        doc_frequency: Counter[str] = Counter()
        for terms in chunk_terms:
            for term in terms:
                doc_frequency[term] += 1
 
        query_vector = cls._tfidf_vector(
            Counter(cls._tokenize_for_similarity(query)),
            doc_frequency=doc_frequency,
            corpus_size=len(chunk_terms),
        )
        if not query_vector:
            return []
 
        scored_chunks: list[tuple[str, float]] = []
        for chunk, terms in zip(chunks, chunk_terms):
            chunk_vector = cls._tfidf_vector(
                terms,
                doc_frequency=doc_frequency,
                corpus_size=len(chunk_terms),
            )
            score = cls._cosine_similarity(query_vector, chunk_vector)
            if score >= min_score:
                scored_chunks.append((chunk, score))
 
        scored_chunks.sort(key=lambda item: item[1], reverse=True)
        return [chunk for chunk, _ in scored_chunks[:max_matches]]
 
    def get_claim_document_searches_summary(
        self,
        claim_id: str,
        patterns: tuple[str, ...] = DEFAULT_AUTO_DOCUMENT_QUERIES,
    ) -> dict:
        safe_claim = urllib.parse.quote(str(claim_id), safe="%")
        documents_response = self.get_json(f"rest/claim/v1/claims/{safe_claim}/documents")
        if not isinstance(documents_response, dict):
            return {
                "claim_id": claim_id,
                "default_profile": "auto_insurance",
                "queries": list(patterns),
                "error": "unexpected_documents_response",
                "results": [
                    {
                        "claim_id": claim_id,
                        "pattern": pattern,
                        "pdf_document_count": 0,
                        "matched_count": 0,
                        "matches": [],
                        "no_matches": True,
                    }
                    for pattern in patterns
                ],
            }
        if documents_response.get("error"):
            return {
                "claim_id": claim_id,
                "default_profile": "auto_insurance",
                "queries": list(patterns),
                "error": documents_response,
                "results": [
                    {
                        "claim_id": claim_id,
                        "pattern": pattern,
                        "pdf_document_count": 0,
                        "matched_count": 0,
                        "matches": [],
                        "no_matches": True,
                    }
                    for pattern in patterns
                ],
            }
 
        pdf_documents = []
        extraction_failures = []
        for document in documents_response.get("data", []):
            attrs = document.get("attributes", {})
            if attrs.get("mimeType") != "application/pdf" or not attrs.get("id"):
                continue
            document_text = self._get_document_text_content(claim_id, attrs["id"])
            text = document_text.get("document_text")
            if not text:
                extraction_failures.append(
                    {
                        "name": attrs.get("name"),
                        "fetch_status": document_text.get("fetch_status"),
                    }
                )
                continue
            pdf_documents.append({"name": attrs.get("name"), "text": text})
 
        results = []
        for pattern in patterns:
            query = self._pattern_to_query(pattern)
            matches = []
            for document in pdf_documents:
                snippets = self._similarity_search_document_text(query, document["text"])
                if snippets:
                    matches.append({"name": document["name"], "snippets": snippets})
            results.append(
                {
                    "claim_id": claim_id,
                    "pattern": pattern,
                    "pdf_document_count": len(pdf_documents) + len(extraction_failures),
                    "matched_count": len(matches),
                    "matches": matches,
                    "no_matches": len(matches) == 0,
                    "extraction_failures": extraction_failures,
                }
            )
 
        return {
            "claim_id": claim_id,
            "default_profile": "auto_insurance",
            "queries": list(patterns),
            "results": results,
        }
 
    def search_claim_documents_summary(self, claim_id: str, pattern: str) -> dict:
        summary = self.get_claim_document_searches_summary(claim_id, (pattern,))
        results = summary.get("results") if isinstance(summary, dict) else None
        if isinstance(results, list) and results:
            return results[0]
        return {
            "claim_id": claim_id,
            "pattern": pattern,
            "pdf_document_count": 0,
            "matched_count": 0,
            "matches": [],
            "no_matches": True,
            "error": summary.get("error") if isinstance(summary, dict) else "unexpected_documents_response",
        }
 
    def get_claim_state_payload(self, claim_id: str) -> dict:
        claim_id = self.resolve_claim_id_by_number(claim_id)
        return {
            "claim_details": self.get_claim_details_summary(claim_id),
            "policy_details": self.get_claim_policy_summary(claim_id),
            "activities": self.get_claim_activities_summary(claim_id),
            "notes": self.get_claim_notes_summary(claim_id),
            "history_events": self.get_claim_history_events_summary(claim_id),
        }
 
    def get_claim_background_context(self, claim_id: str) -> dict:
        claim_id = self.resolve_claim_id_by_number(claim_id)
        return {
            **self.get_claim_state_payload(claim_id),
            "exposures": self.get_claim_exposures_summary(claim_id),
            "contacts": self.get_claim_contacts_summary(claim_id),
            "vehicle_incidents": self.get_claim_vehicle_incidents_summary(claim_id),
            "reserves": self.get_claim_reserves_summary(claim_id),
            "payments": self.get_claim_payments_summary(claim_id),
            "checks": self.get_claim_checks_summary(claim_id),
            "document_searches": self.get_claim_document_searches_summary(claim_id),
        }
 
    def get_group_summary(self, group_ref: Any) -> Union[Dict[str, Any], str]:
        if isinstance(group_ref, dict):
            group_uri = group_ref.get("uri")
            group_id = group_ref.get("id")
        elif isinstance(group_ref, str):
            group_uri = group_ref if group_ref.startswith("/") else None
            group_id = group_ref if group_uri is None else None
        else:
            return {}
 
        safe_group = urllib.parse.quote(str(group_id), safe="%")
        raw = self.get_json(f"rest/admin/v1/groups/{safe_group}")
 
        if not isinstance(raw, dict):
            print(f"Error: {raw}")
            return raw
        if raw.get("error"):
            print(f"Error: {raw}")
            return raw
 
        data = raw.get("data", {}) if isinstance(raw, dict) else {}
        attrs = data.get("attributes", {}) if isinstance(data, dict) else {}
        supervisor = attrs.get("supervisor")
 
        group_type = attrs.get("groupType")
        parent = attrs.get("parent")
 
        return {
            "group_id": attrs.get("id") or self._nested_id(group_ref),
            "group_name": attrs.get("displayName") or attrs.get("name") or self._nested_name(group_ref),
            "group_type_code": self._nested_code(group_type),
            "group_type_name": self._nested_name(group_type),
            "parent_group_id": self._nested_id(parent),
            "parent_group_name": self._nested_name(parent),
            "supervisor_id": self._nested_id(supervisor),
            "supervisor_name": self._nested_name(supervisor),
        }
 
    def get_claim_identity_summary(self, claim_id: str) -> Union[Dict[str, Any], str]:
        claim_id = self.resolve_claim_id_by_number(claim_id)
        safe_claim = urllib.parse.quote(str(claim_id), safe="%")
        raw = self.get_json(f"rest/claim/v1/claims/{safe_claim}")
        data = raw.get("data", {}) if isinstance(raw, dict) else {}
        attrs = data.get("attributes", {}) if isinstance(data, dict) else {}
 
        if not isinstance(raw, dict):
            return raw
        if raw.get("error"):
            return raw
 
        assigned_user = attrs.get("assignedUser")
        assigned_group = attrs.get("assignedGroup")
        lob_code = attrs.get("lobCode")
        group_summary = self.get_group_summary(assigned_group) if assigned_group else {}
        if not isinstance(group_summary, dict):
            group_summary = {}
 
        supervisor_id = group_summary.get("supervisor_id")
        supervisor_name = group_summary.get("supervisor_name")
        if supervisor_id is None and not supervisor_name:
            claim_supervisor = attrs.get("supervisor") or attrs.get("claimSupervisor")
            supervisor_id = self._nested_id(claim_supervisor)
            supervisor_name = self._nested_name(claim_supervisor)
 
        claim_status = self._nested_name(attrs.get("state")) or attrs.get("claim_status")
        loss_type = self._nested_name(attrs.get("lossType"))
 
        return {
            "claim_id": claim_id,
            "claim_number": attrs.get("claimNumber") or attrs.get("claim_number"),
            "policy_number": attrs.get("policyNumber") or attrs.get("policy_number"),
            "claim_status": claim_status,
            "is_open_claim": str(claim_status or "").strip().lower() != "closed",
            "adjuster_id": self._nested_id(assigned_user),
            "adjuster_name": self._nested_name(assigned_user) or attrs.get("adjuster"),
            "assigned_group_id": group_summary.get("group_id") or self._nested_id(assigned_group),
            "assigned_group_name": group_summary.get("group_name") or self._nested_name(assigned_group),
            "supervisor_id": supervisor_id,
            "supervisor_name": supervisor_name,
            "line_of_business_code": self._nested_code(lob_code),
            "line_of_business_name": self._nested_name(lob_code),
            "claim_type": loss_type,
            "loss_type": loss_type,
            "loss_cause": self._nested_name(attrs.get("lossCause")),
            "jurisdiction": self._nested_name(attrs.get("jurisdiction")),
            "reported_date": attrs.get("reportedDate"),
            "loss_date": attrs.get("lossDate"),
        }
 
    def compute_claim_state_hash(self, claim_id: str) -> str:
        payload = self.get_claim_state_payload(claim_id)
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()