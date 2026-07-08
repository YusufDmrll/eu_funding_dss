# Partner Directory Support

The app can now use an optional curated partner directory for outreach planning.

This is intentionally not blind partner scraping. The system does not invent organisation names. If no curated directory is configured, result details show a partner search profile: the roles and themes that should be considered for outreach.

## Directory file

Create this file when a verified or manually reviewed partner list is available:

```text
data/imports/partner_directory.csv
```

Use the template:

```text
data/imports/partner_directory_template.csv
```

Columns:

- `organization_name`
- `country`
- `organization_type`
- `sector`
- `roles`
- `themes`
- `website`
- `notes`
- `verified_status`
- `last_checked_utc`

Separate multiple roles or themes with semicolons, commas, or pipes.

## Example roles

- Port authority or terminal operator
- Grid, energy, or shore-power infrastructure partner
- Shipping, logistics, or port-community operator
- Recycling or materials processor
- Battery, manufacturing, or industrial value-chain partner
- Critical-infrastructure operator
- Security, cybersecurity, or resilience specialist
- SME or scale-up participant
- Research, testing, or validation partner

## Example themes

- critical materials / circularity
- port energy / green harbour
- maritime / logistics
- green energy / hydrogen
- security / resilience
- sme / scale-up innovation
- digital / automation

## Safety rules

- Add only organisations that have been manually checked or provided by a trusted source.
- Do not treat a directory match as consortium confirmation.
- Confirm partner eligibility, role, country rules, and consortium requirements in the official call documents.
- Do not commit private or commercially sensitive partner data unless sharing that data is intended.
