# Security policy

This app can unlock a car and open a gate, so security reports are taken seriously.

* **Report privately** through GitHub: *Security → Report a vulnerability* on this repository (private advisories). Please do not open a public issue for anything exploitable.
* Include the version/commit, what you did, and what you expected. A proof of concept against your own instance is welcome; do not test against other people's cars or accounts.
* There is no bug bounty; fixes are made on a best-effort basis and credited if you wish.

In scope: authentication/authorization bypass, secret leakage, command injection, XSS, SSRF, anything that lets someone other than the owner send commands or read data. Hardening ideas (CSP, containers, rate limits) are welcome as normal issues or pull requests.

See [docs/security.md](docs/security.md) for the built-in protections and the recommended deployment.
