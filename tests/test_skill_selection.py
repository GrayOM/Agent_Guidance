"""A Skill repository is not one Skill, and installing all of it is not a setup.

`trailofbits/skills` holds 85 Skills. Installing every one put roughly 7,800 tokens of
names and descriptions into each Agent's context for a user who asked about two things,
including Skills for organisational-culture metrics and Lean proofs. These cover the three
rules that narrow it, the conflict handling, and the one-line report of what landed.
"""

import json
from pathlib import Path

import pytest

from grayom_agent_guidance.adapters.codex import AdapterError
from grayom_agent_guidance.adapters.json_support import (
    NON_PUBLISHED_DIRECTORIES, foreign_skill_names, skill_group,
)
from grayom_agent_guidance.core.multi_agent_plan import _with_skill_policy
from grayom_agent_guidance.core.skill_selection import (
    LIMIT_BY_MODE, SKIP_GROUP_FULL, SKIP_NAME_CLASH, SKIP_OVER_LIMIT, SKIP_REDUNDANT,
    SKIP_UNRELATED, SkillCandidate, group_quota, limit_for, select_skills,
)
from grayom_agent_guidance.models import (
    AgentType, Capability, Component, ComponentType, InstalledComponent, InterviewAnswer,
    InstallKind, InstallMethod, RecommendationPlan, SetupMode, SkillSelectionPolicy,
    WorkDomain,
)
from grayom_agent_guidance.sources.normalizer import CAPABILITY_KEYWORDS, mentions

SECURITY = {Capability.VULNERABILITY_RESEARCH, Capability.SECURITY_ANALYSIS}


def _candidate(name: str, description: str) -> SkillCandidate:
    return SkillCandidate(name=name, description=description, directory=name)


def _policy(limit: int = 6, capabilities=None) -> SkillSelectionPolicy:
    return SkillSelectionPolicy(capabilities=capabilities or SECURITY, limit=limit)


def _reasons(selection) -> dict[str, str]:
    return {decision.name: decision.reason for decision in selection.decisions}


# --- rule 1: only what the run asked for --------------------------------------------


def test_a_skill_speaking_to_no_requested_capability_is_left_out() -> None:
    selection = select_skills([
        _candidate("cve-triage", "Triages a CVE against the vulnerability database"),
        _candidate("culture-index", "Interprets organisational culture survey metrics"),
    ], _policy())

    assert selection.selected_names == ["cve-triage"]
    assert _reasons(selection)["culture-index"] == SKIP_UNRELATED
    assert selection.skipped_by_reason() == {SKIP_UNRELATED: 1}


def test_without_a_policy_the_repository_is_installed_as_before() -> None:
    """An update or a component carrying no policy must keep the previous behaviour."""
    component = Component(
        id="pack", name="Pack", type=ComponentType.SKILL,
        github_url="https://github.com/example/pack",
    )

    assert component.skill_selection is None


# --- rule 2: conflicts ---------------------------------------------------------------


def test_a_name_already_taken_by_another_component_is_not_installed_over() -> None:
    """Two Skills with one name are not discoverable; the Agent's own check flags it."""
    selection = select_skills(
        [_candidate("semgrep", "Runs semgrep for security analysis of a vulnerability")],
        _policy(), existing_names={"semgrep"},
    )

    assert selection.selected_names == []
    assert _reasons(selection)["semgrep"] == SKIP_NAME_CLASH


def test_two_skills_describing_the_same_job_keep_only_one() -> None:
    shared = (
        "Scans the repository for a known vulnerability and reports security analysis "
        "findings with remediation guidance for every affected dependency"
    )
    selection = select_skills([
        _candidate("scanner-a", shared),
        _candidate("scanner-b", shared + " quickly"),
    ], _policy())

    assert len(selection.selected) == 1
    assert _reasons(selection)["scanner-b"] == SKIP_REDUNDANT


def test_skills_covering_different_capabilities_are_both_kept() -> None:
    selection = select_skills([
        _candidate("vuln", "Finds a vulnerability and a CVE in a dependency"),
        _candidate("audit", "Performs a security review and sast audit of the source"),
    ], _policy())

    assert len(selection.selected) == 2


# --- rule 3: the limit ---------------------------------------------------------------


def test_the_limit_stops_a_large_repository_from_spending_the_context() -> None:
    # Distinct wording, so the limit is what bites rather than the redundancy rule.
    subjects = [
        "parser", "allocator", "scheduler", "serialiser", "template engine", "regex backend",
        "archive reader", "font shaper", "image decoder", "crypto primitive",
    ]
    candidates = [
        _candidate(f"scan-{subject.replace(' ', '-')}", f"Finds a vulnerability in a {subject}")
        for subject in subjects
    ]
    selection = select_skills(candidates, _policy(limit=3))

    assert len(selection.selected) == 3
    assert selection.skipped_by_reason()[SKIP_OVER_LIMIT] == len(subjects) - 3
    assert selection.available == len(subjects)


def test_every_skill_is_accounted_for_exactly_once() -> None:
    """The report must add up, or the counts shown to the user are wrong."""
    candidates = [_candidate("a", "a vulnerability scanner"), _candidate("b", "unrelated prose")]
    candidates += [_candidate(f"s{i}", "security analysis of a vulnerability") for i in range(5)]
    selection = select_skills(candidates, _policy(limit=2))

    assert len(selection.selected) + sum(selection.skipped_by_reason().values()) == len(candidates)
    assert selection.available == len(candidates)


@pytest.mark.parametrize("mode", list(SetupMode))
def test_the_limit_follows_the_mode_and_a_configured_override_wins(mode: SetupMode) -> None:
    assert limit_for(mode) == LIMIT_BY_MODE[mode]
    assert limit_for(mode, 25) == 25
    assert limit_for(mode, None) == LIMIT_BY_MODE[mode]


def test_minimal_keeps_less_context_than_performance() -> None:
    assert LIMIT_BY_MODE[SetupMode.MINIMAL] < LIMIT_BY_MODE[SetupMode.PERFORMANCE]


# --- ranking -------------------------------------------------------------------------


def test_a_skill_covering_more_requested_capabilities_is_preferred() -> None:
    selection = select_skills([
        _candidate("narrow", "A security analysis helper"),
        _candidate("broad", "Finds a vulnerability and runs a security analysis sast audit"),
    ], _policy(limit=1))

    assert selection.selected_names == ["broad"]


def test_the_alphabet_does_not_decide_between_equal_matches() -> None:
    """Ordering by name would let 'a' win, which is the bias the query builder dropped."""
    selection = select_skills([
        _candidate("aaa-thin", "one vulnerability mention"),
        _candidate("zzz-rich", "a vulnerability, a cve and exploit research all together"),
    ], _policy(limit=1))

    assert selection.selected_names == ["zzz-rich"]


def test_selection_is_the_same_whatever_order_the_repository_is_read_in() -> None:
    candidates = [
        _candidate("one", "vulnerability research on a cve"),
        _candidate("two", "security analysis and sast audit"),
        _candidate("three", "unrelated"),
        _candidate("four", "a cve and a vulnerability in a dependency"),
    ]
    forward = select_skills(candidates, _policy(limit=2)).selected_names
    reverse = select_skills(list(reversed(candidates)), _policy(limit=2)).selected_names

    assert forward == reverse


# --- the Plan attaches the policy ----------------------------------------------------


def _recommendation() -> RecommendationPlan:
    return RecommendationPlan(
        interview=InterviewAnswer(
            agents=[AgentType.CODEX], domains=[WorkDomain.VULNERABILITY_RESEARCH],
            tasks=["cve_analysis"], mode=SetupMode.MINIMAL,
        ),
        capabilities=set(SECURITY), items=[],
    )


def test_the_plan_tells_the_adapter_what_this_run_asked_for() -> None:
    component = Component(
        id="pack", name="Pack", type=ComponentType.SKILL,
        github_url="https://github.com/example/pack",
    )

    scoped = _with_skill_policy(component, _recommendation(), 4)

    assert scoped.skill_selection is not None
    assert scoped.skill_selection.capabilities == SECURITY
    assert scoped.skill_selection.limit == 4
    assert component.skill_selection is None, "the candidate itself must not be mutated"


def test_an_mcp_component_gets_no_skill_policy() -> None:
    component = Component(
        id="mcp", name="MCP", type=ComponentType.MCP,
        github_url="https://github.com/example/mcp",
    )

    assert _with_skill_policy(component, _recommendation(), 4).skill_selection is None


# --- a repeated setup must not drift -------------------------------------------------


def test_a_components_own_skills_are_not_treated_as_a_name_clash(tmp_path) -> None:
    """Otherwise every run installs a different set, which reinstalling must never do."""
    root = tmp_path / "skills"
    for owner, skill in (("pack", "semgrep"), ("other-pack", "codeql"), (None, "mine")):
        directory = root / f"{owner or 'user'}--{skill}"
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(
            f"---\nname: {skill}\ndescription: a security analysis tool\n---\n", encoding="utf-8",
        )
        if owner:
            (directory / ".grayom-component.json").write_text(
                json.dumps({"component_id": owner}), encoding="utf-8",
            )

    names = foreign_skill_names(root, "pack")

    assert names == {"codeql", "mine"}, "its own Skill is the same Skill, not a collision"


def test_a_repeated_selection_chooses_the_same_skills() -> None:
    candidates = [
        _candidate(f"s{index}", f"vulnerability research number {index} with a cve")
        for index in range(12)
    ]
    first = select_skills(candidates, _policy(limit=4))
    again = select_skills(candidates, _policy(limit=4))

    assert first.selected_names == again.selected_names


def test_foreign_skill_names_is_empty_when_nothing_is_installed(tmp_path) -> None:
    assert foreign_skill_names(tmp_path / "absent", "pack") == set()


# --- the one-line report -------------------------------------------------------------


def test_a_narrowed_skill_repository_reports_what_it_took() -> None:
    outcome = InstalledComponent(
        agent=AgentType.CODEX, component_id="pack", name="Trail of Bits Skills",
        type=ComponentType.SKILL, changed=True, skills_available=85,
        skills_selected=["semgrep", "codeql", "variant-analysis", "differential-review"],
    )

    summary = outcome.summary()

    assert summary.startswith("4 of 85 Skills: semgrep, codeql, variant-analysis")
    assert "+1 more" in summary


def test_a_fully_installed_repository_does_not_claim_to_have_narrowed() -> None:
    outcome = InstalledComponent(
        agent=AgentType.CODEX, component_id="pack", name="Pack", type=ComponentType.SKILL,
        changed=True, skills_available=2, skills_selected=["one", "two"],
    )

    assert outcome.summary() == "2 Skills: one, two"


def test_a_repository_with_no_match_says_so_rather_than_appearing_installed() -> None:
    outcome = InstalledComponent(
        agent=AgentType.CODEX, component_id="pack", name="Pack", type=ComponentType.SKILL,
        skills_available=85, skills_selected=[],
    )

    assert outcome.summary() == "no Skill matched (of 85 in the repository)"


def test_an_mcp_reports_the_name_it_was_registered_under() -> None:
    registered = InstalledComponent(
        agent=AgentType.CODEX, component_id="github", name="GitHub MCP",
        type=ComponentType.MCP, changed=True, configured_mcp=["github-grayom"],
    )
    preserved = registered.model_copy(update={"changed": False})

    assert registered.summary() == "MCP registered as github-grayom"
    assert preserved.summary() == "MCP already registered"


# --- rule 4: one sub-project does not take the whole budget --------------------------


def _grouped(name: str, description: str, group: str) -> SkillCandidate:
    return SkillCandidate(
        name=name, description=description, directory=f"plugins/{group}/skills/{name}",
        group=group,
    )


def test_one_part_of_a_repository_cannot_take_the_whole_budget() -> None:
    """Six per-platform scanners are one job described six times.

    Measured on `trailofbits/skills`: a request for CVE analysis and OSS vulnerability
    research gave `building-secure-contracts` 7 of the 12 Performance slots, because the
    redundancy rule compares wording and each description names a different platform. The
    repository's own grouping already says they belong together.
    """
    # Worded after the repository's own descriptions: each names its platform's own
    # vulnerability classes, which is why comparing wording does not recognise them as one
    # job. The group does.
    platforms = {
        "algorand": "rekeying attacks, unchecked transaction fees and missing field "
                    "validations in TEAL and PyTeal",
        "cairo": "felt overflow, storage collision and L1 handler authentication gaps "
                 "in Starknet programs",
        "cosmos": "non-deterministic begin-block logic, unbounded iteration and gas "
                  "exhaustion in SDK modules",
        "solana": "missing signer and owner checks, account confusion and arithmetic "
                  "truncation in Anchor programs",
        "substrate": "weight miscalculation, unsigned extrinsic abuse and runtime "
                     "storage migration faults in pallets",
        "ton": "message bounce handling, unbounded dictionary growth and replay of "
               "external messages in FunC",
    }
    candidates = [
        _grouped(
            f"{platform}-vulnerability-scanner",
            f"Scans {platform} smart contracts for {classes}. Use when auditing a "
            f"{platform} project before a security review.",
            "building-secure-contracts",
        )
        for platform, classes in platforms.items()
    ] + [
        _grouped(
            "semgrep",
            "Runs a Semgrep SAST scan over a codebase: detects languages, selects rule "
            "packs and reports each vulnerability with its data flow sink.",
            "static-analysis",
        ),
        _grouped(
            "c-review",
            "Reviews C for memory safety: use-after-free, off-by-one bounds and integer "
            "promotion defects that a vulnerability audit has to cover.",
            "c-review",
        ),
    ]

    selection = select_skills(candidates, _policy(limit=6))

    from_contracts = [
        name for name in selection.selected_names if name.endswith("-vulnerability-scanner")
    ]
    assert len(from_contracts) == 2, f"quota is a third of the limit, got {from_contracts}"
    assert {"semgrep", "c-review"}.issubset(set(selection.selected_names))
    assert SKIP_GROUP_FULL in selection.skipped_by_reason()


def test_the_group_share_scales_with_the_limit() -> None:
    assert group_quota(6) == 2
    assert group_quota(12) == 4
    # A limit smaller than three still has to admit one Skill per group, or a request could
    # select nothing at all from a grouped repository.
    assert group_quota(1) == 1
    assert group_quota(2) == 1


def test_a_flat_repository_is_not_rationed_as_one_group() -> None:
    """Without a grouping there is nothing to spread across, so the limit alone applies."""
    subjects = [
        "use-after-free in C allocators", "deserialization of untrusted YAML",
        "server-side request forgery in webhook handlers", "weak JWT signature verification",
        "path traversal in archive extraction", "SQL injection through string formatting",
        "hardcoded credentials in container images", "race conditions in file locking",
        "XML external entity expansion", "insecure random number seeding",
    ]
    candidates = [
        _candidate(f"scanner-{index}", f"Finds the vulnerability class {subject}.")
        for index, subject in enumerate(subjects)
    ]

    selection = select_skills(candidates, _policy(limit=6))

    assert len(selection.selected) == 6
    assert SKIP_GROUP_FULL not in selection.skipped_by_reason()


def test_a_group_with_fewer_skills_than_its_share_is_not_padded() -> None:
    candidates = [
        _grouped(
            "semgrep",
            "Runs a Semgrep SAST scan and reports each vulnerability with its data flow sink.",
            "static-analysis",
        ),
        _grouped(
            "c-review",
            "Reviews C for the memory safety vulnerability classes an audit must cover.",
            "c-review",
        ),
    ]

    selection = select_skills(candidates, _policy(limit=6))

    assert len(selection.selected) == 2


@pytest.mark.parametrize(
    ("directory", "expected"),
    [
        ("plugins/building-secure-contracts/skills/audit-prep-assistant", "building-secure-contracts"),
        ("plugins/static-analysis/skills/codeql", "static-analysis"),
        # A flat repository has no sub-project, so there is nothing to ration.
        ("skills/review", ""),
        ("review", ""),
    ],
)
def test_the_group_comes_from_where_the_skill_sits(directory: str, expected: str) -> None:
    assert skill_group(Path(directory)) == expected


def test_a_repositorys_own_test_fixtures_are_not_installable_skills() -> None:
    """`trailofbits/skills` keeps two SKILL.md files under `tests/fixtures/`.

    One of them ranked 19th of 85 for a security request, so without this exclusion a
    repository's test data becomes a Skill its own authors never published.
    """
    fixtures = [
        Path("plugins/code-improver/tests/fixtures/pr-review-toolkit/skills/review-pr/SKILL.md"),
        Path("plugins/code-improver/tests/fixtures/review-panel/skills/panel-review/SKILL.md"),
    ]
    published = Path("plugins/code-improver/skills/code-improver/SKILL.md")

    assert all(NON_PUBLISHED_DIRECTORIES.intersection(item.parts) for item in fixtures)
    assert not NON_PUBLISHED_DIRECTORIES.intersection(published.parts)


# --- rule 5: coverage before depth ---------------------------------------------------


def test_the_only_skill_covering_a_capability_is_not_crowded_out() -> None:
    """Claiming a capability and installing nothing that provides it is the worse failure.

    Measured on `trailofbits/skills` at its pinned ref: a request for web application
    assessment reported `web_security_testing` as covered, because the repository does carry
    `burpsuite-project-parser`, and then installed six other Skills — the one Skill
    providing it ranked below the limit. Scarce capabilities now take a slot first.
    """
    wanted = {Capability.VULNERABILITY_RESEARCH, Capability.BROWSER_AUTOMATION}
    crowd = [
        _candidate(
            f"advisory-{index}",
            f"Reads a vulnerability advisory about {subject} and summarises its impact.",
        )
        for index, subject in enumerate([
            "heap corruption in image parsers", "unsafe deserialization in RPC servers",
            "privilege escalation through setuid helpers", "integer overflow in codecs",
            "signature bypass in update channels", "cache poisoning in reverse proxies",
            "symlink races in extraction tools",
        ])
    ]
    only_one = _candidate(
        "session-driver",
        "Drives a headless browser automation session to replay an authenticated flow.",
    )

    selection = select_skills(crowd + [only_one], _policy(limit=6, capabilities=wanted))

    assert "session-driver" in selection.selected_names, (
        "the single Skill covering browser_automation lost its slot to a seventh "
        "vulnerability_research Skill"
    )
    covered = {
        capability for item in selection.selected
        for capability in wanted
        if mentions(item.text, CAPABILITY_KEYWORDS[capability])
    }
    assert covered == wanted


def test_coverage_does_not_override_the_group_share_or_the_limit() -> None:
    """A capability only one group can cover must not let that group exceed its share."""
    candidates = [
        _grouped(
            f"{platform}-scanner",
            f"Scans {platform} smart contracts for the vulnerability classes specific to "
            f"{platform}, and audits their deployment settings.",
            "contracts",
        )
        for platform in ("algorand", "cairo", "cosmos", "solana", "ton")
    ]

    selection = select_skills(candidates, _policy(limit=6))

    assert len(selection.selected) <= group_quota(6)


def test_every_skill_is_still_accounted_for_once_after_two_passes() -> None:
    """Coverage and fill are two passes over the same list; decisions must not double up."""
    candidates = [
        _candidate("scanner", "Finds a vulnerability class in source code."),
        _candidate("reporter", "Writes the reporting section of a security audit."),
        _candidate("unrelated", "Formats spreadsheets for quarterly planning."),
    ]

    selection = select_skills(candidates, _policy(limit=2))

    assert selection.available == len(candidates)
    assert len(selection.decisions) == len(candidates)
    assert len({decision.name for decision in selection.decisions}) == len(candidates)


# --- curated Skill paths -------------------------------------------------------------


REGISTRY_CLONES = {
    "trailofbits-skills": "https://github.com/trailofbits/skills",
    "superpowers": "https://github.com/obra/superpowers",
    "addy-agent-skills": "https://github.com/addyosmani/agent-skills",
}


def _curated_entries():
    from grayom_agent_guidance.registry.loader import load_registry

    return [item for item in load_registry() if item.install_method.subpaths]


def test_a_curated_path_cannot_reach_outside_the_repository_it_pinned() -> None:
    """A Registry entry names paths inside its own pinned clone and nowhere else."""
    entries = _curated_entries()
    assert entries, "no Registry entry curates its Skills"

    for component in entries:
        subpaths = component.install_method.subpaths
        assert len(set(subpaths)) == len(subpaths), f"{component.id} repeats a path"
        for subpath in subpaths:
            assert not subpath.startswith("/"), (component.id, subpath)
            assert ".." not in Path(subpath).parts, (component.id, subpath)
            assert Path(subpath).parts, (component.id, subpath)


def test_a_curated_path_is_resolved_inside_the_clone_only(tmp_path) -> None:
    from grayom_agent_guidance.adapters.json_support import _curated_files

    repo = tmp_path / "repo"
    (repo / "skills" / "wanted").mkdir(parents=True)
    (repo / "skills" / "wanted" / "SKILL.md").write_text("---\nname: wanted\n---\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_text("---\nname: outside\n---\n", encoding="utf-8")

    files, missing = _curated_files(repo, ["skills/wanted", "../outside", "skills/gone"])

    assert [item.parent.name for item in files] == ["wanted"]
    assert missing == ["../outside", "skills/gone"]


def test_a_curated_path_upstream_removed_is_reported_and_skipped(tmp_path, monkeypatch) -> None:
    """`update` reinstalls at a newer ref with the same curated paths.

    Upstream can rename or drop one between refs. Failing the whole install would make a
    single upstream rename break every update of the component, so the path is reported and
    the rest still install.
    """
    from grayom_agent_guidance.adapters.json_support import install_git_skills

    source = tmp_path / "clone"
    for name in ("kept", "also-kept"):
        directory = source / "skills" / name
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Finds a vulnerability class in source code.\n---\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(
        "grayom_agent_guidance.adapters.json_support.clone_pinned",
        lambda component, destination: source,
    )
    component = Component(
        id="curated-pack", name="Curated Pack", type=ComponentType.SKILL,
        github_url="https://github.com/example/pack",
        supported_agents={AgentType.CLAUDE_CODE}, capabilities={Capability.VULNERABILITY_RESEARCH},
        install_method=InstallMethod(
            kind=InstallKind.GIT_SKILLS, repository="https://github.com/example/pack",
            ref="deadbee",
            subpaths=["skills/kept", "skills/renamed-upstream", "skills/also-kept"],
        ),
    )

    result = install_git_skills(component, tmp_path / "skills-root")

    assert result.changed
    assert sorted(path.name for path in result.created_paths) == [
        "curated-pack--also-kept", "curated-pack--kept",
    ]
    assert any("skills/renamed-upstream" in note for note in result.notes)


def test_a_component_whose_every_curated_path_is_gone_fails_loudly(tmp_path, monkeypatch) -> None:
    from grayom_agent_guidance.adapters.json_support import install_git_skills

    source = tmp_path / "clone"
    source.mkdir()
    monkeypatch.setattr(
        "grayom_agent_guidance.adapters.json_support.clone_pinned",
        lambda component, destination: source,
    )
    component = Component(
        id="curated-pack", name="Curated Pack", type=ComponentType.SKILL,
        github_url="https://github.com/example/pack",
        supported_agents={AgentType.CLAUDE_CODE}, capabilities={Capability.VULNERABILITY_RESEARCH},
        install_method=InstallMethod(
            kind=InstallKind.GIT_SKILLS, repository="https://github.com/example/pack",
            ref="deadbee", subpaths=["skills/gone"],
        ),
    )

    with pytest.raises(AdapterError, match="no installable SKILL.md"):
        install_git_skills(component, tmp_path / "skills-root")


def test_curation_does_not_claim_a_capability_the_curated_set_cannot_cover() -> None:
    """Narrowing the pool must not leave a declared capability with no Skill behind it.

    `configuration_audit` was declared on `trailofbits-skills` on the strength of
    `firebase-apk-scanner`; scanning an APK for Firebase misconfigurations is not the
    baseline review of servers and databases the question asks about, so the claim was
    withdrawn rather than curated around.
    """
    from grayom_agent_guidance.registry.loader import load_registry

    entry = next(item for item in load_registry() if item.id == "trailofbits-skills")

    assert Capability.CONFIGURATION_AUDIT not in entry.capabilities
    assert Capability.WEB_SECURITY_TESTING in entry.capabilities
    assert any(
        "burpsuite" in subpath for subpath in entry.install_method.subpaths
    ), "web_security_testing is declared, so the Skill providing it must be curated in"
