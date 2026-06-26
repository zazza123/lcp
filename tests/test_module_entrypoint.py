import subprocess, sys


def test_python_m_lcp_version():
    out = subprocess.run([sys.executable, "-m", "lcp", "--version"],
                         capture_output=True, text=True)
    assert out.returncode == 0
    assert "lcp" in (out.stdout + out.stderr).lower()
