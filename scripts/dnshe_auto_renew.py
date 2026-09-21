#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


DATE_FORMAT = "%Y-%m-%d %H:%M"
DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)
API_BASE = "https://api005.dnshe.com/index.php?m=domain_hub"


@dataclass
class ManagedDomain:
    domain: str
    expires_at: datetime
    renew_before_days: int

    @property
    def renew_at(self) -> datetime:
        return self.expires_at - timedelta(days=self.renew_before_days)


class DNSHEClient:
    def __init__(self, api_key: str, api_secret: str) -> None:
        self.headers = {
            "X-API-Key": api_key,
            "X-API-Secret": api_secret,
            "Content-Type": "application/json",
            "User-Agent": "dnshe-auto-renew/1.0",
        }

    def _request(self, endpoint: str, action: str, method: str = "GET", payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        url = f"{API_BASE}&endpoint={endpoint}&action={action}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, headers=self.headers, data=data, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DNSHE HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"DNSHE network error: {exc}") from exc

    def list_subdomains(self) -> List[Dict[str, Any]]:
        response = self._request("subdomains", "list")
        if not response.get("success"):
            raise RuntimeError(f"DNSHE list failed: {response}")
        return response.get("subdomains", [])

    def renew_subdomain(self, subdomain_id: int) -> Dict[str, Any]:
        response = self._request(
            "subdomains",
            "renew",
            method="POST",
            payload={"subdomain_id": subdomain_id},
        )
        if not response.get("success"):
            raise RuntimeError(f"DNSHE renew failed: {response}")
        return response


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Weekly DNSHE domain renewal helper.")
    parser.add_argument("--state", default="state/domains-state.json", help="Path to state JSON file.")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate and log actions without renewing.")
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def parse_datetime(value: str) -> datetime:
    cleaned = value.strip()
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Unsupported datetime format: {value}")


def parse_domain_variable() -> List[str]:
    raw = require_env("DNSHE_DOMAINS")
    domains = [line.strip() for line in raw.splitlines() if line.strip()]
    if not domains:
        raise RuntimeError("DNSHE_DOMAINS is empty.")
    return domains


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"domains": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, raw_state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def find_subdomain_map(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    mapping: Dict[str, Dict[str, Any]] = {}
    for item in items:
        full_domain = item.get("full_domain")
        if full_domain:
            mapping[full_domain] = item
    return mapping


def derive_initial_expiration(created_at: str) -> datetime:
    return parse_datetime(created_at) + timedelta(days=365)


def build_managed_domains(domain_names: List[str], subdomain_map: Dict[str, Dict[str, Any]], state: Dict[str, Any]) -> Tuple[List[ManagedDomain], bool]:
    managed: List[ManagedDomain] = []
    state_changed = False
    stored_domains = state.setdefault("domains", {})

    for domain_name in domain_names:
        matched = subdomain_map.get(domain_name)
        if not matched:
            raise RuntimeError(f"Domain not found in DNSHE account: {domain_name}")

        item = stored_domains.get(domain_name, {})
        expires_at = item.get("expires_at")
        if expires_at:
            expires_dt = parse_datetime(expires_at)
        else:
            created_at = matched.get("created_at")
            if not created_at:
                raise RuntimeError(f"DNSHE response missing created_at for {domain_name}")
            expires_dt = derive_initial_expiration(created_at)
            item = {
                "expires_at": expires_dt.strftime(DATE_FORMAT),
                "renew_before_days": int(item.get("renew_before_days", 175)),
                "source": "created_at_plus_365_days",
            }
            stored_domains[domain_name] = item
            state_changed = True

        renew_before_days = int(item.get("renew_before_days", 175))
        item["renew_before_days"] = renew_before_days
        managed.append(
            ManagedDomain(
                domain=domain_name,
                expires_at=expires_dt,
                renew_before_days=renew_before_days,
            )
        )

    active_domains = set(domain_names)
    stale_domains = [name for name in list(stored_domains.keys()) if name not in active_domains]
    for name in stale_domains:
        del stored_domains[name]
        state_changed = True

    return managed, state_changed


def update_state_expiration(state: Dict[str, Any], domain_name: str, new_expires_at: str) -> bool:
    item = state.setdefault("domains", {}).setdefault(domain_name, {})
    if item.get("expires_at") == new_expires_at:
        return False
    item["expires_at"] = new_expires_at
    item["source"] = "dnshe_renew_response"
    item["renew_before_days"] = int(item.get("renew_before_days", 175))
    return True


def main() -> int:
    args = parse_args()
    state_path = Path(args.state).resolve()

    api_key = require_env("DNSHE_API_KEY")
    api_secret = require_env("DNSHE_API_SECRET")
    domain_names = parse_domain_variable()
    client = DNSHEClient(api_key, api_secret)

    now = datetime.now(timezone.utc)
    state = load_state(state_path)
    subdomain_map = find_subdomain_map(client.list_subdomains())
    managed_domains, updated = build_managed_domains(domain_names, subdomain_map, state)

    renewed_count = 0

    print(f"UTC now: {now.strftime(DATE_FORMAT)}")
    for managed in managed_domains:
        matched = subdomain_map[managed.domain]
        print(
            f"[CHECK] {managed.domain} expires_at={managed.expires_at.strftime(DATE_FORMAT)} "
            f"renew_at={managed.renew_at.strftime(DATE_FORMAT)}"
        )

        if now < managed.renew_at:
            print(f"[SKIP] {managed.domain} has not entered renewal window yet.")
            continue

        if args.dry_run:
            print(f"[DRY-RUN] Would renew {managed.domain} with subdomain_id={matched['id']}.")
            continue

        result = client.renew_subdomain(int(matched["id"]))
        new_expires_at = result.get("new_expires_at")
        if not new_expires_at:
            raise RuntimeError(f"Renew response missing new_expires_at for {managed.domain}: {result}")

        changed = update_state_expiration(state, managed.domain, new_expires_at)
        updated = updated or changed
        renewed_count += 1
        print(
            f"[RENEWED] {managed.domain} previous_expires_at={result.get('previous_expires_at')} "
            f"new_expires_at={new_expires_at} remaining_days={result.get('remaining_days')}"
        )

    if updated and not args.dry_run:
        save_state(state_path, state)
        print(f"[WRITE] Updated {state_path}")

    if renewed_count == 0:
        print("[DONE] No domains were renewed in this run.")
    else:
        print(f"[DONE] Renewed {renewed_count} domain(s).")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        raise
