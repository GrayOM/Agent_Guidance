"""Choose which Skills of a repository to install.

A Skill repository is not one Skill. `trailofbits/skills` holds 85, and installing all of
them put roughly 7,800 tokens of names and descriptions into every Agent conversation for a
user who had asked about two things, alongside Skills for organisational-culture metrics and
Lean proofs. More Skills is not a better setup: each one costs context whether it is used or
not, and two Skills that do the same job make the Agent's choice worse rather than wider.

Selection is three rules, applied to what each Skill says about itself:

1. keep a Skill only if it speaks to a capability this run asked for
2. drop a Skill that conflicts with one already kept, by name or by purpose
3. stop at the limit, strongest match first

The capability vocabulary is the same table discovery uses to recognise a repository, so a
Skill is judged by the words the rest of GrayOM already understands.
"""

import re

from pydantic import BaseModel, Field

from grayom_agent_guidance.models import Capability, SkillSelectionPolicy, SetupMode
from grayom_agent_guidance.sources.normalizer import CAPABILITY_KEYWORDS, mentions


# An Agent loads every installed Skill's description, so Minimal keeps the context small and
# Performance trades context for coverage. GrayOMConfig can override both.
LIMIT_BY_MODE: dict[SetupMode, int] = {SetupMode.MINIMAL: 6, SetupMode.PERFORMANCE: 12}

# Two Skills matching the same capabilities whose descriptions share this much wording are
# treated as the same job described twice.
REDUNDANCY_THRESHOLD = 0.6

_WORD = re.compile(r"[a-z][a-z0-9+#.-]{3,}")

SKIP_UNRELATED = "unrelated to the selected work"
SKIP_NAME_CLASH = "another Skill already uses this name"
SKIP_REDUNDANT = "same job as a Skill already selected"
SKIP_OVER_LIMIT = "over the Skill limit for this mode"
SKIP_GROUP_FULL = "this part of the repository already contributed its share"


def group_quota(limit: int) -> int:
    """How many Skills one sub-project of a repository may contribute.

    Measured on `trailofbits/skills`: a request for CVE analysis and OSS vulnerability
    research matched 47 of its 85 Skills across 27 plugin groups, but
    `building-secure-contracts` held 10 of the 47 and took 3 of the 6 Minimal slots with
    per-platform smart-contract scanners. Those six scanners are one job described six
    times, which the redundancy rule misses because each description names a different
    platform. The repository's own grouping already says they belong together, so a share
    of the budget per group catches what word overlap cannot.
    """
    return max(1, limit // 3)


def limit_for(mode: SetupMode, configured: int | None = None) -> int:
    return configured if configured else LIMIT_BY_MODE.get(mode, LIMIT_BY_MODE[SetupMode.MINIMAL])


class SkillCandidate(BaseModel):
    """One Skill a cloned repository offers."""

    name: str
    description: str = ""
    directory: str
    # The repository's own sub-project this Skill belongs to, empty when it publishes a flat
    # list. Only a named group is rationed: capping an ungrouped repository would cap it as
    # a whole and install two Skills out of fifty.
    group: str = ""

    @property
    def text(self) -> str:
        return f"{self.name} {self.description}".lower()

    def words(self) -> set[str]:
        return set(_WORD.findall(self.description.lower()))


class SkillDecision(BaseModel):
    name: str
    selected: bool
    reason: str
    capabilities: list[str] = Field(default_factory=list)


class SkillSelection(BaseModel):
    selected: list[SkillCandidate] = Field(default_factory=list)
    decisions: list[SkillDecision] = Field(default_factory=list)

    @property
    def available(self) -> int:
        return len(self.decisions)

    @property
    def selected_names(self) -> list[str]:
        return [item.name for item in self.selected]

    def skipped_by_reason(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for decision in self.decisions:
            if not decision.selected:
                counts[decision.reason] = counts.get(decision.reason, 0) + 1
        return counts


def _matched(candidate: SkillCandidate, wanted: set[Capability]) -> set[Capability]:
    text = candidate.text
    return {
        capability for capability in wanted
        if mentions(text, CAPABILITY_KEYWORDS.get(capability, ()))
    }


def _keyword_hits(candidate: SkillCandidate, wanted: set[Capability]) -> int:
    """How many of the requested vocabulary's words a Skill actually uses.

    This breaks ties between Skills matching the same number of capabilities. It is a weak
    signal, but it is a signal: ordering by name instead would let the alphabet decide,
    which is the bias the search query builder already had to drop.
    """
    text = candidate.text
    return sum(
        1 for capability in wanted
        for keyword in CAPABILITY_KEYWORDS.get(capability, ())
        if mentions(text, (keyword,))
    )


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def select_skills(
    candidates: list[SkillCandidate],
    policy: SkillSelectionPolicy,
    *,
    existing_names: set[str] | None = None,
) -> SkillSelection:
    """Pick the Skills worth installing, and record why each of the others was not.

    Ranking is by how many requested capabilities a Skill speaks to, then by how much of the
    requested vocabulary it uses, then by name, so the same repository and the same request
    always produce the same selection.
    """
    taken = {name.lower() for name in (existing_names or set())}
    by_rank = sorted(
        (
            (candidate, _matched(candidate, policy.capabilities),
             _keyword_hits(candidate, policy.capabilities))
            for candidate in candidates
        ),
        key=lambda item: (-len(item[1]), -item[2], item[0].name),
    )
    scored: list[tuple[SkillCandidate, set[Capability]]] = [
        (candidate, matched) for candidate, matched, _ in by_rank
    ]

    selection = SkillSelection()
    kept: list[tuple[SkillCandidate, set[Capability], set[str]]] = []
    quota = group_quota(policy.limit)
    taken_per_group: dict[str, int] = {}
    outcome: dict[int, str] = {}
    chosen: set[int] = set()

    def consider(index: int) -> bool:
        """Take this Skill if every rule allows it, and record why when one does not."""
        if index in outcome:
            return False
        candidate, matched = scored[index]
        covered = sorted(item.value for item in matched)
        if not matched:
            outcome[index] = SKIP_UNRELATED
            return False
        if candidate.name.lower() in taken:
            outcome[index] = SKIP_NAME_CLASH
            return False
        words = candidate.words()
        if any(
            other_matched == matched and _overlap(words, other_words) >= REDUNDANCY_THRESHOLD
            for _, other_matched, other_words in kept
        ):
            outcome[index] = SKIP_REDUNDANT
            return False
        if candidate.group and taken_per_group.get(candidate.group, 0) >= quota:
            outcome[index] = SKIP_GROUP_FULL
            return False
        if len(selection.selected) >= policy.limit:
            outcome[index] = SKIP_OVER_LIMIT
            return False
        if candidate.group:
            taken_per_group[candidate.group] = taken_per_group.get(candidate.group, 0) + 1
        selection.selected.append(candidate)
        chosen.add(index)
        outcome[index] = "covers " + ", ".join(covered)
        taken.add(candidate.name.lower())
        kept.append((candidate, matched, words))
        return True

    # Coverage before depth. Filling purely by rank let a capability the repository *can*
    # satisfy go unrepresented while several Skills covered an already-covered one: a
    # request for web application assessment reported web_security_testing as covered and
    # installed nothing providing it, because the only such Skill ranked below the limit.
    # Scarce capabilities go first, so the one Skill that can cover a capability is not
    # displaced by the seventh Skill covering a crowded one.
    reachable = [
        capability for capability in policy.capabilities
        if any(capability in matched for _, matched in scored)
    ]
    scarcity = {
        capability: sum(1 for _, matched in scored if capability in matched)
        for capability in reachable
    }
    for capability in sorted(reachable, key=lambda item: (scarcity[item], item.value)):
        for index, (_, matched) in enumerate(scored):
            if capability in matched and consider(index):
                break

    for index in range(len(scored)):
        consider(index)

    # Decisions stay in rank order whichever pass took each Skill, so the report reads the
    # same way it always did and every Skill is accounted for exactly once.
    for index, (candidate, matched) in enumerate(scored):
        reason = outcome[index]
        selection.decisions.append(SkillDecision(
            name=candidate.name, selected=index in chosen, reason=reason,
            capabilities=[] if reason == SKIP_UNRELATED else sorted(
                item.value for item in matched
            ),
        ))
    return selection
