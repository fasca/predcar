Review the recent changes thoroughly before making any code changes. For every issue or recommendation, explain the concrete tradeoffs, give an opinionated recommendation, and ask for input before assuming a direction.

Evaluate in this order:

1. **Architecture review**: System design, component boundaries, dependency graph, data flow patterns, scaling concerns, single points of failure.

2. **Code quality review**: Code organization, DRY violations (be aggressive), error handling patterns, missing edge cases, technical debt hotspots, over/under-engineering.

3. **Test review**: Test coverage gaps (unit, integration), test quality, missing edge case coverage, untested failure modes.

4. **Performance review**: N+1 queries, memory usage, caching opportunities, slow code paths.

For each issue found:
- Describe the problem concretely with file and line references
- Present 2-3 options including "do nothing" where reasonable
- For each option: effort, risk, impact on other code, maintenance burden
- Give recommended option and why
- Ask whether to proceed before making changes

After each section, pause and ask for feedback before moving on.
