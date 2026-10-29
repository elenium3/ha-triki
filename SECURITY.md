# Security policy

## Scope

This integration talks to a Bluetooth Low Energy toy over Home Assistant's
Bluetooth stack. It has no cloud component, opens no network ports and stores
nothing but the token's Bluetooth address and the options you set.

Things that would count as a security issue:

- a crafted BLE notification that crashes or hangs Home Assistant;
- diagnostics or captures leaking data they should redact;
- a dependency problem introduced through this repository's CI configuration.

Things that are not in scope: the token's own protocol has no authentication, so
anyone in radio range can connect to an awake token. That is a property of the
device, not of this integration.

## Reporting

Please do not open a public issue for a vulnerability. Use GitHub's
[private vulnerability reporting](https://github.com/elenium3/ha-triki/security/advisories/new)
instead. You will get an acknowledgement within a week.

## Automated checks

Every pull request and a weekly schedule run ruff's security (`S`, bandit)
rules over the Python code, zizmor over the GitHub workflows, Gitleaks over the
history and CodeQL (`.github/workflows/ci.yml`, `security.yml`). Third-party
actions are pinned to commit SHAs; the test toolchain is pinned in
`requirements_test.txt`; Dependabot updates both and raises alerts for known
vulnerabilities.

The integration itself has no requirements beyond Home Assistant. The packages
the tests pull in (aiohttp and friends) are pinned by
`pytest-homeassistant-custom-component` to whatever the matching Home Assistant
release ships; findings there belong to Home Assistant core, not to this
repository.

## Supported versions

Only the latest release is supported. Home Assistant 2025.8 or newer is required
(see `hacs.json`).
