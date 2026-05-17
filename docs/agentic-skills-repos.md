Here are the strongest, most relevant GitHub collections for Agent Skills (SKILL.md format) tailored to your three roles. These stand out based on popularity (stars/activity), focus on production-grade practices, modularity, and direct relevance.
1. Product Owner (Decompose briefs into epics/milestones, user stories, backlog management, PRDs)
Top recommendations (prioritized for decomposition, agile practices, and requirements breakdown):

Agile-V/agile_v_skills (especially agile-v-product-owner and related skills like requirement-architect)
Strongest match for your use case. Dedicated Product Owner skill for epic decomposition, backlog refinement, traceable requirements, sprint planning, and user stories. Part of a full verifiable Agile framework with human gates and traceability. Excellent for turning high-level briefs into structured epics/milestones.
deanpeters/Product-Manager-Skills
Comprehensive PM-focused collection (47+ skills) with battle-tested frameworks for PRDs, strategy, backlog management, and decomposition. Highly practical for AI agents acting as Product Owners/Managers.
mattpocock/skills (skills like to-prd, to-issues, grill-with-docs, grill-me)
Excellent for alignment, turning conversations into PRDs/specs, breaking into issues/epics, and domain modeling. Real-engineer focus; pairs well with grilling for thorough decomposition.

Honorable mentions: alirezarezvani/claude-skills (cs-agile-product-owner agent/skill) and Anthropics' official examples for patterns.
2. Software Engineer (Production-grade code writing)
These emphasize architecture, TDD, incremental implementation, quality gates, and real engineering (not "vibe coding").

addyosmani/agent-skills
One of the best for production-grade work. Covers the full lifecycle: spec-driven dev, planning/task breakdown, incremental implementation, TDD, code simplification, security, performance, reviews, etc. Structured workflows with quality gates that senior engineers use.
mattpocock/skills (engineering skills: tdd, diagnose, improve-codebase-architecture, grill-with-docs, zoom-out, etc.)
Practical, daily-use skills from a real engineer. Strong on TDD/red-green-refactor, architecture improvement, debugging, and avoiding codebase entropy. Very actionable.
anthropics/skills (official examples) + general engineering patterns in it
Foundational reference with strong examples of structured skills. Use as a base or inspiration; many community repos build on it.

Other strong option: Look for skills in addyosmani or mattpocock for specific domains (frontend, API design, etc.).
3. QA (Evaluate, test, run, review code)
Focus on testing, code review, verification, red-teaming, and automation.

addyosmani/agent-skills (code-review-and-quality, test-driven-development, debugging-and-error-recovery, browser-testing, security-and-hardening, test-engineer agent)
Excellent multi-axis reviews, quality gates, TDD support, and verification workflows. Includes dedicated test engineer persona.
fugazi/test-automation-skills-agents
Targeted QA/Testing library for automation engineers. Practical, production-oriented test skills and agents.
jaktestowac/awesome-copilot-for-testers (or similar tester-focused awesome lists)
Skills for code review, test planning, and quality assurance in AI-assisted testing contexts.

Additional strong picks: Anthropics/skills often includes QA sections (e.g., assume problems and hunt for them); mattpocock has diagnostic/TDD support.
Quick Tips for Using These

Many support npx skills add <repo> for easy installation into Claude Code, Copilot, Cursor, etc.
Start by cloning or installing the full repo, then selectively use/copy relevant SKILL.md folders to avoid context bloat.
Combine them: Use Product Owner skills first for decomposition, then Engineer for implementation, then QA for verification (orchestrate via agents or custom instructions).
Check awesome lists like heilcheng/awesome-agent-skills or kodustech/awesome-agent-skills for more discovery.

These collections represent the current state-of-the-art in structured, reusable LLM guidance for these roles. Test a few skills in your environment, adapt them to your stack/conventions, and iterate. Let me know if you want help evaluating a specific repo or extracting/ customizing particular skills!       