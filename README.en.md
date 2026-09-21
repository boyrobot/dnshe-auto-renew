<div align="center">
  <h1>DNSHE Free Domain Auto Renew</h1>
  <p>Automatically checks your DNSHE domains weekly and renews them for free before expiration</p>
  <p><a href="README.md">简体中文</a> | English</p>
  <p>
    <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776AB">
    <img alt="Platform" src="https://img.shields.io/badge/platform-GitHub%20Actions-2088FF">
    <img alt="License" src="https://img.shields.io/badge/license-MIT-111827">
    <img alt="Schedule" src="https://img.shields.io/badge/schedule-Weekly-22c55e">
  </p>
</div>

> Deploy in 3 minutes, then your DNSHE free domains will be checked and renewed automatically every week.

## 3-Minute Deployment

### Step 0: Get DNSHE API Credentials

Open:

- https://my.dnshe.com

Prepare these two values. You will put them in the account JSON:

- API Key
- API Secret

### Step 1: Import as a Private Repository via GitHub Importer

1. Log in to GitHub and open <https://github.com/new/import>
2. Fill in the following:

| Field | Value |
| --- | --- |
| `Your old repository's clone URL` | `https://github.com/OUBIGFA/dnshe-auto-renew` |
| `Owner` | Your GitHub account |
| `Repository name` | Your repo name, e.g. `my-dnshe-auto-renew` |
| `Privacy` | Select `Private` |

3. Click `Begin import` and wait for it to finish (usually tens of seconds to a few minutes)
4. Once imported, GitHub creates a private repository owned by you. All subsequent Secret and workflow configuration are done on this repo's page.

### Step 2: Add a GitHub Secret

Go to:

- `Settings -> Secrets and variables -> Actions`

Add this Secret:

- `DNSHE_ACCOUNTS`

The value is one JSON document and can list multiple accounts. `accounts.example.json` in the repo is the same shape; replace the placeholders with your own credentials.

### Step 3: Configure Accounts and Domains

Example `DNSHE_ACCOUNTS` value:

```json
{
  "accounts": [
    {
      "name": "account-a",
      "api_key": "YOUR_API_KEY",
      "api_secret": "YOUR_API_SECRET",
      "domains": ["abc88.cc.cd", "12366.cc.cd"]
    },
    {
      "name": "account-b",
      "api_key": "YOUR_API_KEY",
      "api_secret": "YOUR_API_SECRET",
      "domains": ["444.cc.cd"],
      "renew_before_days": 175
    }
  ]
}
```

- `name` must be unique in this config. It is used as the log prefix and the state key.
- `domains` must be unique globally, including across accounts.
- `renew_before_days` is optional and defaults to `175`. When set, it overrides the previous value stored in state.

For local debugging, save the same JSON to a file and run:

```bash
python scripts/dnshe_auto_renew.py --config accounts.json --dry-run
```

### Step 4: Run the Workflow Manually

Open the `Actions` tab and manually run `DNSHE Auto Renew`.

The first run checks the domains and generates `state/domains-state.json`. After that, the workflow runs automatically every week.

## Domain Management

### Format

Each account's `domains` field is an array. Add an entry for a new domain, remove an entry to delete it:

```json
"domains": ["abc88.cc.cd", "12366.cc.cd", "444.cc.cd"]
```

Add another object to `accounts` for each extra DNSHE account, with that account's own API credentials. A failure in one account does not stop the others. The process exits with code `1` if any account failed.

### Adding Domains

Simply append new domains to that account's `domains`. The next workflow run will automatically detect new domains, fetch their `created_at` from the DNSHE API, calculate the initial expiration date (`created_at + 365` days), and save the result to `state/domains-state.json`. No manual registration date or expiration date needed. State is nested under `accounts.<name>.domains`. If the repo still has the old flat `domains` state, the script matches those domains into the configured accounts so existing expiration times are kept.

### Why No Manual Expiration Date

- On first discovery, the initial expiration is calculated as `created_at + 365` days
- After a successful renewal, the state is updated with the `new_expires_at` from the API response
- Expiration rolls forward automatically — no need to update dates every year

## Renewal Rules

Default behavior:

- Free renewal window: `175` days before expiration, overridable per account with `renew_before_days`
- Checked once per week
- Renewal is only requested when a domain enters the renewal window

## Legacy Environment Variable Fallback

When neither `--config` nor `DNSHE_ACCOUNTS` is set, the script still reads these three environment variables and treats them as a single account named `default`:

- `DNSHE_API_KEY`
- `DNSHE_API_SECRET`
- `DNSHE_DOMAINS` (one domain per line)

Priority is: `--config` file > `DNSHE_ACCOUNTS` environment variable > the three legacy variables above. The GitHub Actions workflow passes only the `DNSHE_ACCOUNTS` secret.

## Regenerating API Credentials

If you regenerate your DNSHE API credentials, update `api_key` and `api_secret` for that account inside the `DNSHE_ACCOUNTS` secret.

## Changing the Schedule

Edit the `cron` field in `.github/workflows/dnshe-auto-renew.yml`. Currently runs weekly in UTC.

## File Reference

- `scripts/dnshe_auto_renew.py` — Renewal script
- `accounts.example.json` — Multi-account JSON template, with no real credentials
- `.github/workflows/dnshe-auto-renew.yml` — Weekly GitHub Actions workflow
- `state/domains-state.json` — Auto-generated state file

## Official Links

- [DNSHE Dashboard](https://my.dnshe.com)
- [DNSHE API Manual](https://my.dnshe.com/knowledgebase/1/Free-Domain-Name-Service-API-User-Manual.html)

## License

MIT License
