# Repo Audit Rule

When auditing this repository:

- First map the current entrypoints, routers, services, models, storage helpers, templates, and frontend modules.
- Then determine what already supports the target product.
- Then identify what is missing, broken, duplicated, or misleadingly named.
- Do not assume a feature exists because the file name sounds correct.
- Check whether outputs are real or placeholders.
- Check whether run IDs, version IDs, and persistence paths are real and linked.

Always inspect:
- entrypoint and router registration
- mutation/version service ownership
- result persistence
- optimizer boundary
- AI routing policy
- storage/path consistency
- import consistency

Output issues grouped into:
- Critical gaps
- Important gaps
- Cleanup and naming consistency issues