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

Prepare these two values:

- `DNSHE_API_KEY`
- `DNSHE_API_SECRET`

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
4. Once imported, GitHub creates a private repository owned by you. All subsequent Secrets, Variables, and workflow configuration are done on this repo's page.

### Step 2: Add GitHub Secrets and Variables

Go to:

- `Settings -> Secrets and variables -> Actions`

Add these Secrets:

- `DNSHE_API_KEY`
- `DNSHE_API_SECRET`

Add this Variable:

- `DNSHE_DOMAINS`

### Step 3: Configure Domains

`DNSHE_DOMAINS` takes one domain per line:

```text
abc88.cc.cd
12366.cc.cd
```

### Step 4: Run the Workflow Manually

Open the `Actions` tab and manually run `DNSHE Auto Renew`.

The first run checks the domains and generates `state/domains-state.json`. After that, the workflow runs automatically every week.

## Domain Management

### Format

One domain per line. Add a line for a new domain, remove a line to delete:

```text
abc88.cc.cd
12366.cc.cd
444.cc.cd
```

### Adding Domains

Simply append new domains to `DNSHE_DOMAINS`. The next workflow run will automatically detect new domains, fetch their `created_at` from the DNSHE API, calculate the initial expiration date (`created_at + 365` days), and save the result to `state/domains-state.json`. No manual registration date or expiration date needed.

### Why No Manual Expiration Date

- On first discovery, the initial expiration is calculated as `created_at + 365` days
- After a successful renewal, the state is updated with the `new_expires_at` from the API response
- Expiration rolls forward automatically — no need to update dates every year

## Renewal Rules

Default behavior:

- Free renewal window: `175` days before expiration
- Checked once per week
- Renewal is only requested when a domain enters the renewal window

## Regenerating API Credentials

If you regenerate your DNSHE API credentials, simply update the GitHub Secrets:

- `DNSHE_API_KEY`
- `DNSHE_API_SECRET`

## Changing the Schedule

Edit the `cron` field in `.github/workflows/dnshe-auto-renew.yml`. Currently runs weekly in UTC.

## File Reference

- `scripts/dnshe_auto_renew.py` — Renewal script
- `.github/workflows/dnshe-auto-renew.yml` — Weekly GitHub Actions workflow
- `state/domains-state.json` — Auto-generated state file

## Official Links

- [DNSHE Dashboard](https://my.dnshe.com)
- [DNSHE API Manual](https://my.dnshe.com/knowledgebase/1/Free-Domain-Name-Service-API-User-Manual.html)

## License

MIT License
