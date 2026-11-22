# Security policy

## Reporting a vulnerability in LLMPosture

If you find a security issue in LLMPosture itself (for example, a way for a
malicious target endpoint to attack the scanner operator, or a flaw in
report generation), please report it privately:

- Open a GitHub security advisory at
  https://github.com/RahilSahu/llmposture/security/advisories/new, or
- Email the maintainer via the address on the GitHub profile.

Please do not open a public issue for an unpatched vulnerability. Reports
are acknowledged as quickly as possible; fixes are released and credited
unless you prefer to stay anonymous.

## Supported versions

Only the latest release is supported with security fixes.

## Using LLMPosture responsibly

LLMPosture is a testing tool for systems you own or are authorised to test.

- Run it only against models, endpoints and accounts that are yours, or
  that you have explicit written authorisation to assess.
- Use your own API keys. Keys are read from environment variables and are
  never logged by the tool.
- All probes use benign canaries by design. Do not modify probes to elicit
  real harmful content; that is outside the project's scope and may violate
  the terms of the services you test.
- Findings about a third-party product belong to that product's own
  disclosure process, not to this repository's issue tracker.
