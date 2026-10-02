from agent_guidance.sources.repository_security import scan_repository


def test_repository_security_uses_file_evidence_for_warning_metadata() -> None:
    result = scan_repository({
        "install.sh": "curl https://example.test/tool.sh | bash\nrm -rf ./cache\n",
        "runner.py": "import subprocess\nsubprocess.run(['tool'])\n",
    })
    assert result.metadata.external_download
    assert result.metadata.filesystem_delete
    assert result.metadata.subprocess
    assert any(item.location.startswith("install.sh") for item in result.evidence)
    assert result.warnings
