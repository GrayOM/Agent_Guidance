"""Resolve an npm-launched MCP server against the npm registry, and pin it.

A discovered MCP server's launch command is read out of the repository's README, because that
is where a project writes it. A README is the repository owner's own prose, so what it says is
a claim. Taken at face value it produced three problems at once:

  - The package name was never checked against anything. A README under
    `Sengtocxoen/sast-mcp` reading `npx -y @someone-else/other-package` was written into the
    user's Agent configuration unexamined, so repository ownership and npm package ownership
    were not connected at any point.
  - Nothing was pinned. Skills are pinned to `head_sha`; `npx -y name` resolves npm's current
    latest every time the Agent starts the server, so a package that is clean on the day it is
    installed is not the package that runs next week.
  - The risk review had nothing to say about either, so the approval screen showed no reason
    to look twice, and the candidate was labelled verified.

This module answers the first two. It asks the registry whether the package exists, what its
latest version is, and which repository it declares, then pins the install to that exact
version. A package that cannot be resolved is not installable, which is a hard failure in the
validator rather than a warning: an unpinned install is the thing being removed.

The client is built here rather than reused from the GitHub source on purpose. That client
carries `Authorization: Bearer <GITHUB_TOKEN>`, and sending a user's GitHub token to a third
party because the two requests happen in the same function would be a worse defect than the
one this module fixes.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from pydantic import BaseModel

from agent_guidance.models import Component, InstallKind
from agent_guidance.network import create_async_client


REGISTRY = "https://registry.npmjs.org"

# The whole document for a popular package is megabytes of version history. The `latest`
# dist-tag document is the one version, which is all that is needed to pin.
LATEST = "{registry}/{package}/latest"


class ResolvedPackage(BaseModel):
    """What the registry says about a package, as far as it bears on installing it."""

    name: str
    version: str
    # The repository the package itself declares, as `owner/repo`, when it declares one that
    # can be read as a GitHub repository. Absent for a package that publishes no repository
    # field, which is common and not suspicious on its own.
    repository: str | None = None


def split_package_spec(token: str) -> tuple[str, str | None]:
    """Separate a package name from the version spec a README may already carry.

    `npx -y sast-mcp@latest` scrapes as one token, and `@latest` is not part of the name.
    A scoped package is itself `@scope/name`, so the leading `@` is never the separator and
    `@scope/name@1.2.3` splits at the second one.

    The requested spec is returned but not honoured: a README asking for `@latest` is asking
    for the unpinned behaviour being removed here, and a README asking for `@1.2.3` is still
    the README talking. Both are replaced by the version the registry reports.
    """
    if token.startswith("@"):
        at = token.find("@", 1)
    else:
        at = token.find("@")
    if at <= 0:
        return token, None
    return token[:at], token[at + 1:] or None


def _declared_repository(document: dict[str, Any]) -> str | None:
    """`owner/repo` from a package's repository field, in any of the shapes npm allows.

    npm accepts a string (`"owner/repo"`, a git URL, a shorthand like `github:owner/repo`) or
    an object with a `url`. Anything that is not recognisably a GitHub repository is reported
    as absent rather than guessed at, because a wrong match here would wave through exactly
    the case this check exists to catch.
    """
    field = document.get("repository")
    raw = field.get("url") if isinstance(field, dict) else field
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    for prefix in ("git+", "git://", "ssh://", "https://", "http://", "git@"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    text = text.removeprefix("github:").removeprefix("gh:")
    for host in ("github.com/", "github.com:", "www.github.com/"):
        if text.startswith(host):
            text = text[len(host):]
            break
    else:
        # A bare `owner/repo` shorthand is a GitHub reference by npm's own rules. Anything
        # still carrying a host is some other forge, which this check cannot speak to.
        if "/" not in text or text.count("/") != 1 or "." in text.split("/")[0]:
            return None
    text = text.removesuffix(".git").strip("/")
    parts = text.split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    return f"{parts[0]}/{parts[1]}".lower()


async def resolve_package(package: str, *, client: httpx.AsyncClient) -> ResolvedPackage:
    """Ask the registry about one package.

    Raises `LookupError` when the package does not exist and `httpx.HTTPError` when the
    registry could not be reached. The caller distinguishes them in the message it records,
    because "no such package" and "npm was unreachable" are different things to tell a user,
    even though neither leaves a candidate installable.
    """
    response = await client.get(LATEST.format(registry=REGISTRY, package=package))
    if response.status_code == 404:
        raise LookupError(f"npm has no package named {package}")
    response.raise_for_status()
    document = response.json()
    if not isinstance(document, dict) or not document.get("version"):
        raise LookupError(f"npm returned no version for {package}")
    return ResolvedPackage(
        name=str(document.get("name") or package),
        version=str(document["version"]),
        repository=_declared_repository(document),
    )


async def pin_npm_install(
    component: Component,
    *,
    repository_full_name: str,
    client: httpx.AsyncClient | None = None,
) -> Component:
    """Pin a README-derived npm MCP install to a resolved version, or mark it uninstallable.

    Only an npm-launched MCP server taken from a README is touched. A registry entry declares
    its own install method and is left alone; an HTTP MCP server has no version to pin, and
    carries the README warning instead.

    `repository_full_name` is the repository the candidate was discovered from, which is what
    the declared repository is compared against. The comparison is the point: it is the only
    thing connecting "this GitHub project" to "this npm package".
    """
    method = component.install_method
    if not (method.kind == InstallKind.MCP_STDIO and method.from_readme and method.package):
        return component

    owned = client is None
    http = client or create_async_client(timeout=5)
    try:
        resolved = await resolve_package(method.package, client=http)
    except LookupError as exc:
        method.pin_failure = str(exc)
        return component
    except asyncio.TimeoutError:
        method.pin_failure = f"npm timed out while pinning {method.package}"
        return component
    except (httpx.HTTPError, OSError) as exc:
        method.pin_failure = (
            f"npm could not be reached to pin {method.package}: {exc or exc.__class__.__name__}"
        )
        return component
    finally:
        if owned:
            await http.aclose()

    discovered = repository_full_name.strip("/").lower()
    if resolved.repository and resolved.repository != discovered:
        # The shape of a package advertised under a repository that does not own it. The
        # innocent cause is a fork whose README still carries upstream's install line; the fix
        # is the same either way, which is for the repository to name its own package.
        method.pin_failure = (
            f"npm package {resolved.name} declares repository {resolved.repository}, not "
            f"{discovered}, so this repository does not own the package its README installs"
        )
        return component
    if not resolved.repository:
        component.validation_warnings = list(dict.fromkeys(
            component.validation_warnings
            + [f"npm package {resolved.name} declares no repository, so ownership is unverified"]
        ))

    method.package = resolved.name
    method.package_version = resolved.version
    # The args are what gets written to the Agent configuration, so the pin has to land there
    # and not only on the model. The scraped token is replaced wherever it sits, because the
    # README decides the flag order and `-y` is not always first.
    method.args = [
        f"{resolved.name}@{resolved.version}"
        if split_package_spec(argument)[0] == resolved.name else argument
        for argument in method.args
    ]
    return component
