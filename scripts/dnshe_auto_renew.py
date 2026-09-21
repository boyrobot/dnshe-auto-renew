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
DEFAULT_RENEW_BEFORE_DAYS = 175
LEGACY_ACCOUNT_NAME = "default"


@dataclass
class Account:
    name: str
    api_key: str
    api_secret: str
    domains: List[str]
    renew_before_days: int | None = None


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
    parser.add_argument("--config", help="Path to accounts JSON file. Overrides DNSHE_ACCOUNTS.")
    parser.add_argument("--state", default="state/domains-state.json", help="Path to state JSON file.")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate and log actions without renewing.")
    return parser.parse_args()


def parse_datetime(value: str) -> datetime:
    cleaned = value.strip()
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Unsupported datetime format: {value}")


def _require_nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{label} must be a non-empty string.")
    return value.strip()


def _parse_renew_before_days(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"{label} must be an integer.")
    if value < 0:
        raise RuntimeError(f"{label} must be >= 0.")
    return value


def parse_accounts_config(payload: Any) -> List[Account]:
    if not isinstance(payload, dict):
        raise RuntimeError("Account config must be a JSON object.")
    raw_accounts = payload.get("accounts")
    if not isinstance(raw_accounts, list) or not raw_accounts:
        raise RuntimeError("Account config must contain a non-empty accounts list.")

    accounts: List[Account] = []
    seen_names = set()
    seen_domains = set()

    for index, raw in enumerate(raw_accounts):
        label = f"accounts[{index}]"
        if not isinstance(raw, dict):
            raise RuntimeError(f"{label} must be an object.")

        name = _require_nonempty_string(raw.get("name"), f"{label}.name")
        if name in seen_names:
            raise RuntimeError(f"Duplicate account name: {name}")
        seen_names.add(name)

        api_key = _require_nonempty_string(raw.get("api_key"), f"{label}.api_key")
        api_secret = _require_nonempty_string(raw.get("api_secret"), f"{label}.api_secret")

        raw_domains = raw.get("domains")
        if not isinstance(raw_domains, list) or not raw_domains:
            raise RuntimeError(f"{label}.domains must be a non-empty list.")

        domains: List[str] = []
        for domain_index, raw_domain in enumerate(raw_domains):
            domain = _require_nonempty_string(raw_domain, f"{label}.domains[{domain_index}]")
            if domain in seen_domains:
                raise RuntimeError(f"Duplicate domain across accounts: {domain}")
            seen_domains.add(domain)
            domains.append(domain)

        renew_before_days = None
        if "renew_before_days" in raw and raw.get("renew_before_days") is not None:
            renew_before_days = _parse_renew_before_days(
                raw.get("renew_before_days"),
                f"{label}.renew_before_days",
            )

        accounts.append(
            Account(
                name=name,
                api_key=api_key,
                api_secret=api_secret,
                domains=domains,
                renew_before_days=renew_before_days,
            )
        )

    return accounts


def load_legacy_account() -> List[Account]:
    api_key = os.getenv("DNSHE_API_KEY", "").strip()
    api_secret = os.getenv("DNSHE_API_SECRET", "").strip()
    raw_domains = os.getenv("DNSHE_DOMAINS", "")
    if not api_key or not api_secret or not raw_domains.strip():
        raise RuntimeError(
            "Missing account configuration. Provide --config, DNSHE_ACCOUNTS, "
            "or DNSHE_API_KEY / DNSHE_API_SECRET / DNSHE_DOMAINS."
        )

    domains = [line.strip() for line in raw_domains.splitlines() if line.strip()]
    if not domains:
        raise RuntimeError("DNSHE_DOMAINS is empty.")

    seen = set()
    for domain in domains:
        if domain in seen:
            raise RuntimeError(f"Duplicate domain across accounts: {domain}")
        seen.add(domain)

    return [
        Account(
            name=LEGACY_ACCOUNT_NAME,
            api_key=api_key,
            api_secret=api_secret,
            domains=domains,
        )
    ]


def load_accounts(config_path: str | None) -> List[Account]:
    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise RuntimeError(f"Config file not found: {config_path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in config file: {exc}") from exc
        return parse_accounts_config(payload)

    raw = os.getenv("DNSHE_ACCOUNTS")
    if raw is not None and raw.strip():
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in DNSHE_ACCOUNTS: {exc}") from exc
        return parse_accounts_config(payload)

    return load_legacy_account()


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"accounts": {}}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RuntimeError(f"State file must be a JSON object: {path}")
    return loaded


def save_state(path: Path, raw_state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _account_domains_state(state: Dict[str, Any], account_name: str) -> Dict[str, Any]:
    accounts_state = state.setdefault("accounts", {})
    if not isinstance(accounts_state, dict):
        raise RuntimeError("State field accounts must be an object.")
    account_state = accounts_state.setdefault(account_name, {})
    if not isinstance(account_state, dict):
        account_state = {}
        accounts_state[account_name] = account_state
    stored_domains = account_state.setdefault("domains", {})
    if not isinstance(stored_domains, dict):
        stored_domains = {}
        account_state["domains"] = stored_domains
    return stored_domains


def migrate_flat_state(state: Dict[str, Any], accounts: List[Account]) -> bool:
    """Move a legacy top-level domains map into accounts.<name>.domains.

    Domains are matched by name against the current config. Entries that do not
    belong to a configured account are dropped. Existing nested values win.
    """
    flat = state.get("domains")
    if not isinstance(flat, dict):
        return False

    domain_to_account = {domain: account.name for account in accounts for domain in account.domains}
    for domain, item in flat.items():
        account_name = domain_to_account.get(domain)
        if not account_name or not isinstance(item, dict):
            continue
        stored_domains = _account_domains_state(state, account_name)
        if domain not in stored_domains:
            stored_domains[domain] = item

    del state["domains"]
    return True


def prune_state(state: Dict[str, Any], accounts: List[Account]) -> bool:
    """Drop accounts and domains that are no longer in the config."""
    changed = False
    accounts_state = state.setdefault("accounts", {})
    if not isinstance(accounts_state, dict):
        state["accounts"] = {}
        return True

    configured = {account.name: set(account.domains) for account in accounts}
    for name in list(accounts_state.keys()):
        if name not in configured:
            del accounts_state[name]
            changed = True
            continue
        account_state = accounts_state.get(name)
        if not isinstance(account_state, dict):
            accounts_state[name] = {"domains": {}}
            changed = True
            continue
        stored_domains = account_state.get("domains")
        if not isinstance(stored_domains, dict):
            account_state["domains"] = {}
            changed = True
            continue
        for domain in list(stored_domains.keys()):
            if domain not in configured[name]:
                del stored_domains[domain]
                changed = True
    return changed


def find_subdomain_map(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    mapping: Dict[str, Dict[str, Any]] = {}
    for item in items:
        full_domain = item.get("full_domain")
        if full_domain:
            mapping[full_domain] = item
    return mapping


def derive_initial_expiration(created_at: str) -> datetime:
    return parse_datetime(created_at) + timedelta(days=365)


def build_managed_domains(
    domain_names: List[str],
    subdomain_map: Dict[str, Dict[str, Any]],
    stored_domains: Dict[str, Any],
    renew_before_days_override: int | None = None,
) -> Tuple[List[ManagedDomain], bool]:
    managed: List[ManagedDomain] = []
    state_changed = False

    for domain_name in domain_names:
        matched = subdomain_map.get(domain_name)
        if not matched:
            raise RuntimeError(f"Domain not found in DNSHE account: {domain_name}")

        item = stored_domains.get(domain_name, {})
        if not isinstance(item, dict):
            item = {}
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
                "renew_before_days": (
                    renew_before_days_override
                    if renew_before_days_override is not None
                    else int(item.get("renew_before_days", DEFAULT_RENEW_BEFORE_DAYS))
                ),
                "source": "created_at_plus_365_days",
            }
            stored_domains[domain_name] = item
            state_changed = True

        if renew_before_days_override is not None:
            renew_before_days = renew_before_days_override
        else:
            renew_before_days = int(item.get("renew_before_days", DEFAULT_RENEW_BEFORE_DAYS))
        if item.get("renew_before_days") != renew_before_days:
            item["renew_before_days"] = renew_before_days
            state_changed = True
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


def update_state_expiration(stored_domains: Dict[str, Any], domain_name: str, new_expires_at: str) -> bool:
    item = stored_domains.setdefault(domain_name, {})
    if not isinstance(item, dict):
        item = {}
        stored_domains[domain_name] = item
    if item.get("expires_at") == new_expires_at:
        return False
    item["expires_at"] = new_expires_at
    item["source"] = "dnshe_renew_response"
    item["renew_before_days"] = int(item.get("renew_before_days", DEFAULT_RENEW_BEFORE_DAYS))
    return True


def process_account(
    account: Account,
    state: Dict[str, Any],
    now: datetime,
    dry_run: bool,
) -> Tuple[int, bool]:
    client = DNSHEClient(account.api_key, account.api_secret)
    subdomain_map = find_subdomain_map(client.list_subdomains())
    stored_domains = _account_domains_state(state, account.name)
    managed_domains, updated = build_managed_domains(
        account.domains,
        subdomain_map,
        stored_domains,
        account.renew_before_days,
    )

    renewed_count = 0
    for managed in managed_domains:
        matched = subdomain_map[managed.domain]
        print(
            f"[CHECK] {account.name} {managed.domain} expires_at={managed.expires_at.strftime(DATE_FORMAT)} "
            f"renew_at={managed.renew_at.strftime(DATE_FORMAT)}"
        )

        if now < managed.renew_at:
            print(f"[SKIP] {account.name} {managed.domain} has not entered renewal window yet.")
            continue

        if dry_run:
            print(f"[DRY-RUN] {account.name} Would renew {managed.domain} with subdomain_id={matched['id']}.")
            continue

        result = client.renew_subdomain(int(matched["id"]))
        new_expires_at = result.get("new_expires_at")
        if not new_expires_at:
            raise RuntimeError(f"Renew response missing new_expires_at for {managed.domain}: {result}")

        changed = update_state_expiration(stored_domains, managed.domain, new_expires_at)
        updated = updated or changed
        renewed_count += 1
        print(
            f"[RENEWED] {account.name} {managed.domain} previous_expires_at={result.get('previous_expires_at')} "
            f"new_expires_at={new_expires_at} remaining_days={result.get('remaining_days')}"
        )

    return renewed_count, updated


def main() -> int:
    args = parse_args()
    state_path = Path(args.state).resolve()
    accounts = load_accounts(args.config)

    now = datetime.now(timezone.utc)
    state = load_state(state_path)
    updated = migrate_flat_state(state, accounts)
    updated = prune_state(state, accounts) or updated

    print(f"UTC now: {now.strftime(DATE_FORMAT)}")

    renewed_count = 0
    failed_accounts: List[str] = []
    for account in accounts:
        try:
            renewed, changed = process_account(account, state, now, args.dry_run)
            renewed_count += renewed
            updated = updated or changed
        except Exception as exc:
            failed_accounts.append(account.name)
            print(f"[ERROR] {account.name}: {exc}", file=sys.stderr)

    if updated and not args.dry_run:
        save_state(state_path, state)
        print(f"[WRITE] Updated {state_path}")

    if failed_accounts:
        print(
            f"[DONE] Renewed {renewed_count} domain(s); {len(failed_accounts)} account(s) failed.",
            file=sys.stderr,
        )
        return 1

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
